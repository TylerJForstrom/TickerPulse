import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Bar, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis, Area, AreaChart, BarChart,
} from "recharts";
import { getTicker } from "../api.js";
import {
  Delta, Loading, MoodGauge, PhaseBadge, PlatformChips, SENT_COLOR, SentimentBar,
} from "../components/bits.jsx";

const fmtHour = (iso) =>
  new Date(iso).toLocaleString(undefined, { weekday: "short", hour: "numeric" });
const fmtDay = (iso) =>
  new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export default function TickerDetail() {
  const { symbol } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    setData(null);
    setErr(null);
    getTicker(symbol).then(setData).catch((e) => setErr(String(e)));
  }, [symbol]);

  const series = useMemo(() => {
    if (!data?.correlation?.series) return [];
    return data.correlation.series.map((r) => ({
      ...r,
      label: fmtHour(r.ts),
      day: fmtDay(r.ts),
      sentiment: r.sentiment_avg,
    }));
  }, [data]);

  const lagData = useMemo(() => {
    const byLag = data?.correlation?.by_lag || {};
    return Object.entries(byLag)
      .map(([lag, r]) => ({ lag: Number(lag), r }))
      .sort((a, b) => a.lag - b.lag);
  }, [data]);

  if (err) {
    return (
      <div className="card">
        <h2>No data for ${symbol}</h2>
        <p className="sub">This ticker isn't in the current snapshot's top set.</p>
        <Link className="backlink" to="/">← back to trending</Link>
      </div>
    );
  }
  if (!data) return <Loading label={`loading $${symbol}`} />;

  const t = data.trend;
  const corr = data.correlation;
  const gaugeIndex = ((t.sentiment_avg + 1) / 2) * 100;

  return (
    <>
      <Link className="backlink" to="/">← trending</Link>
      <div className="detail-head">
        <h1>${t.ticker}</h1>
        <span className="full">{t.name} · {t.sector}</span>
        <PhaseBadge phase={t.phase} />
      </div>

      <div className="grid cols-4" style={{ marginBottom: 16 }}>
        <div className="card stat">
          <div className="label">Mentions · {t.window_hours}h</div>
          <div className="value">{t.mentions.toLocaleString()}</div>
          <div className="hint"><Delta curr={t.mentions} prev={t.mentions_prev} /> vs prior window</div>
        </div>
        <div className="card stat">
          <div className="label">Velocity</div>
          <div className="value" style={{ color: t.velocity > 0 ? "var(--bull)" : "var(--bear)" }}>
            {t.velocity > 0 ? "+" : ""}{t.velocity.toFixed(2)}/h
          </div>
          <div className="hint">breakout {t.breakout_score.toFixed(1)}σ above baseline</div>
        </div>
        <div className="card stat">
          <div className="label">Bull : Bear</div>
          <div className="value">{t.bull_bear_ratio.toFixed(1)}</div>
          <div className="hint" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <SentimentBar bull={t.bull} bear={t.bear} neutral={t.neutral} />
          </div>
        </div>
        <div className="card stat">
          <div className="label">Share of voice</div>
          <div className="value">{(t.share_of_voice * 100).toFixed(1)}%</div>
          <div className="hint">engagement score {Math.round(t.engagement_weighted_score)}</div>
        </div>
      </div>

      <div className="card">
        <h2>Chatter vs price — the buzz-vs-move overlay</h2>
        <p className="sub">
          hourly social mentions (bars, colored by sentiment) against the real {t.ticker} price (line) · trailing 7 days
        </p>
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
            <XAxis dataKey="day" tick={{ fill: "#5b6b85", fontSize: 11 }} minTickGap={60} tickLine={false} axisLine={false} />
            <YAxis yAxisId="m" tick={{ fill: "#5b6b85", fontSize: 11 }} tickLine={false} axisLine={false} width={36} />
            <YAxis yAxisId="p" orientation="right" domain={["auto", "auto"]}
              tick={{ fill: "#5b6b85", fontSize: 11 }} tickLine={false} axisLine={false} width={56}
              tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(0)} />
            <Tooltip
              contentStyle={{ background: "#0d1322", border: "1px solid rgba(148,163,184,0.28)", borderRadius: 10 }}
              labelFormatter={(_, payload) => payload?.[0] ? fmtHour(payload[0].payload.ts) : ""}
              formatter={(value, name) => {
                if (name === "mentions") return [value, "mentions"];
                if (name === "close") return [Number(value).toLocaleString(), "price"];
                return [value, name];
              }}
            />
            <Bar yAxisId="m" dataKey="mentions" name="mentions" barSize={3} radius={[2, 2, 0, 0]}>
              {series.map((r, i) => (
                <Cell key={i} fill={
                  r.sentiment == null ? "rgba(148,163,184,0.45)"
                    : r.sentiment > 0.1 ? "rgba(74,222,128,0.75)"
                    : r.sentiment < -0.1 ? "rgba(248,113,113,0.75)"
                    : "rgba(148,163,184,0.55)"
                } />
              ))}
            </Bar>
            <Line yAxisId="p" type="monotone" dataKey="close" name="close" dot={false}
              stroke="#60a5fa" strokeWidth={2} />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="readout" style={{ marginTop: 12 }}>
          📊 {corr.readout}
          {Math.abs(corr.best_lag_r) >= 0.15 && (
            <span style={{ color: "var(--text-dim)" }}>
              {" "}Peak correlation r={corr.best_lag_r.toFixed(2)} at {corr.best_lag_hours > 0 ? "+" : ""}{corr.best_lag_hours}h lag.
            </span>
          )}
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Crowd sentiment gauge</h2>
          <p className="sub">average FinBERT-style score across the last {t.window_hours}h</p>
          <div className="gauge-wrap">
            <MoodGauge index={gaugeIndex} size={170} />
            <div style={{ marginTop: 6, fontFamily: "var(--mono)", fontSize: 15, fontWeight: 700, color: t.sentiment_avg > 0.1 ? "var(--bull)" : t.sentiment_avg < -0.1 ? "var(--bear)" : "var(--neutral)" }}>
              {t.sentiment_avg > 0 ? "+" : ""}{t.sentiment_avg.toFixed(2)}
            </div>
            <div style={{ color: "var(--text-faint)", fontSize: 12 }}>
              {t.bull} bull · {t.neutral} neutral · {t.bear} bear
            </div>
          </div>
        </div>

        <div className="card">
          <h2>Lead / lag profile</h2>
          <p className="sub">correlation between mentions and |price moves| at each hour offset — bars right of zero mean buzz leads</p>
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={lagData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
              <XAxis dataKey="lag" tick={{ fill: "#5b6b85", fontSize: 11 }} tickLine={false} axisLine={false}
                label={{ value: "lag (hours, + = buzz leads)", fill: "#5b6b85", fontSize: 11, dy: 12 }} />
              <YAxis tick={{ fill: "#5b6b85", fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
              <Tooltip
                contentStyle={{ background: "#0d1322", border: "1px solid rgba(148,163,184,0.28)", borderRadius: 10 }}
                formatter={(v) => [Number(v).toFixed(3), "r"]} labelFormatter={(l) => `${l > 0 ? "+" : ""}${l}h`}
              />
              <ReferenceLine x={0} stroke="rgba(148,163,184,0.4)" />
              <Bar dataKey="r" radius={[3, 3, 0, 0]}>
                {lagData.map((d, i) => (
                  <Cell key={i} fill={d.lag === corr.best_lag_hours ? "#60a5fa" : "rgba(96,165,250,0.35)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Sentiment trajectory</h2>
          <p className="sub">hourly average sentiment, -1 (bearish) to +1 (bullish)</p>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={data.buckets.map((b) => ({ ...b, label: fmtDay(b.bucket_start) }))}>
              <CartesianGrid stroke="rgba(148,163,184,0.08)" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "#5b6b85", fontSize: 11 }} minTickGap={60} tickLine={false} axisLine={false} />
              <YAxis domain={[-1, 1]} tick={{ fill: "#5b6b85", fontSize: 11 }} tickLine={false} axisLine={false} width={36} />
              <Tooltip
                contentStyle={{ background: "#0d1322", border: "1px solid rgba(148,163,184,0.28)", borderRadius: 10 }}
                formatter={(v) => [v == null ? "—" : Number(v).toFixed(2), "sentiment"]}
              />
              <ReferenceLine y={0} stroke="rgba(148,163,184,0.3)" />
              <defs>
                <linearGradient id="sentGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4ade80" stopOpacity={0.6} />
                  <stop offset="50%" stopColor="#94a3b8" stopOpacity={0.15} />
                  <stop offset="100%" stopColor="#f87171" stopOpacity={0.6} />
                </linearGradient>
              </defs>
              <Area type="monotone" dataKey="sentiment_avg" stroke="#94a3b8" strokeWidth={1.6}
                fill="url(#sentGrad)" connectNulls />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <h2>Where the chatter lives</h2>
          <p className="sub">cross-platform diffusion — conversation origin: <b style={{ color: "var(--text)" }}>{t.origin_platform || "—"}</b></p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 14 }}>
            {Object.entries(t.platforms || {}).sort((a, b) => b[1] - a[1]).map(([p, n]) => {
              const total = Object.values(t.platforms).reduce((s, x) => s + x, 0);
              return (
                <div key={p} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span className={`chip ${p}`} style={{ width: 90, textAlign: "center" }}>{p}</span>
                  <div style={{ flex: 1, height: 9, background: "rgba(148,163,184,0.12)", borderRadius: 5, overflow: "hidden" }}>
                    <div style={{ width: `${(n / total) * 100}%`, height: "100%", background: "var(--accent)", opacity: 0.8 }} />
                  </div>
                  <span className="num" style={{ fontFamily: "var(--mono)", fontSize: 12.5, width: 70, textAlign: "right" }}>
                    {n} · {((n / total) * 100).toFixed(0)}%
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Top posts</h2>
        <p className="sub">highest-engagement chatter in the window</p>
        <div className="post-list">
          {(t.top_posts || []).map((p) => (
            <div key={p.id} className="post">
              <div className="meta">
                <span className="sent-dot" style={{ background: SENT_COLOR[p.sentiment] || "var(--neutral)" }} />
                <span className="author">@{p.author}</span>
                <span className={`chip ${p.platform}`}>{p.platform}{p.source && p.source !== p.platform ? ` · ${p.source}` : ""}</span>
                <span className="eng">▲ {p.engagement.toLocaleString()}</span>
                <span>{new Date(p.timestamp).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
              </div>
              {p.url ? <a href={p.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--text)" }}>{p.text}</a> : p.text}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
