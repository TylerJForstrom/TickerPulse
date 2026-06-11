import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getData, getTicker } from "../api.js";
import { Loading, PhaseBadge, SentimentBar } from "../components/bits.jsx";

const COLORS = { a: "#60a5fa", b: "#f472b6" };
const fmtDay = (iso) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

function joinSeries(da, db, field) {
  // Align two tickers' hourly series on timestamp; values normalized for price.
  const map = new Map();
  for (const r of da.correlation.series) map.set(r.ts, { ts: r.ts, a: r[field] });
  for (const r of db.correlation.series) {
    const row = map.get(r.ts) || { ts: r.ts };
    row.b = r[field];
    map.set(r.ts, row);
  }
  return [...map.values()].sort((x, y) => x.ts.localeCompare(y.ts));
}

function normalizePrices(rows) {
  const baseA = rows.find((r) => r.a != null)?.a;
  const baseB = rows.find((r) => r.b != null)?.b;
  return rows.map((r) => ({
    ...r,
    a: r.a != null && baseA ? ((r.a / baseA) - 1) * 100 : null,
    b: r.b != null && baseB ? ((r.b / baseB) - 1) * 100 : null,
  }));
}

function DuelChart({ title, sub, rows, symA, symB, unit }) {
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <h2>{title}</h2>
      <p className="sub">{sub}</p>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={rows.map((r) => ({ ...r, label: fmtDay(r.ts) }))}>
          <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: "#5b6b85", fontSize: 11 }} minTickGap={60} tickLine={false} axisLine={false} />
          <YAxis tick={{ fill: "#5b6b85", fontSize: 11 }} tickLine={false} axisLine={false} width={44}
            tickFormatter={(v) => unit === "%" ? `${v.toFixed(0)}%` : v} />
          <Tooltip
            contentStyle={{ background: "#0d1322", border: "1px solid rgba(148,163,184,0.28)", borderRadius: 10 }}
            formatter={(v, name) => [unit === "%" ? `${Number(v).toFixed(2)}%` : v, name]}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {unit === "%" && <ReferenceLine y={0} stroke="rgba(148,163,184,0.3)" />}
          <Line type="monotone" dataKey="a" name={`$${symA}`} stroke={COLORS.a} strokeWidth={2} dot={false} connectNulls />
          <Line type="monotone" dataKey="b" name={`$${symB}`} stroke={COLORS.b} strokeWidth={2} dot={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function StatDuel({ ta, tb }) {
  const rows = [
    ["Mentions", (t) => t.mentions.toLocaleString()],
    ["Velocity", (t) => `${t.velocity > 0 ? "+" : ""}${t.velocity.toFixed(2)}/h`],
    ["Breakout", (t) => `${t.breakout_score.toFixed(1)}σ`],
    ["Bull:Bear", (t) => t.bull_bear_ratio.toFixed(1)],
    ["Share of voice", (t) => `${(t.share_of_voice * 100).toFixed(1)}%`],
    ["Engagement", (t) => Math.round(t.engagement_weighted_score).toLocaleString()],
  ];
  return (
    <div className="grid cols-2" style={{ marginTop: 16 }}>
      {[ta, tb].map((t, i) => (
        <div className="card" key={t.ticker}>
          <h2 style={{ color: i === 0 ? COLORS.a : COLORS.b }}>${t.ticker} <span style={{ color: "var(--text-faint)", fontWeight: 500, fontSize: 13 }}>{t.name}</span> <PhaseBadge phase={t.phase} /></h2>
          <table style={{ width: "100%", fontSize: 13.5, marginTop: 8 }}>
            <tbody>
              {rows.map(([label, fn]) => (
                <tr key={label}>
                  <td style={{ color: "var(--text-faint)", padding: "4px 0" }}>{label}</td>
                  <td className="num" style={{ textAlign: "right", fontFamily: "var(--mono)" }}>{fn(t)}</td>
                </tr>
              ))}
              <tr>
                <td style={{ color: "var(--text-faint)", padding: "4px 0" }}>Sentiment mix</td>
                <td style={{ textAlign: "right" }}><SentimentBar bull={t.bull} bear={t.bear} neutral={t.neutral} /></td>
              </tr>
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

export default function Compare() {
  const [params, setParams] = useSearchParams();
  const [options, setOptions] = useState([]);
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  const symA = (params.get("a") || "").toUpperCase();
  const symB = (params.get("b") || "").toUpperCase();

  useEffect(() => {
    getData("trending").then((t) => {
      const ticks = t.tickers.map((x) => x.ticker);
      setOptions(ticks);
      // Default matchup: the two most-mentioned tickers.
      if (!symA && ticks[0]) params.set("a", ticks[0]);
      if (!symB && ticks[1]) params.set("b", ticks[1]);
      if (!symA || !symB) setParams(params, { replace: true });
    }).catch(console.error);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!symA || !symB) return;
    setData(null);
    setErr(null);
    Promise.all([getTicker(symA), getTicker(symB)])
      .then(([a, b]) => setData({ a, b }))
      .catch((e) => setErr(String(e)));
  }, [symA, symB]);

  const mentionRows = useMemo(() => data ? joinSeries(data.a, data.b, "mentions") : [], [data]);
  const priceRows = useMemo(() => data ? normalizePrices(joinSeries(data.a, data.b, "close")) : [], [data]);

  const pick = (key) => (e) => {
    params.set(key, e.target.value);
    setParams(params, { replace: true });
  };

  return (
    <>
      <div className="card">
        <h2>Head to head</h2>
        <p className="sub">pit two tickers' chatter against each other — and against their real price moves</p>
        <div className="filters">
          <select value={symA} onChange={pick("a")} style={{ borderColor: COLORS.a }}>
            {options.map((o) => <option key={o} value={o}>${o}</option>)}
          </select>
          <span style={{ color: "var(--text-faint)", fontWeight: 700 }}>vs</span>
          <select value={symB} onChange={pick("b")} style={{ borderColor: COLORS.b }}>
            {options.map((o) => <option key={o} value={o}>${o}</option>)}
          </select>
        </div>
        {err && <p className="sub">One of those tickers has no snapshot data — pick another.</p>}
      </div>

      {!data && !err && <Loading label={`loading $${symA} vs $${symB}`} />}

      {data && (
        <>
          <StatDuel ta={data.a.trend} tb={data.b.trend} />
          <DuelChart
            title="Mentions per hour"
            sub="who owns the conversation, hour by hour"
            rows={mentionRows} symA={symA} symB={symB} unit=""
          />
          <DuelChart
            title="Price, % change"
            sub="both tickers rebased to 0% at the start of the window — chatter on the chart above, tape down here"
            rows={priceRows} symA={symA} symB={symB} unit="%"
          />
        </>
      )}
    </>
  );
}
