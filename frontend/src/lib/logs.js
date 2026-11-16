// Log search against Loki, through the gateway's read-only /api/v1/logs/* routes.
// Container logs are shipped by Alloy with the labels: service, container, compose_project, level.

export const LOG_SERVICES = [
  "target-service",
  "monitoring-service",
  "incident-service",
  "notification-service",
  "gateway",
  "demo-app",
];

export const SCOPES = [
  { value: "app", label: "MiniOps services" },
  ...LOG_SERVICES.map((s) => ({ value: s, label: s })),
  { value: "all", label: "All containers" },
];

export const LEVELS = [
  { value: "", label: "All levels" },
  { value: "WARNING|ERROR|CRITICAL", label: "Warnings & errors" },
  { value: "ERROR|CRITICAL", label: "Errors only" },
];

export const RANGES = [
  { value: 5 * 60, label: "5m" },
  { value: 15 * 60, label: "15m" },
  { value: 60 * 60, label: "1h" },
  { value: 6 * 3600, label: "6h" },
  { value: 24 * 3600, label: "24h" },
];

const quote = (s) => `"${String(s).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;

/** LogQL for the given filters. Text filters are plain substring matches: fast and predictable. */
export function buildQuery({ scope = "app", level = "", text = "", correlationId = "", hideRequests = true } = {}) {
  const matchers = ['compose_project="miniops"'];
  if (scope === "app") matchers.push(`service=~${quote(LOG_SERVICES.join("|"))}`);
  else if (scope !== "all") matchers.push(`service=${quote(scope)}`);
  if (level) matchers.push(`level=~${quote(level)}`);
  // The dashboard's own log searches put the search text in the URL: never match those.
  let q = `{${matchers.join(", ")}} != "/api/v1/logs/"`;
  if (hideRequests) q += ' != "Request completed" != "GET /api/" != "GET /health"';
  if (correlationId.trim()) q += ` |= ${quote(correlationId.trim())}`;
  if (text.trim()) q += ` |= ${quote(text.trim())}`;
  return q;
}

const SKIP = new Set(["timestamp", "level", "service", "message", "logger", "correlation_id"]);

/** One Loki line: JSON from the MiniOps services, plain text from everything else. */
export function parseLine(line) {
  if (line.startsWith("{")) {
    try {
      const json = JSON.parse(line);
      const fields = Object.entries(json).filter(([k, v]) => !SKIP.has(k) && v !== null && v !== "");
      return {
        message: json.message ?? line,
        level: json.level ?? null,
        correlationId: json.correlation_id ?? null,
        logger: json.logger ?? null,
        fields,
        json,
      };
    } catch {
      /* not JSON after all */
    }
  }
  const level = /\b(error|crit|emerg|alert)\b/i.test(line) ? "ERROR" : /\bwarn/i.test(line) ? "WARNING" : null;
  return { message: line, level, correlationId: null, logger: null, fields: [], json: null };
}

/** query_range "streams" result -> newest-first entries. */
export function flattenStreams(result = []) {
  const out = [];
  for (const stream of result) {
    for (const [ns, line] of stream.values) {
      out.push({
        key: `${stream.stream.container}-${ns}-${out.length}`,
        ts: Number(BigInt(ns) / 1_000_000n),
        service: stream.stream.service ?? stream.stream.container ?? "unknown",
        ...parseLine(line),
      });
    }
  }
  return out.sort((a, b) => b.ts - a.ts);
}

export async function queryLogs({ query, seconds, limit = 300, signal }) {
  const end = Date.now();
  const params = new URLSearchParams({
    query,
    start: `${(end - seconds * 1000) * 1_000_000}`,
    end: `${end * 1_000_000}`,
    limit: String(limit),
    direction: "backward",
  });
  const response = await fetch(`/api/v1/logs/query_range?${params}`, { signal });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    const error = new Error(response.status === 503 ? "Log storage (Loki) is unavailable" : text.slice(0, 200) || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  const body = await response.json();
  return flattenStreams(body.data?.result);
}

/** Log volume per level over the range, as ~40 buckets. */
export async function queryVolume({ query, seconds, signal }) {
  const end = Date.now();
  const step = Math.max(5, Math.round(seconds / 40));
  const params = new URLSearchParams({
    query: `sum by (level) (count_over_time(${query} [${step}s]))`,
    start: `${(end - seconds * 1000) * 1_000_000}`,
    end: `${end * 1_000_000}`,
    step: `${step}s`,
  });
  const response = await fetch(`/api/v1/logs/query_range?${params}`, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const body = await response.json();
  const start = Math.floor((end - seconds * 1000) / 1000 / step) * step;
  const buckets = Array.from({ length: Math.ceil(seconds / step) + 1 }, (_, i) => ({ t: (start + i * step) * 1000, info: 0, warn: 0, error: 0 }));
  const index = (t) => Math.round((t - start) / step);
  for (const series of body.data?.result ?? []) {
    const lvl = series.metric.level ?? "";
    const bucket = /ERROR|CRITICAL/.test(lvl) ? "error" : /WARN/.test(lvl) ? "warn" : "info";
    for (const [t, v] of series.values) {
      const b = buckets[index(Number(t))];
      if (b) b[bucket] += Number(v);
    }
  }
  return { step, buckets };
}
