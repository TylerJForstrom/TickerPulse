import React, { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Route, Routes, Link } from "react-router-dom";
import { getData, currentMode } from "./api.js";
import Leaderboard from "./pages/Leaderboard.jsx";
import TickerDetail from "./pages/TickerDetail.jsx";
import Topics from "./pages/Topics.jsx";
import Brief from "./pages/Brief.jsx";

const MetaContext = createContext(null);
export const useMeta = () => useContext(MetaContext);

function timeAgo(iso) {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

function Logo() {
  return (
    <Link to="/" className="logo">
      <svg width="26" height="26" viewBox="0 0 32 32">
        <rect width="32" height="32" rx="7" fill="#11182a" />
        <path d="M5 21 L11 13 L15 17 L21 8 L27 12" stroke="#4ade80" strokeWidth="2.6"
          fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="21" cy="8" r="2.4" fill="#4ade80" />
      </svg>
      Ticker<span className="pulse">Pulse</span>
    </Link>
  );
}

export default function App() {
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    getData("meta").then(setMeta).catch(() => setMeta({ mode: "demo", error: true }));
  }, []);

  const mode = meta?.mode || currentMode() || "demo";
  const isDemo = mode !== "live";

  return (
    <MetaContext.Provider value={meta}>
      <div className="shell">
        <header className="topbar">
          <Logo />
          <nav className="nav">
            <NavLink to="/" end>Trending</NavLink>
            <NavLink to="/topics">Topic Map</NavLink>
            <NavLink to="/brief">Brief</NavLink>
          </nav>
          <div className="topbar-right">
            <div className="refresh-pill" title={meta?.updated_at || ""}>
              <span className={`refresh-dot${isDemo ? " demo" : ""}`} />
              {isDemo
                ? `demo snapshot · ${timeAgo(meta?.updated_at)}`
                : `near-live · updated ${timeAgo(meta?.updated_at)} · every ${meta?.refresh_minutes ?? 15} min`}
            </div>
          </div>
        </header>

        <Routes>
          <Route path="/" element={<Leaderboard />} />
          <Route path="/ticker/:symbol" element={<TickerDetail />} />
          <Route path="/topics" element={<Topics />} />
          <Route path="/brief" element={<Brief />} />
        </Routes>

        <footer className="footer">
          <span className="disclaimer">⚠ Not financial advice. TickerPulse aggregates public social chatter for research and entertainment.</span>
          <span>
            Sources: {meta?.sources?.length ? meta.sources.join(", ") : "bundled sample dataset"} ·
            sentiment: {meta?.sentiment_backend || "—"}
          </span>
          <span style={{ marginLeft: "auto" }}>
            <a href="https://github.com/TylerJForstrom/TickerPulse" target="_blank" rel="noopener noreferrer">GitHub →</a>
          </span>
        </footer>
      </div>
    </MetaContext.Provider>
  );
}
