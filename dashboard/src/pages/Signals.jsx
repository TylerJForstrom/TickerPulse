import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getData } from "../api.js";
import { Loading } from "../components/bits.jsx";

const fmtWhen = (iso) =>
  new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric" });

function Ret({ value }) {
  if (value == null) return <span style={{ color: "var(--text-faint)" }}>—</span>;
  const color = value > 0.05 ? "var(--bull)" : value < -0.05 ? "var(--bear)" : "var(--neutral)";
  return (
    <span className="num" style={{ color, fontFamily: "var(--mono)" }}>
      {value > 0 ? "+" : ""}{value.toFixed(2)}%
    </span>
  );
}

function HorizonCard({ hours, stats }) {
  const wr = stats?.win_rate;
  return (
    <div className="card stat">
      <div className="label">+{hours}h after flag</div>
      <div className="value" style={{ color: wr == null ? "var(--text-faint)" : wr >= 0.5 ? "var(--bull)" : "var(--bear)" }}>
        {wr == null ? "—" : `${Math.round(wr * 100)}%`}
      </div>
      <div className="hint">
        {stats?.n
          ? `win rate over ${stats.n} flags${stats.flat ? ` (${stats.flat} flat/closed excluded)` : ""} · avg ${stats.avg > 0 ? "+" : ""}${stats.avg}% · median ${stats.median > 0 ? "+" : ""}${stats.median}%`
          : "no scored flags yet"}
      </div>
    </div>
  );
}

export default function Signals() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const nav = useNavigate();

  useEffect(() => {
    getData("backtest").then(setData).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="card"><h2>No backtest data yet</h2><p className="sub">The next pipeline run will populate this page.</p></div>;
  if (!data) return <Loading label="replaying flag history" />;

  const { summary, events, params } = data;

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Do the flags actually work?</h2>
        <p className="sub">
          Every <span className="badge emerging">emerging</span> flag the trend engine would have
          raised over the trailing week (breakout ≥ {params.breakout_floor}σ), replayed exactly as it
          would have fired live, scored by what the price really did next. Honest numbers — fizzled
          flags count against the win rate.
        </p>
        <div className="grid cols-3">
          {params.horizons.map((h) => (
            <HorizonCard key={h} hours={h} stats={summary.horizons[String(h)]} />
          ))}
        </div>
      </div>

      <div className="card">
        <h2>Flag log</h2>
        <p className="sub">{summary.events} flags raised in the replay window · click a row for the ticker</p>
        <div className="table-wrap">
          <table className="lb">
            <thead>
              <tr>
                <th>Flagged</th>
                <th>Ticker</th>
                <th>Breakout</th>
                <th>Mentions</th>
                <th>Sentiment</th>
                {params.horizons.map((h) => <th key={h}>+{h}h</th>)}
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i} onClick={() => nav(`/ticker/${e.ticker}`)}>
                  <td style={{ color: "var(--text-dim)" }}>{fmtWhen(e.flagged_at)}</td>
                  <td><span className="sym">${e.ticker}</span> <span className="name">{e.name}</span></td>
                  <td className="num">{e.breakout_score.toFixed(1)}σ</td>
                  <td className="num">{e.mentions}</td>
                  <td className="num" style={{ color: e.sentiment_avg > 0.1 ? "var(--bull)" : e.sentiment_avg < -0.1 ? "var(--bear)" : "var(--neutral)" }}>
                    {e.sentiment_avg > 0 ? "+" : ""}{e.sentiment_avg.toFixed(2)}
                  </td>
                  {params.horizons.map((h) => (
                    <td key={h}><Ret value={e.returns?.[String(h)]} /></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="sub" style={{ marginTop: 12 }}>
          Methodology: the trend engine is re-run at 6-hour as-of steps using only posts visible at
          that moment; forward returns use the last real close at/before the flag and at each horizon.
          Past chatter ≠ future returns — this is research, not advice.
        </p>
      </div>
    </>
  );
}
