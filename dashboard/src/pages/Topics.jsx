import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getData } from "../api.js";
import { Loading, Sparkline } from "../components/bits.jsx";

const PALETTE = [
  "#60a5fa", "#4ade80", "#f87171", "#fbbf24", "#c084fc", "#34d399",
  "#fb923c", "#38bdf8", "#f472b6", "#a3e635", "#facc15", "#818cf8",
];
const topicColor = (id) => (id === -1 ? "rgba(120,134,160,0.35)" : PALETTE[id % PALETTE.length]);

function ScatterMap({ points, topics, activeTopic, setActiveTopic }) {
  const [tip, setTip] = useState(null);
  const W = 860, H = 560, PAD = 24;

  const shown = useMemo(
    () => (activeTopic == null ? points : points.filter((p) => p.topic_id === activeTopic)),
    [points, activeTopic]
  );

  return (
    <div className="scatter-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", display: "block" }}
        onMouseLeave={() => setTip(null)}>
        <rect width={W} height={H} fill="transparent" onClick={() => setActiveTopic(null)} />
        {shown.map((p, i) => {
          const r = 2.2 + Math.min(6, Math.sqrt(p.engagement + 1) * 0.55);
          return (
            <circle
              key={p.post_id || i}
              cx={PAD + p.x * (W - 2 * PAD)}
              cy={PAD + p.y * (H - 2 * PAD)}
              r={r}
              fill={topicColor(p.topic_id)}
              opacity={p.topic_id === -1 ? 0.4 : 0.78}
              stroke={p.topic_id === -1 ? "none" : "rgba(11,15,26,0.6)"}
              strokeWidth="0.5"
              style={{ cursor: "pointer" }}
              onMouseEnter={(e) => {
                const rect = e.currentTarget.ownerSVGElement.getBoundingClientRect();
                setTip({
                  x: ((PAD + p.x * (W - 2 * PAD)) / W) * rect.width,
                  y: ((PAD + p.y * (H - 2 * PAD)) / H) * rect.height,
                  p,
                });
              }}
            />
          );
        })}
      </svg>
      {tip && (
        <div className="scatter-tip" style={{
          left: Math.min(tip.x + 14, 600), top: tip.y + 10,
        }}>
          <div style={{ color: topicColor(tip.p.topic_id), fontWeight: 700, fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5 }}>
            {tip.p.topic_id === -1 ? "unclustered" : topics.find((t) => t.id === tip.p.topic_id)?.label || "topic"}
          </div>
          <div style={{ margin: "4px 0" }}>{tip.p.text}</div>
          <div style={{ color: "var(--text-faint)", fontSize: 11 }}>
            {tip.p.platform} · ▲{tip.p.engagement}
            {tip.p.tickers?.length ? ` · ${tip.p.tickers.map((t) => "$" + t).join(" ")}` : ""}
          </div>
        </div>
      )}
    </div>
  );
}

