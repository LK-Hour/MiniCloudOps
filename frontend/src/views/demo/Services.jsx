import { motion } from "framer-motion";
import { ArrowRight, BellRing, Check, Database, Gauge, Radar, Siren, Target } from "lucide-react";
import { SERVICES, useInfrastructure, usePolicy, useSpec, useSpecs } from "../../api/hooks.js";
import { Badge, Card, Meter, Segmented, StatusDot, ease } from "../../components/ui.jsx";
import { bytes } from "../../lib/format.js";
import { LogExplorer } from "./Logs.jsx";

const rise = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease } } };

const COMMON = [
  "Python 3.12 · FastAPI · SQLAlchemy 2 · httpx",
  "Own PostgreSQL database and user; no other service reads it",
  "JSON logs with the request's correlation ID",
  "GET /health (liveness) and /health/ready (database)",
  "Prometheus metrics on /metrics",
  "Standard error body with code, message, details, correlation_id",
  "Non-root container (uid 10001) with a Docker healthcheck",
];

/** What each microservice is for, what it owns and how it behaves when its neighbours fail. */
export const CATALOG = {
  target: {
    title: "Target Service",
    icon: Target,
    owner: "Backend Engineer",
    tests: 51,
    purpose:
      "Source of truth for what is monitored. Registers and validates applications, stores how often to check them, and keeps each one's last known status.",
    database: "target_db",
    tables: [
      ["targets", "name, URL, type, check interval, enabled, status"],
      ["target_configurations", "per-target monitoring settings"],
    ],
    calls: [],
    calledBy: [
      ["Dashboard", "Create, edit, enable/disable and delete targets"],
      ["Monitoring Service", "Lists enabled targets every tick; reports status over an internal route"],
    ],
    guarantees: [
      "SSRF guard at registration: loopback, link-local (cloud metadata), internal container names, non-HTTP schemes and embedded credentials are rejected",
      "Only the Monitoring Service may set a status: the gateway hides PATCH /targets/{id}/status",
      "Disabling a target resets its status to UNKNOWN; deleting it makes Monitoring resolve its open incident",
      "Validation errors name the exact field (422), so forms can show them inline",
    ],
    env: ["DATABASE_URL", "SSRF_ALLOW_PRIVATE_NETWORKS", "LOG_LEVEL"],
    metrics: ["process & Python runtime metrics"],
  },
  monitoring: {
    title: "Monitoring Service",
    icon: Radar,
    owner: "Backend Engineer",
    tests: 50,
    purpose:
      "The platform's engine. Schedules HTTP health checks, applies the incident rules, and reads host and container metrics from Prometheus.",
    database: "monitoring_db",
    tables: [
      ["health_checks", "every check result, kept 7 days"],
      ["target_states", "current status, failure counter, open incident"],
    ],
    calls: [
      ["Target Service", "GET enabled targets (paged) · PATCH status", "Skips the round; nothing is reset"],
      ["Incident Service", "POST incident · PATCH status=RESOLVED", "Retries on the next check; checks keep running"],
      ["Prometheus", "PromQL: CPU, memory, scrape health, alerts", "Metrics shown as unavailable (null, never 0)"],
      ["Monitored apps", "GET target URL, no redirects", "Timeout or 4xx/5xx counts as a failed check"],
    ],
    calledBy: [["Dashboard", "Overview, history, infrastructure, Check now"]],
    guarantees: [
      "Scheduler tick every 5 s; never two checks of the same target at once (per-target lock)",
      "SSRF re-check before every request, so a DNS answer that changes after registration is still caught",
      "Opens one incident after N consecutive failures and resolves it on the first success",
      "Calls to other services retry network errors and 5xx with exponential backoff",
      "Incidents of disabled or deleted targets are resolved automatically",
    ],
    env: [
      "DATABASE_URL",
      "TARGET_SERVICE_URL",
      "INCIDENT_SERVICE_URL",
      "PROMETHEUS_URL",
      "DEFAULT_CHECK_INTERVAL_SECONDS",
      "FAILURE_THRESHOLD",
      "RESPONSE_TIME_THRESHOLD_MS",
      "SSRF_ALLOW_PRIVATE_NETWORKS",
    ],
    metrics: [
      "miniops_health_check_total",
      "miniops_health_check_failures_total",
      "miniops_http_response_time_seconds",
      "miniops_active_targets",
      "miniops_open_incidents",
    ],
  },
  incident: {
    title: "Incident Service",
    icon: Siren,
    owner: "Backend Engineer",
    tests: 20,
    purpose:
      "Owns the incident lifecycle: opening, acknowledging and resolving incidents, with a complete audit trail of every change and notification attempt.",
    database: "incident_db",
    tables: [
      ["incidents", "target, title, severity, status, timestamps"],
      ["incident_events", "append-only history: CREATED, ACKNOWLEDGED, RESOLVED, NOTIFICATION_*"],
    ],
    calls: [["Notification Service", "POST notification, after the commit, in the background", "Incident stays saved; NOTIFICATION_FAILED is recorded"]],
    calledBy: [
      ["Monitoring Service", "Opens and resolves incidents"],
      ["Dashboard", "Lists incidents, acknowledges and resolves"],
    ],
    guarantees: [
      "At most one unresolved incident per target (partial unique index); a repeated report returns the existing one with 200",
      "Status only moves forward: OPEN → ACKNOWLEDGED → RESOLVED; anything else is 409",
      "Setting the status an incident already has is a no-op, so retries are safe",
      "Every change and every notification attempt is recorded as an event",
    ],
    env: ["DATABASE_URL", "NOTIFICATION_SERVICE_URL", "LOG_LEVEL"],
    metrics: ["process & Python runtime metrics"],
  },
  notification: {
    title: "Notification Service",
    icon: BellRing,
    owner: "Backend Engineer",
    tests: 14,
    purpose:
      "Stores the messages sent when incidents open and resolve, deduplicates retried deliveries, and serves the dashboard's notification inbox.",
    database: "notification_db",
    tables: [["notifications", "incident, event type, severity, title, message, read, dedup_key"]],
    calls: [],
    calledBy: [
      ["Incident Service", "One notification per incident event"],
      ["Dashboard", "Inbox and mark as read"],
    ],
    guarantees: [
      "Deduplicated on incident_id:event_type: a retried delivery returns the stored copy with 200",
      "Concurrent duplicates are caught by a unique constraint, not just a lookup",
      "Read state is per notification and idempotent",
    ],
    env: ["DATABASE_URL", "LOG_LEVEL"],
    metrics: ["process & Python runtime metrics"],
  },
};

