import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { clockTime, ms } from "../lib/format.js";
import { ease } from "./ui.jsx";

function scale(points, width, height, pad) {
  const values = points.map((p) => p.response_time_ms).filter((v) => v != null);
  const max = Math.max(...values, 1);
  const min = 0;
  const step = points.length > 1 ? (width - pad * 2) / (points.length - 1) : 0;
  const y = (v) => height - pad - ((v - min) / (max - min || 1)) * (height - pad * 2);
  return { step, y, max };
}

/** Line path that breaks where a check failed (no response time). */
function linePath(points, step, y, pad) {
  let d = "";
  let pen = false;
  points.forEach((p, i) => {
    if (p.response_time_ms == null) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${(pad + i * step).toFixed(1)},${y(p.response_time_ms).toFixed(1)} `;
    pen = true;
  });
  return d.trim();
}

/** Tiny response-time trend. Failed checks are red ticks along the bottom. */
export function Sparkline({ points = [], width = 120, height = 32 }) {
  const pad = 3;
  const { step, y } = scale(points, width, height, pad);
  const d = linePath(points, step, y, pad);
  if (!points.length) return <svg width={width} height={height} className="spark spark-empty" aria-hidden="true" />;
  return (
    <svg width={width} height={height} className="spark" aria-hidden="true" viewBox={`0 0 ${width} ${height}`}>
      {d && (
        <motion.path
          d={d}
          fill="none"
          className="spark-line"
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: 0.9, ease }}
        />
      )}
      {points.map((p, i) =>
        p.status === "DOWN" ? (
          <rect key={i} x={pad + i * step - 1.5} y={height - 6} width={3} height={6} rx={1} className="spark-fail" />
        ) : null,
      )}
    </svg>
  );
}

/** Response-time chart with hover read-out, for the target drawer. */
export function ResponseChart({ points = [], height = 160 }) {
  const width = 560;
  const pad = 12;
  const [hover, setHover] = useState(null);
  const { step, y, max } = useMemo(() => scale(points, width, height, pad), [points, height]);
  const line = useMemo(() => linePath(points, step, y, pad), [points, step, y]);

  if (points.length < 2) return <div className="chart-empty">Not enough checks yet for a chart.</div>;

  const area = line
    .split(/(?=M)/)
    .map((seg) => {
      const coords = seg.trim().slice(1).split(/\s*L/);
      const first = coords[0].split(",")[0];
      const last = coords[coords.length - 1].split(",")[0];
      return `${seg.trim()} L${last},${height - pad} L${first},${height - pad} Z`;
    })
    .join(" ");

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * width;
    setHover(Math.max(0, Math.min(points.length - 1, Math.round((x - pad) / (step || 1)))));
  };
  const h = hover != null ? points[hover] : null;

  return (
    <div className="chart">
      <div className="chart-meta">
        <span>Peak {ms(max)}</span>
        {h ? (
          <span className={h.status === "DOWN" ? "text-danger" : ""}>
            {clockTime(h.checked_at)} · {h.status === "DOWN" ? h.error ?? "Down" : ms(h.response_time_ms)}
          </span>
        ) : (
          <span className="muted">Hover for details</span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="chart-svg"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="Response time over the latest checks"
      >
        <defs>
          <linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={pad} x2={width - pad} y1={pad + f * (height - pad * 2)} y2={pad + f * (height - pad * 2)} className="chart-grid" />
        ))}
        <motion.path d={area} fill="url(#chart-fill)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }} />
        <motion.path
          d={line}
          fill="none"
          className="chart-line"
          vectorEffect="non-scaling-stroke"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 1, ease }}
        />
        {points.map((p, i) =>
          p.status === "DOWN" ? (
            <rect key={i} x={pad + i * step - 2} y={height - pad - 10} width={4} height={10} rx={1.5} className="spark-fail" />
          ) : null,
        )}
        {h && (
          <>
            <line x1={pad + hover * step} x2={pad + hover * step} y1={pad} y2={height - pad} className="chart-cursor" vectorEffect="non-scaling-stroke" />
            {h.response_time_ms != null && <circle cx={pad + hover * step} cy={y(h.response_time_ms)} r={4} className="chart-dot" />}
          </>
        )}
      </svg>
    </div>
  );
}

/** Up/down strip, one bar per check, like a status page. */
export function UptimeBars({ points = [], slots = 30 }) {
  const padded = [...Array(Math.max(0, slots - points.length)).fill(null), ...points.slice(-slots)];
  return (
    <div className="uptime-bars" aria-hidden="true">
      {padded.map((p, i) => (
        <motion.span
          key={i}
          className={`uptime-bar ${p ? (p.status === "UP" ? "up" : "down") : "none"}`}
          initial={{ scaleY: 0.3, opacity: 0 }}
          animate={{ scaleY: 1, opacity: 1 }}
          transition={{ delay: i * 0.012, duration: 0.3, ease }}
          title={p ? `${clockTime(p.checked_at)} · ${p.status}` : "No check"}
        />
      ))}
    </div>
  );
}
