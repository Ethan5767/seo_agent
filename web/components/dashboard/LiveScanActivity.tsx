"use client";

import React from "react";
import { formatElapsed, type ToolActivity } from "@/lib/scanActivity";

/**
 * A loading indicator for a running scan: an animated bar, what is running now,
 * and elapsed time. Shown only while the scan runs.
 *
 * The operator asked for "just a loading" over a step-by-step panel. The line
 * still names a real event (the tool the scanner reports as running, and
 * DataForSEO's own page count while Site Health crawls), never an invented
 * percentage.
 */
export function LiveScanActivity({
  tools,
  busy,
}: {
  tools: ToolActivity[] | null | undefined;
  busy?: boolean;
  phaseLine?: string;
  catalog?: unknown;
}) {
  const [now, setNow] = React.useState(() => Date.now());
  const startRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    if (!busy) {
      startRef.current = null;
      return;
    }
    startRef.current = Date.now();
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [busy]);

  if (!busy) return null;

  const list = Array.isArray(tools) ? tools : [];
  const current = [...list].reverse().find((t) => t.state === "running");
  const what = current
    ? current.crawl
      ? `${current.name}: ${current.crawl.crawled} of ${current.crawl.max} pages`
      : current.name
    : "Opening the page";

  return (
    <div className="lsl" role="status" aria-live="polite">
      <style>{CSS}</style>
      <div className="lsl-bar" aria-hidden><span /></div>
      <div className="lsl-text">
        <span>Scanning · {what}</span>
        <span className="lsl-time">{formatElapsed(now - (startRef.current ?? now))}</span>
      </div>
    </div>
  );
}

const CSS = `
.lsl{margin:0 0 14px}
.lsl-bar{height:4px;border-radius:2px;background:var(--accent-tint);overflow:hidden;position:relative}
.lsl-bar span{position:absolute;top:0;left:-40%;width:40%;height:100%;border-radius:2px;background:var(--accent);animation:lsl-slide 1.2s ease-in-out infinite}
.lsl-text{display:flex;justify-content:space-between;gap:12px;margin-top:6px;font-size:12px;color:var(--ink-muted)}
.lsl-time{font-variant-numeric:tabular-nums}
@keyframes lsl-slide{0%{left:-40%}100%{left:100%}}
@media (prefers-reduced-motion: reduce){.lsl-bar span{animation:none;left:0;width:100%;opacity:.5}}
`;
