import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronRight, Copy, Search } from "lucide-react";
import { SERVICES, usePolicy, useSpec } from "../api/hooks.js";
import { Badge, ErrorState, Skeleton, ease } from "../components/ui.jsx";

// --- small building blocks -------------------------------------------------------------------

export function Code({ children }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(children);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked (insecure context): the text is still selectable */
    }
  };
  return (
    <div className="code">
      <pre>{children}</pre>
      <button className="icon-btn code-copy" onClick={copy} aria-label="Copy">
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </div>
  );
}

export function Callout({ tone = "info", title, children }) {
  return (
    <div className={`callout tone-${tone}`}>
      {title && <strong>{title}</strong>}
      <div>{children}</div>
    </div>
  );
}

export const C = ({ children }) => <code className="inline-code">{children}</code>;

// --- guides ----------------------------------------------------------------------------------

function GettingStarted({ policy, go }) {
  const origin = window.location.origin;
  return (
    <>
      <p className="lead">
        MiniOps checks your applications over HTTP, opens an incident when one stops responding, and resolves it when it
        recovers. This guide gets your first application monitored in about two minutes.
      </p>
      <h2>1. Expose a health endpoint</h2>
      <p>
        Any URL that answers <C>2xx</C> or <C>3xx</C> while the app is healthy works. A dedicated endpoint such as{" "}
        <C>/health</C> is best: it should be fast, need no login, and fail when a critical dependency fails.
      </p>
      <h2>2. Register the target</h2>
      <p>
        Open <button className="link" onClick={() => go("targets", "new")}>Targets → Add target</button>, or use the API:
      </p>
      <Code>{`curl -X POST ${origin}/api/v1/targets \\
  -H "Content-Type: application/json" \\
  -d '{"name": "Payments API", "target_url": "http://payments:8000/health", "check_interval": 30}'`}</Code>
      <h2>3. Watch it</h2>
      <ul>
        <li>The first check runs within {policy?.scheduler_tick_seconds ?? 5} seconds, then every <C>check_interval</C> seconds.</li>
        <li>
          After {policy?.failure_threshold ?? 3} failed checks in a row a <Badge tone="danger">CRITICAL</Badge> incident opens and a
          notification appears.
        </li>
        <li>The first successful check resolves the incident automatically.</li>
      </ul>
      <Callout title="Apps in Docker Compose">
        Use the Compose service name as the host, for example <C>http://demo-app/</C>. MiniOps then also shows the
        container's CPU and memory.
      </Callout>
    </>
  );
}

function Concepts() {
  return (
    <>
      <p className="lead">Four ideas cover everything MiniOps does.</p>
      <h2>Target</h2>
      <p>An application to watch: a name, a health URL, a check interval (10–3600 s) and an enabled flag. Names are unique.</p>
      <h2>Health check</h2>
      <p>One <C>GET</C> request to the target's URL. The result is stored for the history and the charts.</p>
      <table className="doc-table">
        <thead>
          <tr>
            <th>Status</th>
            <th>Meaning</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><Badge tone="success">UP</Badge></td>
            <td>The last check got a 2xx or 3xx answer.</td>
          </tr>
          <tr>
            <td><Badge tone="danger">DOWN</Badge></td>
            <td>The last check got a 4xx/5xx, timed out, could not connect, or the host did not resolve.</td>
          </tr>
          <tr>
            <td><Badge>UNKNOWN</Badge></td>
            <td>Not checked yet, or the target is disabled.</td>
          </tr>
        </tbody>
      </table>
      <h2>Incident</h2>
      <p>
        A record of an outage, with a severity, a status (<C>OPEN</C> → <C>ACKNOWLEDGED</C> → <C>RESOLVED</C>) and a timeline.
        One target never has more than one unresolved incident.
      </p>
      <h2>Notification</h2>
      <p>A message created when an incident opens or resolves. One per incident event, so retries never produce duplicates.</p>
    </>
  );
}

