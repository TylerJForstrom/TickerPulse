import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getData } from "../api.js";
import {
  Delta, Loading, MoodGauge, PhaseBadge, PlatformChips, SentimentBar, Sparkline,
} from "../components/bits.jsx";

const COLUMNS = [
  { key: "mentions", label: "Mentions" },
  { key: "velocity", label: "Velocity" },
  { key: "breakout_score", label: "Breakout" },
  { key: "sentiment_avg", label: "Sentiment" },
  { key: "bull_bear_ratio", label: "Bull:Bear" },
  { key: "engagement_weighted_score", label: "Engagement" },
];

export default function Leaderboard() {
  const [trending, setTrending] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [sortKey, setSortKey] = useState("mentions");
  const [desc, setDesc] = useState(true);
  const [q, setQ] = useState("");
  const [phase, setPhase] = useState("all");
  const [platform, setPlatform] = useState("all");
  const [sector, setSector] = useState("all");
  const nav = useNavigate();

  useEffect(() => {
    getData("trending").then(setTrending).catch(console.error);
    getData("alerts").then((a) => setAlerts(a.alerts || [])).catch(() => {});
  }, []);

  const tickers = trending?.tickers || [];
  const sectors = useMemo(
    () => [...new Set(tickers.map((t) => t.sector).filter(Boolean))].sort(),
    [tickers]
  );
  const platforms = useMemo(
    () => [...new Set(tickers.flatMap((t) => Object.keys(t.platforms || {})))].sort(),
    [tickers]
  );

  const rows = useMemo(() => {
    let out = tickers;
    if (q) {
      const needle = q.toLowerCase();
      out = out.filter(
        (t) => t.ticker.toLowerCase().includes(needle) || (t.name || "").toLowerCase().includes(needle)
      );
    }
    if (phase !== "all") out = out.filter((t) => t.phase === phase);
    if (sector !== "all") out = out.filter((t) => t.sector === sector);
    if (platform !== "all") out = out.filter((t) => (t.platforms || {})[platform] > 0);
    return [...out].sort((a, b) => (desc ? b[sortKey] - a[sortKey] : a[sortKey] - b[sortKey]));
  }, [tickers, q, phase, sector, platform, sortKey, desc]);

  if (!trending) return <Loading label="loading trending tickers" />;
  const mood = trending.mood || {};

  return (
    <>
      <div className="mood-strip">
        <div className="mood-gauge-wrap">
          <MoodGauge index={mood.index ?? 50} />
          <div className="mood-meta">
            <div className="mood-label">{mood.label || "neutral"}</div>
            <div className="mood-sub">
              market mood across {mood.posts?.toLocaleString() || 0} scored posts ·
              last {trending.window_hours}h
            </div>
          </div>
        </div>
        <div className="mood-counts">
          <div className="mood-count"><div className="n" style={{ color: "var(--bull)" }}>{mood.bull?.toLocaleString()}</div><div className="t">bullish</div></div>
          <div className="mood-count"><div className="n" style={{ color: "var(--neutral)" }}>{mood.neutral?.toLocaleString()}</div><div className="t">neutral</div></div>
          <div className="mood-count"><div className="n" style={{ color: "var(--bear)" }}>{mood.bear?.toLocaleString()}</div><div className="t">bearish</div></div>
          <div className="mood-count"><div className="n">{tickers.length}</div><div className="t">tickers</div></div>
        </div>
      </div>

      {alerts.length > 0 && (
        <div className="alerts-bar">
          {alerts.slice(0, 8).map((a, i) => (
            <span
              key={i} className={`alert-chip ${a.kind}`} title={a.message}
              style={{ cursor: "pointer" }}
              onClick={() => nav(`/ticker/${a.ticker}`)}
            >
              ⚡ <b>${a.ticker}</b> {a.message.replace(`$${a.ticker} `, "")}
            </span>
          ))}
        </div>
      )}

      <div className="card">
        <h2>Trending tickers</h2>
        <p className="sub">what the crowd is talking about right now — click any row for the full breakdown</p>

        <div className="filters">
          <input type="text" placeholder="Search ticker or company…" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="seg">
            {["all", "emerging", "peaking", "fading", "steady"].map((p) => (
              <button key={p} className={phase === p ? "on" : ""} onClick={() => setPhase(p)}>{p}</button>
            ))}
          </div>
          <select value={platform} onChange={(e) => setPlatform(e.target.value)}>
            <option value="all">all platforms</option>
            {platforms.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <select value={sector} onChange={(e) => setSector(e.target.value)}>
            <option value="all">all sectors</option>
            {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <span className="count">{rows.length} tickers</span>
        </div>

        <div className="table-wrap">
          <table className="lb">
            <thead>
              <tr>
                <th>#</th>
                <th>Ticker</th>
                {COLUMNS.map((c) => (
                  <th
                    key={c.key}
                    className={sortKey === c.key ? "active" : ""}
                    onClick={() => {
                      if (sortKey === c.key) setDesc(!desc);
                      else { setSortKey(c.key); setDesc(true); }
                    }}
                  >
                    {c.label} {sortKey === c.key ? (desc ? "↓" : "↑") : ""}
                  </th>
                ))}
                <th>Phase</th>
                <th>24h</th>
                <th>Platforms</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t, i) => (
                <tr key={t.ticker} onClick={() => nav(`/ticker/${t.ticker}`)}>
                  <td className="num" style={{ color: "var(--text-faint)" }}>{i + 1}</td>
                  <td>
                    <span className="sym">${t.ticker}</span>{" "}
                    <span className="name">{t.name}</span>
                  </td>
                  <td className="num">
                    {t.mentions.toLocaleString()}{" "}
                    <Delta curr={t.mentions} prev={t.mentions_prev} />
                  </td>
                  <td className="num" style={{ color: t.velocity > 0 ? "var(--bull)" : t.velocity < 0 ? "var(--bear)" : undefined }}>
                    {t.velocity > 0 ? "+" : ""}{t.velocity.toFixed(2)}/h
                  </td>
                  <td className="num">{t.breakout_score.toFixed(1)}σ</td>
                  <td><SentimentBar bull={t.bull} bear={t.bear} neutral={t.neutral} /></td>
                  <td className="num">{t.bull_bear_ratio.toFixed(1)}</td>
                  <td className="num">{Math.round(t.engagement_weighted_score).toLocaleString()}</td>
                  <td><PhaseBadge phase={t.phase} /></td>
                  <td><Sparkline data={t.sparkline} /></td>
                  <td><PlatformChips platforms={t.platforms} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
