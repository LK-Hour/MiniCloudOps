import { useEffect, useMemo, useRef, useState } from "react";
import { Segmented } from "./ui.jsx";

export const RANGES = [
  { value: 15, label: "15m" },
  { value: 60, label: "1h" },
  { value: 360, label: "6h" },
  { value: 1440, label: "24h" },
];

export const RangeSelect = ({ value, onChange }) => <Segmented size="sm" options={RANGES} value={value} onChange={onChange} />;

export const SERIES_COLORS = ["var(--accent)", "var(--info)", "var(--warning)", "var(--violet)", "var(--danger)", "var(--success-ink)"];

const pad = { top: 10, right: 12, bottom: 22, left: 44 };

function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return ([1, 2, 2.5, 5, 10].find((m) => m * p >= v) ?? 10) * p;
}

function clock(t, spanMs) {
  const d = new Date(t);
  return spanMs > 36 * 3600_000
    ? d.toLocaleDateString([], { month: "short", day: "numeric" })
    : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Width of the element, kept up to date, so SVG text stays crisp instead of being stretched. */
function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    if (!ref.current) return undefined;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))));
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/**
 * Multi-series line chart over time.
 *   series  [{ key, label, color?, area?, points: [{t (ms), v (number | null)}] }]  null breaks the line
 *   format  value -> text (axis and tooltip)
 *   max     fixed top of the y axis (e.g. 100 for percentages); otherwise rounded up from the data
 *   marks   [{t, label?}] vertical markers, e.g. failed checks
 *   thresholds [{value, label}] dashed horizontal lines
 *   domain  [startMs, endMs]; default is the data's extent
 */
export function TimeSeriesChart({ series, format = (v) => String(Math.round(v)), max, marks = [], thresholds = [], domain, height = 200, empty = "No data in this range yet." }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState(null);
  const colored = series.map((s, i) => ({ ...s, color: s.color ?? SERIES_COLORS[i % SERIES_COLORS.length] }));

  const model = useMemo(() => {
    const all = colored.flatMap((s) => s.points.filter((p) => p.v != null));
    if (!all.length) return null;
    const t0 = domain?.[0] ?? Math.min(...all.map((p) => p.t));
    const t1 = Math.max(domain?.[1] ?? Math.max(...all.map((p) => p.t)), t0 + 1);
    const top = max ?? niceMax(Math.max(...all.map((p) => p.v), ...thresholds.map((th) => th.value)) * 1.05);
    return { t0, t1, top };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series, domain, max, thresholds]);

  if (!model) return <div className="chart-empty" ref={ref}>{empty}</div>;

  const { t0, t1, top } = model;
  const w = width - pad.left - pad.right;
  const h = height - pad.top - pad.bottom;
  const x = (t) => pad.left + ((t - t0) / (t1 - t0)) * w;
  const y = (v) => pad.top + h - (Math.min(v, top) / top) * h;

  const path = (points) => {
    let d = "";
    let pen = false;
    for (const p of points) {
      if (p.v == null) pen = false;
      else {
        d += `${pen ? "L" : "M"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)} `;
        pen = true;
      }
    }
    return d.trim();
  };
  const area = (points) =>
    path(points)
      .split(/(?=M)/)
      .map((seg) => {
        const xs = [...seg.matchAll(/[ML]([\d.]+),/g)].map((m) => m[1]);
        return `${seg.trim()} L${xs.at(-1)},${pad.top + h} L${xs[0]},${pad.top + h} Z`;
      })
      .join(" ");

  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * top);
  const tickCount = Math.max(2, Math.min(6, Math.floor(w / 110)));
  const xTicks = Array.from({ length: tickCount }, (_, i) => t0 + ((t1 - t0) * i) / (tickCount - 1));

  const times = [...new Set(colored.flatMap((s) => s.points.map((p) => p.t)))].sort((a, b) => a - b);
  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const t = t0 + ((e.clientX - rect.left - pad.left) / w) * (t1 - t0);
    let best = times[0];
    for (const c of times) if (Math.abs(c - t) < Math.abs(best - t)) best = c;
    setHover(best);
  };
  const rows = hover == null ? [] : colored.map((s) => ({ s, p: s.points.find((p) => p.t === hover) })).filter((r) => r.p?.v != null);
  const flip = hover != null && x(hover) > width * 0.6;

  return (
    <div className="ts" ref={ref}>
      <svg width={width} height={height} className="ts-svg" onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img" aria-label={colored.map((s) => s.label).join(", ")}>
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={pad.left} x2={width - pad.right} y1={y(v)} y2={y(v)} className="chart-grid" />
            <text x={pad.left - 8} y={y(v) + 4} textAnchor="end" className="ts-tick">{format(v)}</text>
          </g>
        ))}
        {xTicks.map((t, i) => (
          <text key={i} x={x(t)} y={height - 5} textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"} className="ts-tick">
            {clock(t, t1 - t0)}
          </text>
        ))}
        {thresholds.map((th) => (
          <g key={th.label}>
            <line x1={pad.left} x2={width - pad.right} y1={y(th.value)} y2={y(th.value)} className="ts-threshold" />
            <text x={width - pad.right - 4} y={y(th.value) - 4} textAnchor="end" className="ts-tick ts-tick-warn">{th.label}</text>
          </g>
        ))}
        {marks.map((m, i) => (
          <rect key={i} x={x(m.t) - 1.5} y={pad.top + h - 8} width={3} height={8} rx={1} className="spark-fail" />
        ))}
        {colored.map((s, i) => (
          <g key={s.key} style={{ color: s.color }}>
            {s.area && (
              <>
                <defs>
                  <linearGradient id={`ts-fill-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="currentColor" stopOpacity="0.22" />
                    <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
                  </linearGradient>
                </defs>
                <path d={area(s.points)} fill={`url(#ts-fill-${s.key})`} />
              </>
            )}
            <path d={path(s.points)} fill="none" className="ts-line" stroke="currentColor" />
            {s.points.filter((p) => p.v != null).length === 1 && (
              <circle cx={x(s.points.find((p) => p.v != null).t)} cy={y(s.points.find((p) => p.v != null).v)} r={3} fill="currentColor" />
            )}
            {hover != null && rows.some((r) => r.s.key === s.key) && (
              <circle cx={x(hover)} cy={y(rows.find((r) => r.s.key === s.key).p.v)} r={4} className="ts-dot" stroke="currentColor" />
            )}
          </g>
        ))}
        {hover != null && <line x1={x(hover)} x2={x(hover)} y1={pad.top} y2={pad.top + h} className="chart-cursor" />}
      </svg>
      {hover != null && rows.length > 0 && (
        <div className="ts-tip" style={{ left: x(hover), [flip ? "right" : "left"]: undefined, transform: `translateX(${flip ? "calc(-100% - 12px)" : "12px"})` }}>
          <strong>{new Date(hover).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: t1 - t0 < 3600_000 ? "2-digit" : undefined })}</strong>
          {rows.map(({ s, p }) => (
            <span key={s.key} className="ts-tip-row">
              <i style={{ background: s.color }} />
              <span className="truncate">{s.label}</span>
              <b className="num">{format(p.v)}</b>
            </span>
          ))}
        </div>
      )}
      {colored.length > 1 && (
        <div className="ts-legend">
          {colored.map((s) => (
            <span key={s.key}>
              <i style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Small label + number for the row above a chart. */
export function Stat({ label, value, tone }) {
  return (
    <div className={`ts-stat ${tone ? `ts-stat-${tone}` : ""}`}>
      <span className="muted small">{label}</span>
      <strong className="num">{value}</strong>
    </div>
  );
}