function ForceGraph({ graph }) {
  const ref = useRef(null);
  const [sim, setSim] = useState(null);
  const nav = useNavigate();
  const W = 860, H = 540;

  const SECTOR_COLORS = {
    Technology: "#60a5fa", Semiconductors: "#818cf8", Crypto: "#fbbf24",
    Financials: "#34d399", Fintech: "#4ade80", Consumer: "#f472b6",
    Automotive: "#fb923c", Energy: "#facc15", Healthcare: "#f87171",
    Industrials: "#94a3b8", Communication: "#c084fc", "Index/ETF": "#38bdf8",
    Commodities: "#a3e635", Other: "#7886a0",
  };

  useEffect(() => {
    if (!graph?.nodes?.length) return;
    let cancelled = false;
    import("d3-force").then((d3) => {
      if (cancelled) return;
      const nodes = graph.nodes.map((n) => ({ ...n }));
      const links = graph.edges.map((e) => ({ ...e }));
      const simulation = d3
        .forceSimulation(nodes)
        .force("link", d3.forceLink(links).id((d) => d.id).distance(90).strength((l) => Math.min(1, l.weight / 8)))
        .force("charge", d3.forceManyBody().strength(-180))
        .force("center", d3.forceCenter(W / 2, H / 2))
        .force("collide", d3.forceCollide().radius((d) => 14 + Math.sqrt(d.mentions) * 1.3))
        .stop();
      simulation.tick(220);
      nodes.forEach((n) => {
        n.x = Math.max(30, Math.min(W - 30, n.x));
        n.y = Math.max(24, Math.min(H - 24, n.y));
      });
      setSim({ nodes, links });
    });
    return () => { cancelled = true; };
  }, [graph]);

  if (!sim) return <Loading label="laying out graph" />;

  return (
    <svg ref={ref} viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", display: "block" }}>
      {sim.links.map((l, i) => (
        <line key={i} x1={l.source.x} y1={l.source.y} x2={l.target.x} y2={l.target.y}
          stroke="rgba(96,165,250,0.22)" strokeWidth={Math.min(5, 0.7 + l.weight * 0.35)} />
      ))}
      {sim.nodes.map((n) => {
        const r = 7 + Math.sqrt(n.mentions) * 1.15;
        return (
          <g key={n.id} style={{ cursor: "pointer" }} onClick={() => nav(`/ticker/${n.id}`)}>
            <circle cx={n.x} cy={n.y} r={r}
              fill={SECTOR_COLORS[n.sector] || SECTOR_COLORS.Other} opacity="0.85"
              stroke="rgba(11,15,26,0.8)" strokeWidth="1.5">
              <title>{`$${n.id} ${n.name} — ${n.mentions} mentions (${n.sector})`}</title>
            </circle>
            <text x={n.x} y={n.y - r - 5} textAnchor="middle" fill="#cbd5e1"
              fontSize="11" fontWeight="700" fontFamily="JetBrains Mono, monospace">
              {n.id}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function Topics() {
  const [data, setData] = useState(null);
  const [graph, setGraph] = useState(null);
  const [activeTopic, setActiveTopic] = useState(null);

  useEffect(() => {
    getData("topics").then(setData).catch(console.error);
    getData("graph").then(setGraph).catch(console.error);
  }, []);

  if (!data) return <Loading label="loading topic landscape" />;
  const topics = [...(data.topics || [])].sort((a, b) => b.size - a.size);

  return (
    <>
      <div className="card">
        <h2>Topic landscape</h2>
        <p className="sub">
          every post embedded and projected to 2-D — nearby points talk about similar things ·
          color = topic cluster · size = engagement · hover to read, click a topic to isolate it
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 280px", gap: 18 }}>
          <ScatterMap points={data.points || []} topics={topics}
            activeTopic={activeTopic} setActiveTopic={setActiveTopic} />
          <div className="topic-legend">
            {topics.map((t) => (
              <div key={t.id}
                className={`topic-row${activeTopic === t.id ? " on" : ""}`}
                onClick={() => setActiveTopic(activeTopic === t.id ? null : t.id)}>
                <span className="swatch" style={{ background: topicColor(t.id) }} />
                <span className="lbl" title={t.terms?.join(", ")}>{t.label}</span>
                {t.trend === "rising" && <span title="rising over the last 3 days" style={{ color: "var(--bull)", fontSize: 11 }}>▲</span>}
                {t.trend === "cooling" && <span title="cooling over the last 3 days" style={{ color: "var(--bear)", fontSize: 11 }}>▼</span>}
                {t.series && <Sparkline data={t.series} width={54} height={18} color={topicColor(t.id)} />}
                <span className="n">{t.size}</span>
              </div>
            ))}
            {activeTopic != null && (() => {
              const t = topics.find((x) => x.id === activeTopic);
              if (!t) return null;
              return (
                <div style={{ padding: "10px 12px", fontSize: 12, color: "var(--text-dim)", borderTop: "1px solid var(--border)", marginTop: 6 }}>
                  <div><b style={{ color: "var(--text)" }}>{t.label}</b></div>
                  <div style={{ margin: "4px 0" }}>terms: {t.terms?.join(", ")}</div>
                  <div>sentiment {t.sentiment_avg > 0 ? "+" : ""}{t.sentiment_avg?.toFixed(2)}</div>
                  <div style={{ marginTop: 4 }}>
                    {t.tickers?.slice(0, 4).map((x) => (
                      <span key={x.ticker} className="chip" style={{ marginRight: 4 }}>${x.ticker} {x.count}</span>
                    ))}
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Ticker relationship graph</h2>
        <p className="sub">
          symbols that get mentioned together in the same posts · node size = mention volume ·
          color = sector · click a node to open its detail page
        </p>
        {graph ? <ForceGraph graph={graph} /> : <Loading label="loading graph" />}
      </div>
    </>
  );
}
