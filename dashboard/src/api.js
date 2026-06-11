// Data client with live → demo fallback.
//
// Every payload exists in two places with identical shape:
//   live:  /api/<name>        (Netlify function → Supabase meta lookup)
//   demo:  /data/<name>.json  (static artifacts bundled with the build)
// The first successful /api/meta marks the session "live"; any failure
// (no Supabase configured, local vite dev, offline) flips to demo and all
// subsequent reads go straight to the static files.

let mode = null; // "live" | "demo"

const DEMO_PATHS = {
  meta: "/data/meta.json",
  trending: "/data/trending.json",
  topics: "/data/topics.json",
  graph: "/data/graph.json",
  alerts: "/data/alerts.json",
  brief: "/data/brief.json",
};

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

export async function resolveMode() {
  if (mode) return mode;
  try {
    const res = await fetch("/api/meta");
    if (res.ok) {
      mode = "live";
      return mode;
    }
  } catch { /* fall through */ }
  mode = "demo";
  return mode;
}

export async function getData(name) {
  const m = await resolveMode();
  if (m === "live") {
    try {
      return await fetchJson(`/api/${name}`);
    } catch {
      mode = "demo"; // live flaked mid-session — degrade gracefully
    }
  }
  return fetchJson(DEMO_PATHS[name] || `/data/${name}.json`);
}

export async function getTicker(symbol) {
  const m = await resolveMode();
  if (m === "live") {
    try {
      return await fetchJson(`/api/ticker?symbol=${encodeURIComponent(symbol)}`);
    } catch { /* fall back */ }
  }
  return fetchJson(`/data/tickers/${encodeURIComponent(symbol)}.json`);
}

export function currentMode() {
  return mode;
}