// --- service map ---------------------------------------------------------------------------------

const NODES = {
  dashboard: { x: 90, y: 160, label: "Dashboard", sub: "React · nginx" },
  gateway: { x: 255, y: 160, label: "API gateway", sub: "nginx :8080" },
  target: { x: 470, y: 60, label: "target-service", sub: "target_db", service: true },
  monitoring: { x: 470, y: 160, label: "monitoring-service", sub: "monitoring_db", service: true },
  incident: { x: 470, y: 260, label: "incident-service", sub: "incident_db", service: true },
  notification: { x: 715, y: 260, label: "notification-service", sub: "notification_db", service: true },
  prometheus: { x: 715, y: 160, label: "Prometheus", sub: "metrics · alerts" },
  loki: { x: 715, y: 60, label: "Loki", sub: "container logs" },
};
const W = 160;
const H = 46;

const EDGES = [
  { from: "dashboard", to: "gateway", label: "HTTPS /api/v1" },
  { from: "gateway", to: "target" },
  { from: "gateway", to: "monitoring" },
  { from: "gateway", to: "incident" },
  { from: "gateway", to: "notification", d: "M 335 172 C 370 345, 590 345, 635 275" },
  { from: "monitoring", to: "target", label: "list · report status" },
  { from: "monitoring", to: "incident", label: "open · resolve" },
  { from: "incident", to: "notification", label: "notify" },
  { from: "monitoring", to: "prometheus", label: "PromQL" },
];

function edgePath(e) {
  if (e.d) return e.d;
  const a = NODES[e.from];
  const b = NODES[e.to];
  if (a.x === b.x) {
    const dir = b.y > a.y ? 1 : -1;
    return `M ${a.x} ${a.y + (dir * H) / 2} L ${b.x} ${b.y - (dir * H) / 2}`;
  }
  const x1 = a.x + W / 2;
  const x2 = b.x - W / 2;
  const mid = (x1 + x2) / 2;
  return `M ${x1} ${a.y} C ${mid} ${a.y}, ${mid} ${b.y}, ${x2} ${b.y}`;
}

