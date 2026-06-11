// Data-client fallback chain: live → demo, mid-session degradation, paths.
import { beforeEach, describe, expect, it, vi } from "vitest";

const ok = (payload) =>
  Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
const fail = (status = 503) =>
  Promise.resolve({ ok: false, status, json: () => Promise.resolve({}) });

// api.js caches the resolved mode in module state, so each test gets a
// fresh copy via resetModules + dynamic import.
async function freshApi() {
  vi.resetModules();
  return import("./api.js");
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe("resolveMode", () => {
  it("is live when /api/meta responds", async () => {
    vi.stubGlobal("fetch", vi.fn(() => ok({ mode: "live" })));
    const api = await freshApi();
    expect(await api.resolveMode()).toBe("live");
  });

  it("is demo when /api/meta 503s (no Supabase configured)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => fail(503)));
    const api = await freshApi();
    expect(await api.resolveMode()).toBe("demo");
  });

  it("is demo when the network throws entirely", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
    const api = await freshApi();
    expect(await api.resolveMode()).toBe("demo");
  });
});

describe("getData", () => {
  it("reads /api/<name> in live mode", async () => {
    const fetchMock = vi.fn((url) =>
      ok(url === "/api/meta" ? { mode: "live" } : { tickers: [1] })
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = await freshApi();
    const data = await api.getData("trending");
    expect(data.tickers).toEqual([1]);
    expect(fetchMock).toHaveBeenCalledWith("/api/trending");
  });

  it("reads static /data/<name>.json in demo mode", async () => {
    const fetchMock = vi.fn((url) =>
      url.startsWith("/api/") ? fail() : ok({ source: "static" })
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = await freshApi();
    const data = await api.getData("trending");
    expect(data.source).toBe("static");
    expect(fetchMock).toHaveBeenCalledWith("/data/trending.json");
  });

  it("degrades live → demo when the API flakes mid-session", async () => {
    const fetchMock = vi.fn((url) => {
      if (url === "/api/meta") return ok({ mode: "live" });
      if (url === "/api/trending") return fail(500); // live endpoint breaks
      return ok({ source: "static" });
    });
    vi.stubGlobal("fetch", fetchMock);
    const api = await freshApi();
    await api.resolveMode();
    const data = await api.getData("trending");
    expect(data.source).toBe("static");
    expect(api.currentMode()).toBe("demo");
  });
});

describe("getTicker", () => {
  it("uses the static per-ticker path in demo mode", async () => {
    const fetchMock = vi.fn((url) =>
      url.startsWith("/api/") ? fail() : ok({ trend: { ticker: "NVDA" } })
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = await freshApi();
    const data = await api.getTicker("NVDA");
    expect(data.trend.ticker).toBe("NVDA");
    expect(fetchMock).toHaveBeenCalledWith("/data/tickers/NVDA.json");
  });
});
