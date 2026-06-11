import React, { useEffect, useState } from "react";
import { marked } from "marked";
import { getData } from "../api.js";
import { Loading } from "../components/bits.jsx";

export default function Brief() {
  const [brief, setBrief] = useState(null);

  useEffect(() => {
    getData("brief").then(setBrief).catch(console.error);
  }, []);

  if (!brief) return <Loading label="assembling the brief" />;

  const download = () => {
    const blob = new Blob([brief.markdown], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `tickerpulse-brief-${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="card">
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8 }} className="no-print">
        <h2 style={{ margin: 0 }}>Market chatter brief</h2>
        <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className="btn" onClick={download}>↓ Markdown</button>
          <button className="btn" onClick={() => window.print()}>⎙ Print / PDF</button>
        </span>
      </div>
      <div
        className="brief-doc"
        dangerouslySetInnerHTML={{ __html: marked.parse(brief.markdown || "") }}
      />
    </div>
  );
}