function ServiceMap({ selected, onSelect, health }) {
  return (
    <div className="svc-map-scroll">
      <svg className="svc-map" viewBox="0 0 810 330" role="img" aria-label="Service map">
        {EDGES.map((e) => {
          const hot = e.from === selected || e.to === selected;
          const a = NODES[e.from];
          const b = NODES[e.to];
          return (
            <g key={`${e.from}-${e.to}`} className={`svc-edge ${hot ? "hot" : ""}`}>
              <path d={edgePath(e)} />
              {hot && e.label && (
                <text x={a.x === b.x ? a.x + 8 : (a.x + b.x) / 2} y={a.x === b.x ? (a.y + b.y) / 2 + 4 : (a.y + b.y) / 2 - 8} textAnchor={a.x === b.x ? "start" : "middle"}>
                  {e.label}
                </text>
              )}
            </g>
          );
        })}
        {Object.entries(NODES).map(([id, n]) => {
          const isSel = id === selected;
          const status = n.service ? health[id] : null;
          return (
            <g
              key={id}
              className={`svc-node ${n.service ? "clickable" : ""} ${isSel ? "selected" : ""}`}
              transform={`translate(${n.x - W / 2} ${n.y - H / 2})`}
              onClick={n.service ? () => onSelect(id) : undefined}
              role={n.service ? "button" : undefined}
              tabIndex={n.service ? 0 : undefined}
              onKeyDown={n.service ? (ev) => (ev.key === "Enter" || ev.key === " ") && onSelect(id) : undefined}
            >
              <rect width={W} height={H} rx={10} />
              {status && <circle className={`svc-dot dot-${status}`} cx={14} cy={H / 2} r={4} />}
              <text x={n.service ? 26 : 14} y={20} className="svc-label">
                {n.label}
              </text>
              <text x={n.service ? 26 : 14} y={35} className="svc-sub">
                {n.sub}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// --- detail --------------------------------------------------------------------------------------

function Endpoints({ service, go }) {
  const spec = useSpec(service);
  if (!spec.data) return <p className="muted small">{spec.isError ? "OpenAPI document unavailable" : "Loading…"}</p>;
  const ops = Object.entries(spec.data.paths).flatMap(([path, item]) =>
    ["get", "post", "put", "patch", "delete"].filter((m) => item[m]).map((m) => ({ method: m, path, summary: item[m].summary })),
  );
  return (
    <>
      <ul className="endpoint-list">
        {ops.map((o) => (
          <li key={`${o.method}${o.path}`}>
            <span className={`method method-${o.method}`}>{o.method.toUpperCase()}</span>
            <span className="mono small">{o.path}</span>
          </li>
        ))}
      </ul>
      <button className="link small" onClick={() => go("docs", `api-${service}`)}>
        Full API reference <ArrowRight size={13} />
      </button>
    </>
  );
}

function ServiceDetail({ id, go, health, container, specVersion }) {
  const svc = CATALOG[id];
  const policy = usePolicy();
  const Icon = svc.icon;
  const name = `${id}-service`;
  const hostMem = useInfrastructure().data?.host?.memory_total_bytes;
  const policyValue = {
    DEFAULT_CHECK_INTERVAL_SECONDS: policy.data && `${policy.data.default_check_interval_seconds}`,
    FAILURE_THRESHOLD: policy.data && `${policy.data.failure_threshold}`,
    RESPONSE_TIME_THRESHOLD_MS: policy.data && `${policy.data.response_time_threshold_ms}`,
    SSRF_ALLOW_PRIVATE_NETWORKS: policy.data && `${policy.data.ssrf_allow_private_networks}`,
    TARGET_SERVICE_URL: "http://target-service:8000",
    INCIDENT_SERVICE_URL: "http://incident-service:8000",
    NOTIFICATION_SERVICE_URL: "http://notification-service:8000",
    PROMETHEUS_URL: "http://prometheus:9090",
    DATABASE_URL: `postgresql+psycopg://…@postgres:5432/${svc.database}`,
    LOG_LEVEL: "INFO",
  };

  return (
    <motion.div key={id} className="svc-detail" initial="initial" animate="animate" variants={{ animate: { transition: { staggerChildren: 0.04 } } }}>
      <motion.header variants={rise} className="svc-head">
        <span className="svc-icon">
          <Icon size={20} />
        </span>
        <div className="svc-head-main">
          <h2>
            {svc.title} <StatusDot status={health[id]} />
          </h2>
          <p className="muted">{svc.purpose}</p>
          <div className="svc-chips">
            <Badge tone="info">{specVersion ? `v${specVersion}` : "version …"}</Badge>
            <span className="chip mono">{name}:8000</span>
            <span className="chip mono">
              <Database size={12} /> {svc.database}
            </span>
            <span className="chip mono">ghcr.io/…/miniops-{name}</span>
            <span className="chip">{svc.tests} unit tests</span>
          </div>
        </div>
      </motion.header>

      <div className="svc-grid">
        <div className="stack">
          <Card title="Guarantees" variants={rise}>
            <ul className="checklist">
              {svc.guarantees.map((g) => (
                <li key={g}>
                  <Check size={14} className="ok" />
                  <span>{g}</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Dependencies" variants={rise}>
            {svc.calls.length ? (
              <div className="dep-table">
                <div className="dep-row dep-headrow small muted">
                  <span>Calls</span>
                  <span>For</span>
                  <span>If it is down</span>
                </div>
                {svc.calls.map(([to, what, fallback]) => (
                  <div key={to} className="dep-row">
                    <strong>{to}</strong>
                    <span className="small">{what}</span>
                    <span className="small muted">{fallback}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted small">No outbound calls: this service only answers requests.</p>
            )}
            <div className="called-by">
              <span className="eyebrow">Called by</span>
              {svc.calledBy.map(([who, why]) => (
                <div key={who} className="called-row">
                  <strong className="small">{who}</strong>
                  <span className="small muted">{why}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card title="Data it owns" variants={rise}>
            <dl className="kv">
              {svc.tables.map(([t, d]) => (
                <div key={t}>
                  <dt className="mono">{t}</dt>
                  <dd>{d}</dd>
                </div>
              ))}
            </dl>
          </Card>
        </div>

        <div className="stack">
          <Card title="Live resources" variants={rise} action={<span className="muted small">cAdvisor</span>}>
            {container ? (
              <div className="stack-sm">
                <Meter label="CPU" value={container.cpu_percent ?? 0} detail={`${(container.cpu_percent ?? 0).toFixed(1)}% of a core`} />
                <Meter
                  label="Memory"
                  value={hostMem ? ((container.memory_bytes ?? 0) / hostMem) * 100 : 0}
                  warn={20}
                  danger={40}
                  detail={bytes(container.memory_bytes)}
                />
              </div>
            ) : (
              <p className="muted small">No container metrics: the service is stopped or Prometheus is unavailable.</p>
            )}
          </Card>

          <Card title="Endpoints" variants={rise}>
            <Endpoints service={id} go={go} />
          </Card>

          <Card title="Configuration" variants={rise} action={<span className="muted small">environment</span>}>
            <dl className="kv kv-mono">
              {svc.env.map((k) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{policyValue[k] ?? "—"}</dd>
                </div>
              ))}
            </dl>
          </Card>

          <Card title="Metrics" variants={rise} action={<Gauge size={14} className="muted" />}>
            <ul className="metric-names">
              {svc.metrics.map((m) => (
                <li key={m} className="mono small">
                  {m}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>

      <Card title="Recent logs" variants={rise} action={<span className="muted small">Loki · live</span>}>
        <LogExplorer key={name} fixedScope={name} compact limit={60} />
      </Card>
    </motion.div>
  );
}

export default function Services({ service, go }) {
  const selected = SERVICES.includes(service) ? service : "monitoring";
  const specs = useSpecs();
  const infra = useInfrastructure();
  const scrapeUp = Object.fromEntries((infra.data?.services ?? []).map((s) => [s.instance.split(":")[0], s.up]));
  const health = Object.fromEntries(
    SERVICES.map((s, i) => [s, specs[i].isLoading ? "UNKNOWN" : specs[i].isSuccess && scrapeUp[`${s}-service`] !== false ? "UP" : "DOWN"]),
  );
  const container = (infra.data?.containers ?? []).find((c) => c.service === `${selected}-service`);
  const select = (id) => go("demo", `services/${id}`);

  return (
    <div className="stack">
      <Card
        title="Service map"
        action={<span className="muted small">Select a service · highlighted lines are its calls</span>}
      >
        <ServiceMap selected={selected} onSelect={select} health={health} />
        <div className="common-traits">
          <span className="eyebrow">Every service</span>
          <ul>
            {COMMON.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      </Card>

      <Segmented
        options={SERVICES.map((s) => ({ value: s, label: CATALOG[s].title.replace(" Service", "") }))}
        value={selected}
        onChange={select}
      />

      <ServiceDetail
        key={selected}
        id={selected}
        go={go}
        health={health}
        container={container}
        specVersion={specs[SERVICES.indexOf(selected)].data?.info?.version}
      />
    </div>
  );
}
