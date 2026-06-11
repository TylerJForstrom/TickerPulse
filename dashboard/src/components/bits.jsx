// Small shared display atoms: sparkline, phase badge, sentiment bar,
// platform chips, deltas, mood gauge, loading state.
import React from "react";

export function Sparkline({ data, width = 110, height = 28, color = "#60a5fa" }) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data, 1);
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * (width - 2) + 1,
    height - 2 - (v / max) * (height - 6),
  ]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${d} L${pts[pts.length - 1][0].toFixed(1)},${height} L1,${height} Z`;
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <path d={area} fill={color} opacity="0.12" />
      <path d={d} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

export function PhaseBadge({ phase }) {
  return <span className={`badge ${phase}`}>{phase}</span>;
}

export function SentimentBar({ bull, bear, neutral }) {
  const total = Math.max(1, bull + bear + neutral);
  return (
    <span className="sentbar" title={`${bull} bull / ${neutral} neutral / ${bear} bear`}>
      <span className="b" style={{ width: `${(bull / total) * 100}%` }} />
      <span className="n" style={{ width: `${(neutral / total) * 100}%` }} />
      <span className="r" style={{ width: `${(bear / total) * 100}%` }} />
    </span>
  );
}

export function PlatformChips({ platforms, max = 3 }) {
  const entries = Object.entries(platforms || {}).sort((a, b) => b[1] - a[1]).slice(0, max);
  return (
    <span className="chips">
      {entries.map(([p, n]) => (
        <span key={p} className={`chip ${p}`}>{p} {n}</span>
      ))}
    </span>
  );
}

export function Delta({ curr, prev }) {
  if (!prev) return <span className="delta-up">new</span>;
  const pct = ((curr - prev) / prev) * 100;
  if (Math.abs(pct) < 1) return <span style={{ color: "var(--text-faint)" }}>·</span>;
  return pct > 0
    ? <span className="delta-up">▲ {pct.toFixed(0)}%</span>
    : <span className="delta-down">▼ {Math.abs(pct).toFixed(0)}%</span>;
}

export function MoodGauge({ index = 50, size = 92 }) {
  // Semicircular gauge: 0 (extreme fear) → 100 (extreme greed).
  const angle = (index / 100) * 180;
  const rad = ((180 - angle) * Math.PI) / 180;
  const r = size / 2 - 8;
  const cx = size / 2, cy = size / 2 + 6;
  const nx = cx + r * 0.72 * Math.cos(rad);
  const ny = cy - r * 0.72 * Math.sin(rad);
  const arc = (from, to, color) => {
    const a1 = ((180 - from) * Math.PI) / 180, a2 = ((180 - to) * Math.PI) / 180;
    return (
      <path
        d={`M ${cx + r * Math.cos(a1)} ${cy - r * Math.sin(a1)} A ${r} ${r} 0 0 1 ${cx + r * Math.cos(a2)} ${cy - r * Math.sin(a2)}`}
        fill="none" stroke={color} strokeWidth="7" strokeLinecap="round"
      />
    );
  };
  return (
    <svg width={size} height={size / 2 + 18}>
      {arc(2, 58, "#f87171")}
      {arc(64, 116, "#94a3b8")}
      {arc(122, 178, "#4ade80")}
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="#e2e8f0" strokeWidth="2.4" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="3.6" fill="#e2e8f0" />
      <text x={cx} y={cy + 1} textAnchor="middle" dy="12" fill="#8b9bb4"
        fontSize="11" fontFamily="JetBrains Mono, monospace" fontWeight="700">
        {Math.round(index)}
      </text>
    </svg>
  );
}

export function Loading({ label = "loading data" }) {
  return (
    <div className="loading">
      <span className="spinner" /> {label}…
    </div>
  );
}

export const SENT_COLOR = { bull: "var(--bull)", bear: "var(--bear)", neutral: "var(--neutral)" };