function IncidentLifecycle({ policy }) {
  const n = policy?.failure_threshold ?? 3;
  return (
    <>
      <p className="lead">How an outage turns into an incident, and back.</p>
      <ol className="steps">
        <li><strong>Failure.</strong> A check fails. The target shows DOWN and its failure count increases.</li>
        <li><strong>Threshold.</strong> After {n} consecutive failures an incident opens with severity CRITICAL. A single slow or failed check does not page anyone.</li>
        <li><strong>Notify.</strong> The Incident Service saves the incident first, then notifies. If notifications are down the incident is still saved, and the timeline records <C>NOTIFICATION_FAILED</C>.</li>
        <li><strong>Acknowledge</strong> (optional). Tells the team someone is on it. The incident stays active.</li>
        <li><strong>Resolve.</strong> Happens automatically on the first successful check, or manually from the incident panel.</li>
      </ol>
      <Callout tone="warning" title="Disabling or deleting a target">
        Its open incident is resolved with the note "Monitoring stopped", so nothing stays open forever.
      </Callout>
      <h2>Resilience</h2>
      <p>
        Calls between services time out after a few seconds and are retried 3 times with exponential backoff. If the
        Incident Service is unavailable, the Monitoring Service keeps recording checks and opens the incident on the next
        check after it returns.
      </p>
    </>
  );
}

function Metrics() {
  return (
    <>
      <p className="lead">Where the numbers on the Infrastructure page come from.</p>
      <table className="doc-table">
        <thead>
          <tr><th>Metric</th><th>Source</th></tr>
        </thead>
        <tbody>
          <tr><td>Host CPU, memory, disk, uptime</td><td>Node Exporter, via Prometheus</td></tr>
          <tr><td>Container CPU and memory</td><td>cAdvisor, via Prometheus, matched by Compose service name</td></tr>
          <tr><td>Service status</td><td>Prometheus scrape status of each MiniOps service</td></tr>
          <tr><td>Response times, check counts</td><td>The Monitoring Service's own <C>miniops_*</C> metrics</td></tr>
        </tbody>
      </table>
      <Callout title="No data is never zero">
        When Prometheus is unreachable, or a target is not a container in this stack, values show as "no data". A 0% bar
        always means a real 0.
      </Callout>
      <h2>Alert rules</h2>
      <p>Prometheus evaluates these (demonstration thresholds):</p>
      <ul>
        <li>Container CPU above 80% for 1 minute: warning</li>
        <li>Container memory above 85% of its limit for 1 minute: warning</li>
        <li>Host memory above 85% for 1 minute: warning</li>
        <li>A MiniOps service not answering scrapes for 30 seconds: critical</li>
      </ul>
      <p>Firing and pending alerts appear on the Infrastructure page. Full dashboards are in Grafana.</p>
    </>
  );
}

function Troubleshooting() {
  return (
    <>
      <p className="lead">Common situations and what to do.</p>
      <h3>"Target URL is not allowed"</h3>
      <p>
        MiniOps refuses URLs that point at itself or at sensitive addresses: loopback, link-local and cloud metadata (
        <C>169.254.169.254</C>), MiniOps's own containers, and URLs with a username and password. Use the application's
        own hostname.
      </p>
      <h3>A target is DOWN with "DNS lookup failed"</h3>
      <p>The hostname does not resolve. In Docker Compose this usually means the container is stopped or on another network.</p>
      <h3>The header says "Degraded"</h3>
      <p>One API is failing. Hover the indicator to see which. The other pages keep working.</p>
      <h3>Following one request across services</h3>
      <p>
        Every request carries an <C>X-Correlation-ID</C>; scheduled checks use <C>check-…</C> IDs. Error messages in the
        dashboard show the ID. In Grafana → Explore → Loki:
      </p>
      <Code>{'{compose_project="miniops"} | json | correlation_id="check-0123abcd4567"'}</Code>
    </>
  );
}

