// Shared read-only Supabase access for all API functions.
//
// The worker precomputes every payload and stores it in the `meta` table
// keyed by name (trending, graph, ticker:NVDA, …), so the read API is a
// single indexed lookup — fast, cheap, and impossible to abuse for writes.
// Without Supabase env vars the API answers 503 and the frontend falls
// back to the bundled static demo artifacts under /data/.

const SUPABASE_URL = process.env.SUPABASE_URL;
const SUPABASE_KEY = process.env.SUPABASE_ANON_KEY;

export const liveConfigured = Boolean(SUPABASE_URL && SUPABASE_KEY);

export async function metaValue(key) {
  if (!liveConfigured) return null;
  const url = `${SUPABASE_URL}/rest/v1/meta?key=eq.${encodeURIComponent(key)}&select=value`;
  const res = await fetch(url, {
    headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` },
  });
  if (!res.ok) return null;
  const rows = await res.json();
  return rows.length ? rows[0].value : null;
}

export function json(payload, status = 200, maxAge = 120) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": `public, max-age=${maxAge}`,
      "Access-Control-Allow-Origin": "*",
    },
  });
}

export async function serveMeta(key) {
  if (!liveConfigured) {
    return json({ error: "live mode not configured", demo: true }, 503, 60);
  }
  const value = await metaValue(key);
  if (value === null) return json({ error: `no data for ${key}` }, 404, 30);
  return json(value);
}
