import { useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight, ExternalLink, Pause, Play, Search, X } from "lucide-react";
import { useLogVolume, useLogs } from "../../api/hooks.js";
import { Badge, ErrorState, Segmented, Skeleton, Switch, ease } from "../../components/ui.jsx";
import { LEVELS, RANGES, SCOPES, buildQuery } from "../../lib/logs.js";
import { Code } from "../Docs.jsx";

const SERVICE_HUE = {
  "target-service": 210,
  "monitoring-service": 265,
  "incident-service": 0,
  "notification-service": 35,
  gateway: 160,
  "demo-app": 300,
};
const hue = (s) => SERVICE_HUE[s] ?? [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
const levelTone = (l) => (/ERROR|CRIT/.test(l ?? "") ? "danger" : /WARN/.test(l ?? "") ? "warning" : "neutral");

export const grafanaExplore = (query, seconds) => {
  const left = { datasource: "loki", queries: [{ refId: "A", expr: query }], range: { from: `now-${Math.round(seconds / 60)}m`, to: "now" } };
  return `${window.location.protocol}//${window.location.hostname}:3001/explore?orgId=1&left=${encodeURIComponent(JSON.stringify(left))}`;
};

function time(ts) {
  const d = new Date(ts);
  return `${d.toLocaleTimeString([], { hour12: false })}.${String(d.getMilliseconds()).padStart(3, "0")}`;
}

/** Stacked log volume per level. */
function Volume({ data }) {
  if (!data) return <div className="volume volume-empty" />;
  const max = Math.max(1, ...data.buckets.map((b) => b.info + b.warn + b.error));
  return (
    <div className="volume" role="img" aria-label="Log volume over time">
      {data.buckets.map((b) => {
        const total = b.info + b.warn + b.error;
        return (
          <div key={b.t} className="volume-col" title={`${new Date(b.t).toLocaleTimeString()} · ${total} lines${b.error ? ` · ${b.error} errors` : ""}${b.warn ? ` · ${b.warn} warnings` : ""}`}>
            <motion.div className="volume-stack" initial={false} animate={{ height: `${(total / max) * 100}%` }} transition={{ duration: 0.4, ease }}>
              {b.error > 0 && <span className="v-error" style={{ flexGrow: b.error }} />}
              {b.warn > 0 && <span className="v-warn" style={{ flexGrow: b.warn }} />}
              {b.info > 0 && <span className="v-info" style={{ flexGrow: b.info }} />}
            </motion.div>
          </div>
        );
      })}
    </div>
  );
}

function LogRow({ entry, isNew, onCorrelation, showService }) {
  const [open, setOpen] = useState(false);
  return (
    <motion.li
      className={`log-row level-${levelTone(entry.level)} ${open ? "open" : ""}`}
      initial={isNew ? { opacity: 0, backgroundColor: "var(--accent-soft)" } : false}
      animate={{ opacity: 1, backgroundColor: "rgba(0,0,0,0)" }}
      transition={{ duration: 1.2, ease }}
    >
      <button className="log-main" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <ChevronRight size={13} className="log-caret" />
        <span className="log-time mono">{time(entry.ts)}</span>
        {showService && (
          <span className="log-service" style={{ "--h": hue(entry.service) }}>
            {entry.service.replace("-service", "")}
          </span>
        )}
        <span className={`log-level tone-${levelTone(entry.level)}`}>{entry.level ? entry.level.slice(0, 4) : "—"}</span>
        <span className="log-msg">
          {entry.message}
          {entry.fields.slice(0, 4).map(([k, v]) => (
            <span key={k} className="log-field">
              <span className="muted">{k}=</span>
              {typeof v === "object" ? JSON.stringify(v) : String(v)}
            </span>
          ))}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div className="log-detail" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2, ease }}>
            {entry.correlationId && (
              <button className="link small" onClick={() => onCorrelation(entry.correlationId)}>
                Follow {entry.correlationId} across services <ChevronRight size={12} />
              </button>
            )}
            <pre>{entry.json ? JSON.stringify(entry.json, null, 2) : entry.message}</pre>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.li>
  );
}

/**
 * Log search over Loki. `fixedScope` locks the service (microservice detail pages);
 * `compact` drops the volume chart and the query panel.
 */