function Shortcuts() {
  const rows = [
    ["Ctrl K  /  ⌘ K", "Command palette: jump to any page, target or incident"],
    ["1 – 9", "Switch page"],
    ["Esc", "Close a panel or dialog"],
  ];
  return (
    <>
      <p className="lead">Move around without the mouse.</p>
      <table className="doc-table">
        <tbody>
          {rows.map(([k, d]) => (
            <tr key={k}>
              <td><kbd>{k}</kbd></td>
              <td>{d}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

// --- API reference (rendered from the live OpenAPI documents) --------------------------------

const SERVICE_LABEL = { target: "Targets", monitoring: "Monitoring", incident: "Incidents", notification: "Notifications" };
const METHOD_ORDER = ["get", "post", "put", "patch", "delete"];

function resolve(schema, spec) {
  if (schema?.$ref) return resolve(spec.components?.schemas?.[schema.$ref.split("/").pop()], spec);
  return schema ?? {};
}

function typeLabel(schema, spec) {
  if (!schema) return "any";
  if (schema.$ref) return schema.$ref.split("/").pop();
  if (schema.anyOf) return schema.anyOf.map((s) => typeLabel(s, spec)).join(" | ");
  if (schema.enum) return schema.enum.map((v) => JSON.stringify(v)).join(" | ");
  if (schema.const !== undefined) return JSON.stringify(schema.const);
  if (schema.type === "array") return `${typeLabel(schema.items, spec)}[]`;
  return schema.format ? `${schema.type} (${schema.format})` : schema.type ?? "object";
}

function constraints(schema) {
  const s = schema.anyOf?.find((x) => x.type !== "null") ?? schema;
  const out = [];
  if (s.minLength != null) out.push(`min length ${s.minLength}`);
  if (s.maxLength != null) out.push(`max length ${s.maxLength}`);
  if (s.minimum != null) out.push(`≥ ${s.minimum}`);
  if (s.maximum != null) out.push(`≤ ${s.maximum}`);
  if (schema.default !== undefined) out.push(`default ${JSON.stringify(schema.default)}`);
  return out.join(" · ");
}

function SchemaFields({ schema, spec, showRequired = true }) {
  const resolved = resolve(schema, spec);
  const props = resolved.properties;
  if (!props) return <p className="muted small mono">{typeLabel(schema, spec)}</p>;
  const required = new Set(resolved.required ?? []);
  return (
    <table className="doc-table fields">
      <tbody>
        {Object.entries(props).map(([name, p]) => (
          <tr key={name}>
            <td>
              <span className="mono">{name}</span>
              {showRequired && required.has(name) && <span className="req">required</span>}
            </td>
            <td>
              <span className="mono muted">{typeLabel(p, spec)}</span>
              {(p.description || constraints(p)) && (
                <span className="field-doc">{[p.description, constraints(p)].filter(Boolean).join(" · ")}</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function curlFor(method, path, op, spec) {
  const url = `${window.location.origin}${path.replace(/\{(\w+)\}/g, "<$1>")}`;
  const parts = [`curl${method === "get" ? "" : ` -X ${method.toUpperCase()}`} "${url}"`];
  const body = op.requestBody?.content?.["application/json"]?.schema;
  if (body) {
    const resolved = resolve(body, spec);
    const example = Object.fromEntries(
      (resolved.required ?? Object.keys(resolved.properties ?? {}).slice(0, 2)).map((k) => [k, `<${k}>`]),
    );
    parts.push(`-H "Content-Type: application/json"`, `-d '${JSON.stringify(example)}'`);
  }
  return parts.join(" \\\n  ");
}

function Operation({ method, path, op, spec }) {
  const [open, setOpen] = useState(false);
  const internal = !path.startsWith("/api/v1/") || /internal/i.test(op.summary ?? "");
  const body = op.requestBody?.content?.["application/json"]?.schema;
  const params = op.parameters ?? [];
  const ok = Object.entries(op.responses ?? {}).find(([code]) => code.startsWith("2"));
  return (
    <div className={`op ${open ? "open" : ""}`}>
      <button className="op-head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className={`method method-${method}`}>{method.toUpperCase()}</span>
        <span className="mono op-path">{path}</span>
        <span className="op-summary truncate">{op.summary}</span>
        {internal && <Badge tone="warning">internal</Badge>}
        <motion.span animate={{ rotate: open ? 90 : 0 }} className="muted" style={{ display: "flex" }}>
          <ChevronRight size={16} />
        </motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            className="op-body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1, transition: { duration: 0.25, ease } }}
            exit={{ height: 0, opacity: 0, transition: { duration: 0.18 } }}
          >
            <div className="op-inner">
              {op.description && <p className="op-desc">{op.description}</p>}
              {internal && (
                <Callout tone="warning">
                  Not reachable through the gateway. Used between MiniOps services, or by Docker and Prometheus.
                </Callout>
              )}
              {params.length > 0 && (
                <>
                  <h4 className="section-title">Parameters</h4>
                  <table className="doc-table fields">
                    <tbody>
                      {params.map((p) => (
                        <tr key={`${p.in}-${p.name}`}>
                          <td>
                            <span className="mono">{p.name}</span>
                            {p.required && <span className="req">required</span>}
                          </td>
                          <td>
                            <span className="mono muted">
                              {p.in} · {typeLabel(p.schema, spec)}
                            </span>
                            {(p.description || p.schema?.description || constraints(p.schema ?? {})) && (
                              <span className="field-doc">
                                {[p.description ?? p.schema?.description, constraints(p.schema ?? {})].filter(Boolean).join(" · ")}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
              {body && (
                <>
                  <h4 className="section-title">Request body</h4>
                  <SchemaFields schema={body} spec={spec} />
                </>
              )}
              {ok?.[1]?.content?.["application/json"]?.schema && (
                <>
                  <h4 className="section-title">Response {ok[0]}</h4>
                  <SchemaFields schema={ok[1].content["application/json"].schema} spec={spec} showRequired={false} />
                </>
              )}
              <h4 className="section-title">Status codes</h4>
              <div className="codes">
                {Object.entries(op.responses ?? {}).map(([code, r]) => (
                  <span key={code} className={`code-chip c${code[0]}`} title={r.description}>
                    {code} <span className="muted">{r.description}</span>
                  </span>
                ))}
              </div>
              {!internal && (
                <>
                  <h4 className="section-title">Example</h4>
                  <Code>{curlFor(method, path, op, spec)}</Code>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function ApiReference({ service }) {
  const spec = useSpec(service);
  const [query, setQuery] = useState("");
  const operations = useMemo(() => {
    if (!spec.data) return [];
    const q = query.trim().toLowerCase();
    return Object.entries(spec.data.paths)
      .flatMap(([path, item]) =>
        METHOD_ORDER.filter((m) => item[m]).map((method) => ({ method, path, op: item[method] })),
      )
      .filter(({ path, op, method }) => !q || `${method} ${path} ${op.summary}`.toLowerCase().includes(q))
      .sort((a, b) => Number(!a.path.startsWith("/api/")) - Number(!b.path.startsWith("/api/")));
  }, [spec.data, query]);

  return (
    <>
      <div className="api-head">
        <p className="lead">
          {spec.data ? (
            <>
              {spec.data.info.title} · <span className="mono">v{spec.data.info.version}</span> · generated live from the
              service's OpenAPI document.
            </>
          ) : (
            "Loading the service's OpenAPI document…"
          )}
        </p>
        <label className="search">
          <Search size={15} />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter endpoints" />
        </label>
      </div>
      {spec.isError && <ErrorState error={spec.error} source={`${SERVICE_LABEL[service]} API`} />}
      {spec.isLoading && <Skeleton rows={5} height={46} />}
      <div className="ops">
        {operations.map((o) => (
          <Operation key={`${o.method} ${o.path}`} {...o} spec={spec.data} />
        ))}
      </div>
      {spec.data && (
        <Callout title="Conventions">
          JSON in and out. Errors use <C>{'{"error": {"code", "message", "details", "correlation_id"}}'}</C>. Send{" "}
          <C>X-Correlation-ID</C> to trace a request; one is generated if you don't.
        </Callout>
      )}
    </>
  );
}

// --- page ------------------------------------------------------------------------------------

export const DOC_PAGES = [
  { id: "getting-started", group: "Guides", title: "Getting started", render: GettingStarted },
  { id: "concepts", group: "Guides", title: "Core concepts", render: Concepts },
  { id: "incidents", group: "Guides", title: "Incident lifecycle", render: IncidentLifecycle },
  { id: "metrics", group: "Guides", title: "Metrics & alerts", render: Metrics },
  { id: "troubleshooting", group: "Guides", title: "Troubleshooting", render: Troubleshooting },
  { id: "shortcuts", group: "Guides", title: "Keyboard shortcuts", render: Shortcuts },
  ...SERVICES.map((s) => ({
    id: `api-${s}`,
    group: "API reference",
    title: SERVICE_LABEL[s],
    render: () => <ApiReference service={s} />,
  })),
];

export default function Docs({ sub, go }) {
  const policy = usePolicy();
  const page = DOC_PAGES.find((p) => p.id === sub) ?? DOC_PAGES[0];
  const groups = [...new Set(DOC_PAGES.map((p) => p.group))];
  const Render = page.render;

  return (
    <div className="docs">
      <nav className="docs-nav" aria-label="Documentation">
        {groups.map((g) => (
          <div key={g} className="docs-nav-group">
            <span className="docs-nav-label">{g}</span>
            {DOC_PAGES.filter((p) => p.group === g).map((p) => (
              <button key={p.id} className={`docs-link ${p.id === page.id ? "active" : ""}`} onClick={() => go("docs", p.id)}>
                {p.id === page.id && <motion.span layoutId="docs-active" className="docs-link-bg" transition={{ type: "spring", stiffness: 420, damping: 36 }} />}
                <span>{p.title}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>
      <AnimatePresence mode="wait">
        <motion.article
          key={page.id}
          className="prose"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0, transition: { duration: 0.25, ease } }}
          exit={{ opacity: 0, transition: { duration: 0.12 } }}
        >
          <span className="eyebrow">{page.group}</span>
          <h1>{page.title}</h1>
          <Render policy={policy.data} go={go} />
        </motion.article>
      </AnimatePresence>
    </div>
  );
}