export function LogExplorer({ initialCorrelation = "", fixedScope, compact = false, limit = 300, defaultRange = 900 }) {
  const [scope, setScope] = useState(fixedScope ?? "app");
  const [level, setLevel] = useState("");
  const [text, setText] = useState("");
  const [correlationId, setCorrelationId] = useState(initialCorrelation);
  const [seconds, setSeconds] = useState(initialCorrelation ? 3600 : defaultRange);
  const [hideRequests, setHideRequests] = useState(!initialCorrelation);
  const [live, setLive] = useState(true);
  const [debouncedText, setDebouncedText] = useState("");
  const timer = useRef(null);

  const onText = (v) => {
    setText(v);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setDebouncedText(v), 350);
  };

  const query = buildQuery({ scope: fixedScope ?? scope, level, text: debouncedText, correlationId, hideRequests });
  const logs = useLogs({ query, seconds, limit, live });
  const volume = useLogVolume({ query, seconds, live: live && !compact });

  // Lines not seen before get a short highlight.
  const seen = useRef(new Set());
  const fresh = useMemo(() => {
    const isFirst = seen.current.size === 0;
    const out = new Set();
    for (const e of logs.data ?? []) {
      if (!seen.current.has(e.key)) {
        if (!isFirst) out.add(e.key);
        seen.current.add(e.key);
      }
    }
    return out;
  }, [logs.data]);

  const services = new Set((logs.data ?? []).map((l) => l.service));
  const errors = (logs.data ?? []).filter((l) => levelTone(l.level) === "danger").length;

  return (
    <div className={`logs ${compact ? "compact" : ""}`}>
      <div className="log-toolbar">
        {!fixedScope && (
          <select className="select" value={scope} onChange={(e) => setScope(e.target.value)} aria-label="Service">
            {SCOPES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        )}
        <label className="search log-search">
          <Search size={15} />
          <input value={text} onChange={(e) => onText(e.target.value)} placeholder="Search text" />
        </label>
        {!compact && (
          <label className={`search log-search corr ${correlationId ? "filled" : ""}`}>
            <span className="mono muted">cid</span>
            <input value={correlationId} onChange={(e) => setCorrelationId(e.target.value)} placeholder="Correlation ID" spellCheck={false} />
            {correlationId && (
              <button className="icon-btn" onClick={() => setCorrelationId("")} aria-label="Clear correlation ID">
                <X size={13} />
              </button>
            )}
          </label>
        )}
        <Segmented size="sm" options={LEVELS.map((l) => ({ value: l.value, label: l.label.replace("Warnings & errors", "Warn+").replace("Errors only", "Errors").replace("All levels", "All") }))} value={level} onChange={setLevel} />
        <Segmented size="sm" options={RANGES.map((r) => ({ value: r.value, label: r.label }))} value={seconds} onChange={setSeconds} />
        <span className="log-tools-right">
          <label className="keep-toggle small muted" title="Hide per-request access logs (dashboard polling)">
            <Switch checked={hideRequests} onChange={setHideRequests} label="Hide request logs" />
            Hide requests
          </label>
          <button className={`icon-btn live-btn ${live ? "on" : ""}`} onClick={() => setLive((v) => !v)} title={live ? "Pause live tail" : "Resume live tail"} aria-label={live ? "Pause" : "Resume"}>
            {live ? <Pause size={15} /> : <Play size={15} />}
          </button>
        </span>
      </div>

      {!compact && <Volume data={volume.data} />}

      <div className="log-meta small muted">
        <span>
          {logs.data ? `${logs.data.length}${logs.data.length >= limit ? "+" : ""} lines` : "…"} · {services.size} service{services.size === 1 ? "" : "s"}
          {errors > 0 && (
            <>
              {" "}
              · <span className="danger">{errors} error{errors === 1 ? "" : "s"}</span>
            </>
          )}
        </span>
        <span className="log-meta-right">
          {live && <Badge tone="success">Live</Badge>}
          <a className="link small" href={grafanaExplore(query, seconds)} target="_blank" rel="noreferrer">
            Grafana Explore <ExternalLink size={12} />
          </a>
        </span>
      </div>

      {logs.isError && <ErrorState error={logs.error} source="Log search" />}
      {logs.isLoading && <Skeleton rows={6} height={28} />}
      {logs.data?.length === 0 && (
        <div className="log-empty muted small">
          No log lines match in the last {RANGES.find((r) => r.value === seconds)?.label}. Loki usually indexes new lines within a few seconds.
        </div>
      )}
      <ul className="log-list">
        {(logs.data ?? []).map((e) => (
          <LogRow key={e.key} entry={e} isNew={fresh.has(e.key)} showService={!fixedScope} onCorrelation={(cid) => { setCorrelationId(cid); setHideRequests(false); setSeconds(3600); }} />
        ))}
      </ul>

      {!compact && (
        <details className="logql">
          <summary className="small muted">LogQL query</summary>
          <Code>{query}</Code>
        </details>
      )}
    </div>
  );
}

export default function Logs({ correlationId }) {
  return <LogExplorer key={correlationId ?? "all"} initialCorrelation={correlationId ?? ""} />;
}
