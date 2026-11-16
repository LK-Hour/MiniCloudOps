// Demo Lab scenarios: experiments run against the live platform, step by step.
//
// Each step is an async function that receives the run context (see Scenarios.jsx: makeContext):
//   ctx.call(path, opts)      gateway call tagged with the run's correlation ID; throws on HTTP errors
//   ctx.raw(path, opts)       same, never throws: {status, ok, data, correlationId, ms}
//   ctx.waitFor(fn, opts)     poll fn until it returns something truthy
//   ctx.expect(cond, msg)     assertion; a false condition fails the step
//   ctx.log / ctx.metric / ctx.defer / ctx.manual / ctx.state / ctx.policy
// A step returns a short detail string shown under its title.
//
// Lab targets use a 1-hour check interval, so after the scheduler's first check every further
// check is triggered by the scenario itself and the results are deterministic.

import { queryLogs } from "../../lib/logs.js";

const LAB_INTERVAL = 3600;

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

// --- shared steps --------------------------------------------------------------------------------

/** Sandbox endpoint + registered target, and wait for the scheduler's first (healthy) check. */
function provision(label) {
  return [
    {
      title: "Provision a sandbox endpoint and register it as a target",
      services: ["target"],
      run: async (ctx) => {
        const endpoint = `lab-${ctx.runId}-${label}`;
        await ctx.lab(endpoint, { mode: "healthy" });
        ctx.defer(() => ctx.raw(`/lab/endpoints/${endpoint}`, { method: "DELETE" }));
        const target = await ctx.call("/targets", {
          method: "POST",
          body: {
            name: `Lab · ${ctx.scenario.short} · ${ctx.runId}`,
            target_url: `http://demo-app/${endpoint}/health`,
            check_interval: LAB_INTERVAL,
          },
        });
        ctx.defer(() => ctx.raw(`/targets/${target.id}`, { method: "DELETE" }), { keepable: true });
        Object.assign(ctx.state, { endpoint, target });
        return `${target.target_url} → target ${target.id.slice(0, 8)}`;
      },
    },
    {
      title: "Monitoring Service discovers the target on its next scheduler tick",
      services: ["monitoring"],
      run: async (ctx) => {
        const started = Date.now();
        const status = await ctx.waitFor(
          async () => {
            const s = await ctx.raw(`/monitoring/targets/${ctx.state.target.id}/status`);
            return s.ok && s.data.last_checked_at ? s.data : null;
          },
          { timeout: (ctx.policy.scheduler_tick_seconds + 10) * 1000, what: "the first scheduled check" },
        );
        ctx.expect(status.status === "UP", `expected UP, got ${status.status}`);
        ctx.metric("Discovery", `${((Date.now() - started) / 1000).toFixed(1)} s`);
        return `First check UP in ${Math.round(status.last_response_time_ms)} ms`;
      },
    },
  ];
}

const inject = (title, config) => ({
  title,
  services: ["lab"],
  run: async (ctx) => {
    await ctx.lab(ctx.state.endpoint, typeof config === "function" ? config(ctx) : config);
    ctx.state.faultAt = Date.now();
    const c = typeof config === "function" ? config(ctx) : config;
    return c.mode === "down" ? `Endpoint now answers HTTP ${c.status_code ?? 503}` : c.mode === "healthy" ? "Endpoint answers 200 OK" : `mode=${c.mode}${c.latency_ms ? ` · ${c.latency_ms} ms` : ""}`;
  },
});

async function check(ctx) {
  const result = await ctx.call(`/monitoring/check/${ctx.state.target.id}`, { method: "POST" });
  const status = await ctx.call(`/monitoring/targets/${ctx.state.target.id}/status`);
  return { result, status };
}

/** Fail checks until the incident opens (at most threshold + 1 checks). */
const detectOutage = {
  title: (p) => `Detect: ${p.failure_threshold} consecutive failed checks open an incident`,
  services: ["monitoring", "incident"],
  run: async (ctx) => {
    const threshold = ctx.policy.failure_threshold;
    let status;
    for (let i = 1; i <= threshold + 1; i += 1) {
      const out = await check(ctx);
      status = out.status;
      ctx.log(`Check ${i}: ${out.result.status}${out.result.status_code ? ` (HTTP ${out.result.status_code})` : ""} · failures ${status.consecutive_failures}/${threshold}`, out.result.status === "UP" ? "info" : "warn");
      if (status.open_incident_id) break;
    }
    ctx.expect(status.open_incident_id, "no incident was opened");
    ctx.expect(status.consecutive_failures === threshold, `incident opened after ${status.consecutive_failures} failures, expected ${threshold}`);
    ctx.state.incidentId = status.open_incident_id;
    ctx.metric("Time to detect", `${((Date.now() - ctx.state.faultAt) / 1000).toFixed(1)} s`);
    ctx.metric("At 30 s interval", `≈ ${threshold * 30} s`);
    return `Incident ${status.open_incident_id.slice(0, 8)} opened after ${plural(threshold, "failure")}`;
  },
};

const notificationDelivered = (eventType) => ({
  title: `Notification Service stores ${eventType}`,
  services: ["incident", "notification"],
  run: async (ctx) => {
    const n = await ctx.waitFor(
      async () => {
        const list = await ctx.call(`/notifications?incident_id=${ctx.state.incidentId}`);
        return list.find((x) => x.event_type === eventType);
      },
      { timeout: 20_000, what: `a ${eventType} notification` },
    );
    return `"${n.title}"`;
  },
});

const recover = {
  title: "Recover: the next passing check resolves the incident automatically",
  services: ["monitoring", "incident"],
  run: async (ctx) => {
    const { result, status } = await check(ctx);
    ctx.expect(result.status === "UP", `check returned ${result.status}`);
    ctx.expect(status.consecutive_failures === 0, "failure counter was not reset");
    const incident = await ctx.waitFor(
      async () => {
        const i = await ctx.call(`/incidents/${ctx.state.incidentId}`);
        return i.status === "RESOLVED" ? i : null;
      },
      { timeout: 15_000, what: "the incident to resolve" },
    );
    const outage = new Date(incident.resolved_at) - new Date(incident.created_at);
    ctx.metric("Outage duration", `${(outage / 1000).toFixed(1)} s`);
    return `Resolved ${((Date.now() - ctx.state.faultAt) / 1000).toFixed(1)} s after the repair`;
  },
};

const LOG_SERVICES = ["target-service", "monitoring-service", "incident-service", "notification-service"];

const traced = (minServices) => ({
  title: "Trace: the run's correlation ID appears in every service's logs",
  services: ["target", "monitoring", "incident", "notification"],
  run: async (ctx) => {
    const lines = await ctx.waitFor(
      async () => {
        const found = await queryLogs({ query: `{compose_project="miniops"} != "/api/v1/logs/" |= "${ctx.correlationId}"`, seconds: 900, limit: 500 });
        const services = new Set(found.map((l) => l.service).filter((s) => LOG_SERVICES.includes(s)));
        return services.size >= minServices ? found : null;
      },
      { timeout: 30_000, interval: 2500, what: `log lines from ${minServices} services in Loki` },
    );
    const services = [...new Set(lines.map((l) => l.service))].sort();
    ctx.metric("Log lines traced", lines.length);
    ctx.state.traceReady = true;
    return services.join(" · ");
  },
});

const repairStep = inject("Repair: the endpoint answers 200 OK again", { mode: "healthy" });

async function expectStatus(ctx, path, opts, expected) {
  const res = await ctx.raw(path, opts);
  ctx.expect(res.status === expected, `expected HTTP ${expected}, got ${res.status}${res.data?.error ? `: ${res.data.error.message}` : ""}`);
  return res;
}

// --- scenarios -----------------------------------------------------------------------------------

export const SCENARIOS = [
  {
    id: "outage",
    short: "Outage",
    title: "Outage detection & recovery",
    category: "End-to-end",
    summary: "Break a monitored app and follow the outage through every service, from the failed checks to the resolution notice.",
    hypothesis: (p) =>
      `When a target fails ${p.failure_threshold} checks in a row, exactly one CRITICAL incident opens and a notification is stored; the first passing check resolves it and sends a second notification.`,
    services: ["target", "monitoring", "incident", "notification"],
    estimate: "~15 s",
    steps: [
      ...provision("outage"),
      inject("Inject fault: the endpoint answers HTTP 503", { mode: "down", status_code: 503 }),
      detectOutage,
      {
        title: "Incident Service holds one OPEN, CRITICAL incident for the target",
        services: ["incident"],
        run: async (ctx) => {
          const list = await ctx.call(`/incidents?target_id=${ctx.state.target.id}`);
          ctx.expect(list.length === 1, `expected 1 incident, found ${list.length}`);
          ctx.expect(list[0].status === "OPEN" && list[0].severity === "CRITICAL", `got ${list[0].status} ${list[0].severity}`);
          return list[0].title;
        },
      },
      notificationDelivered("INCIDENT_CREATED"),
      {
        title: "Target Service shows the target as DOWN",
        services: ["target"],
        run: async (ctx) => {
          const t = await ctx.call(`/targets/${ctx.state.target.id}`);
          ctx.expect(t.status === "DOWN", `status is ${t.status}`);
          return "Status reported by the Monitoring Service over the internal API";
        },
      },
      repairStep,
      recover,
      notificationDelivered("INCIDENT_RESOLVED"),
      {
        title: "The incident's audit trail is complete",
        services: ["incident"],
        run: async (ctx) => {
          const events = await ctx.call(`/incidents/${ctx.state.incidentId}/history`);
          const types = events.map((e) => e.event_type);
          for (const t of ["CREATED", "RESOLVED"]) ctx.expect(types.includes(t), `missing ${t} event`);
          ctx.expect(types.filter((t) => t === "NOTIFICATION_SENT").length >= 1, "no NOTIFICATION_SENT event");
          return types.join(" → ");
        },
      },
      traced(4),
    ],
  },
  {
    id: "debounce",
    short: "Debounce",
    title: "Alert debouncing",
    category: "End-to-end",
    summary: "Short blips must not page anyone. Fail the target just under the threshold, twice, with a recovery in between.",
    hypothesis: (p) =>
      `${plural(p.failure_threshold - 1, "failure")} in a row never open an incident, and one passing check resets the counter to zero.`,
    services: ["target", "monitoring", "incident"],
    estimate: "~10 s",
    steps: [
      ...provision("debounce"),
      inject("Inject fault: the endpoint answers HTTP 500", { mode: "down", status_code: 500 }),
      {
        title: (p) => `Blip 1: ${plural(p.failure_threshold - 1, "failed check")}, no incident`,
        services: ["monitoring"],
        run: async (ctx) => {
          const n = ctx.policy.failure_threshold - 1;
          let status;
          for (let i = 1; i <= n; i += 1) ({ status } = await check(ctx));
          ctx.expect(status.consecutive_failures === n, `counter is ${status.consecutive_failures}, expected ${n}`);
          ctx.expect(!status.open_incident_id, "an incident was opened");
          return `failures ${n}/${ctx.policy.failure_threshold} · status ${status.status}`;
        },
      },
      repairStep,
      {
        title: "One passing check resets the failure counter",
        services: ["monitoring"],
        run: async (ctx) => {
          const { result, status } = await check(ctx);
          ctx.expect(result.status === "UP" && status.consecutive_failures === 0, `counter is ${status.consecutive_failures}`);
          return "failures 0 · status UP";
        },
      },
      inject("Inject the fault again", { mode: "down", status_code: 500 }),
      {
        title: (p) => `Blip 2: another ${plural(p.failure_threshold - 1, "failed check")}, still no incident`,
        services: ["monitoring"],
        run: async (ctx) => {
          const n = ctx.policy.failure_threshold - 1;
          let status;
          for (let i = 1; i <= n; i += 1) ({ status } = await check(ctx));
          ctx.expect(status.consecutive_failures === n, `counter is ${status.consecutive_failures}`);
          ctx.expect(!status.open_incident_id, "an incident was opened");
          return `failures ${n}/${ctx.policy.failure_threshold}: the count restarted after the recovery`;
        },
      },
      {
        title: "No incident exists for the target",
        services: ["incident"],
        run: async (ctx) => {
          const list = await ctx.call(`/incidents?target_id=${ctx.state.target.id}`);
          ctx.expect(list.length === 0, `found ${list.length} incident(s)`);
          ctx.metric("Blips suppressed", 2);
          ctx.metric("Failed checks", (ctx.policy.failure_threshold - 1) * 2);
          return "Nobody was paged";
        },
      },
    ],
  },
  {
    id: "latency",
    short: "Latency",
    title: "Latency & timeouts",
    category: "End-to-end",
    summary: "Slow is not the same as down. Push response time over the warning threshold, then past the request timeout.",
    hypothesis: (p) =>
      `A response slower than ${p.response_time_threshold_ms} ms is still UP but logged as a warning; no answer within ${p.check_timeout_seconds} s is a failed check.`,
    services: ["monitoring"],
    estimate: "~20 s",
    steps: [
      ...provision("latency"),
      inject(
        (ctx) => "Inject latency above the response-time threshold",
        (ctx) => ({ mode: "slow", latency_ms: Math.min(ctx.policy.response_time_threshold_ms + 600, ctx.policy.check_timeout_seconds * 1000 - 1200) }),
      ),
      {
        title: "Slow but available: the check is UP",
        services: ["monitoring"],
        run: async (ctx) => {
          const { result } = await check(ctx);
          ctx.expect(result.status === "UP", `check returned ${result.status}: ${result.error}`);
          ctx.expect(result.response_time_ms >= ctx.policy.response_time_threshold_ms, `only ${Math.round(result.response_time_ms)} ms`);
          ctx.metric("Slow response", `${Math.round(result.response_time_ms)} ms`);
          return `UP in ${Math.round(result.response_time_ms)} ms (threshold ${ctx.policy.response_time_threshold_ms} ms)`;
        },
      },
      {
        title: "The Monitoring Service logs a “Slow response” warning",
        services: ["monitoring"],
        run: async (ctx) => {
          const lines = await ctx.waitFor(
            async () => {
              const found = await queryLogs({
                query: `{service="monitoring-service"} |= "${ctx.state.target.id}" |= "Slow response"`,
                seconds: 600,
                limit: 5,
              });
              return found.length ? found : null;
            },
            { timeout: 30_000, interval: 2500, what: "the warning in Loki" },
          );
          return `${lines[0].level} · ${lines[0].message}`;
        },
      },
      inject(
        () => "Inject latency beyond the check timeout",
        (ctx) => ({ mode: "slow", latency_ms: ctx.policy.check_timeout_seconds * 1000 + 1500 }),
      ),
      {
        title: "No answer in time: the check fails with a timeout",
        services: ["monitoring"],
        run: async (ctx) => {
          const { result, status } = await check(ctx);
          ctx.expect(result.status === "DOWN", `check returned ${result.status}`);
          ctx.expect(/timed out/i.test(result.error ?? ""), `error was: ${result.error}`);
          ctx.expect(status.consecutive_failures === 1, `counter is ${status.consecutive_failures}`);
          ctx.metric("Timeout", `${ctx.policy.check_timeout_seconds} s`);
          return `DOWN · ${result.error} · failures 1/${ctx.policy.failure_threshold}`;
        },
      },
      repairStep,
      {
        title: "Back to normal",
        services: ["monitoring"],
        run: async (ctx) => {
          const { result } = await check(ctx);
          ctx.expect(result.status === "UP", `check returned ${result.status}`);
          return `UP in ${Math.round(result.response_time_ms)} ms`;
        },
      },
    ],
  },
  {
    id: "flaky",
    short: "Flaky",
    title: "Intermittent errors",
    category: "End-to-end",
    summary: "A randomly failing endpoint. Whatever the dice say, incidents must match the failure streaks exactly.",
    hypothesis: (p) =>
      `With 60% of requests failing, an incident opens once per streak of ${p.failure_threshold} or more failures and resolves on the next success; isolated failures are ignored.`,
    services: ["monitoring", "incident"],
    estimate: "~10 s",
    steps: [
      ...provision("flaky"),
      inject("Inject fault: 60% of requests answer HTTP 502", { mode: "flaky", status_code: 502, error_rate: 0.6 }),
      {
        title: "Run 15 health checks",
        services: ["monitoring"],
        run: async (ctx) => {
          const results = [];
          for (let i = 0; i < 15; i += 1) {
            const { result } = await check(ctx);
            results.push(result.status);
          }
          ctx.state.results = results;
          ctx.log(`Results: ${results.map((r) => (r === "UP" ? "▮" : "▯")).join("")}  (▮ up · ▯ down)`);
          const up = results.filter((r) => r === "UP").length;
          ctx.metric("Availability", `${Math.round((up / results.length) * 100)}%`);
          return `${up} up · ${results.length - up} down`;
        },
      },
      {
        title: "Incidents match the failure streaks",
        services: ["incident"],
        run: async (ctx) => {
          const threshold = ctx.policy.failure_threshold;
          let streak = 0;
          let expected = 0;
          for (const r of ctx.state.results) {
            streak = r === "UP" ? 0 : streak + 1;
            if (streak === threshold) expected += 1;
          }
          const stillOpen = streak >= threshold;
          const list = await ctx.call(`/incidents?target_id=${ctx.state.target.id}`);
          ctx.metric("Incidents", list.length);
          ctx.expect(list.length === expected, `expected ${expected} incident(s) from the streaks, found ${list.length}`);
          const open = list.filter((i) => i.status !== "RESOLVED").length;
          ctx.expect(open === (stillOpen ? 1 : 0), `${open} incident(s) still open`);
          return expected
            ? `${plural(expected, "streak")} of ≥${threshold} failures → ${plural(expected, "incident")}${stillOpen ? " (last one still open)" : ""}`
            : `No streak reached ${threshold} failures → no incident`;
        },
      },
      repairStep,
      {
        title: "A passing check closes anything still open",
        services: ["monitoring", "incident"],
        run: async (ctx) => {
          await check(ctx);
          const open = await ctx.waitFor(
            async () => {
              const list = await ctx.call(`/incidents?target_id=${ctx.state.target.id}`);
              return list.every((i) => i.status === "RESOLVED") ? list : null;
            },
            { timeout: 10_000, what: "all incidents to resolve" },
          );
          return `${plural(open.length, "incident")}, all RESOLVED`;
        },
      },
    ],
  },
  {
    id: "contract",
    short: "Contract",
    title: "Idempotency & state machine",
    category: "API contract",
    summary: "Retries must be safe. Repeat calls, try illegal transitions and check that nothing is duplicated.",
    hypothesis: () =>
      "Reporting the same outage twice returns the existing incident; statuses only move forward; each incident event produces exactly one notification.",
    services: ["incident", "notification"],
    estimate: "~5 s",
    steps: [
      {
        title: "Report an outage: 201 Created",
        services: ["incident"],
        run: async (ctx) => {
          ctx.state.fakeTarget = `lab-${ctx.runId}`;
          const res = await expectStatus(ctx, "/incidents", {
            method: "POST",
            body: { target_id: ctx.state.fakeTarget, title: `[Lab] Contract test ${ctx.runId}`, severity: "WARNING", description: "Created by the Demo Lab" },
          }, 201);
          ctx.state.incidentId = res.data.id;
          ctx.defer(() => ctx.raw(`/incidents/${res.data.id}/status`, { method: "PATCH", body: { status: "RESOLVED", note: "Demo Lab cleanup" } }));
          return `Incident ${res.data.id.slice(0, 8)} · ${res.ms} ms`;
        },
      },
      {
        title: "Report it again: 200 OK with the same incident",
        services: ["incident"],
        run: async (ctx) => {
          const res = await expectStatus(ctx, "/incidents", {
            method: "POST",
            body: { target_id: ctx.state.fakeTarget, title: "[Lab] duplicate report", severity: "CRITICAL" },
          }, 200);
          ctx.expect(res.data.id === ctx.state.incidentId, "a different incident was returned");
          return "Duplicate suppressed (partial unique index: one unresolved incident per target)";
        },
      },
      {
        title: "Acknowledge twice: the second call is a no-op",
        services: ["incident"],
        run: async (ctx) => {
          const path = `/incidents/${ctx.state.incidentId}/status`;
          await expectStatus(ctx, path, { method: "PATCH", body: { status: "ACKNOWLEDGED", note: "on it" } }, 200);
          await expectStatus(ctx, path, { method: "PATCH", body: { status: "ACKNOWLEDGED" } }, 200);
          const events = await ctx.call(`/incidents/${ctx.state.incidentId}/history`);
          const acks = events.filter((e) => e.event_type === "ACKNOWLEDGED").length;
          ctx.expect(acks === 1, `${acks} ACKNOWLEDGED events recorded`);
          return "1 ACKNOWLEDGED event in the history";
        },
      },
      {
        title: "Move backwards to OPEN: 409 Conflict",
        services: ["incident"],
        run: async (ctx) => {
          const res = await expectStatus(ctx, `/incidents/${ctx.state.incidentId}/status`, { method: "PATCH", body: { status: "OPEN" } }, 409);
          return res.data.error.message;
        },
      },
      {
        title: "Resolve, then try to re-acknowledge: 409 Conflict",
        services: ["incident"],
        run: async (ctx) => {
          const path = `/incidents/${ctx.state.incidentId}/status`;
          await expectStatus(ctx, path, { method: "PATCH", body: { status: "RESOLVED", note: "Demo Lab" } }, 200);
          const res = await expectStatus(ctx, path, { method: "PATCH", body: { status: "ACKNOWLEDGED" } }, 409);
          return res.data.error.message;
        },
      },
      {
        title: "Exactly one notification per incident event",
        services: ["notification"],
        run: async (ctx) => {
          const list = await ctx.waitFor(
            async () => {
              const l = await ctx.call(`/notifications?incident_id=${ctx.state.incidentId}`);
              return l.some((n) => n.event_type === "INCIDENT_RESOLVED") ? l : null;
            },
            { timeout: 15_000, what: "both notifications" },
          );
          const created = list.filter((n) => n.event_type === "INCIDENT_CREATED").length;
          const resolved = list.filter((n) => n.event_type === "INCIDENT_RESOLVED").length;
          ctx.expect(created === 1 && resolved === 1, `${created} created, ${resolved} resolved`);
          ctx.state.notification = list.find((n) => n.event_type === "INCIDENT_CREATED");
          return "1 × INCIDENT_CREATED · 1 × INCIDENT_RESOLVED";
        },
      },
      {
        title: "Replay a notification: 200 OK, deduplicated",
        services: ["notification"],
        run: async (ctx) => {
          const n = ctx.state.notification;
          const res = await expectStatus(ctx, "/notifications", {
            method: "POST",
            body: { incident_id: n.incident_id, event_type: n.event_type, severity: n.severity, title: n.title, message: n.message },
          }, 200);
          ctx.expect(res.data.id === n.id, "a new notification was stored");
          ctx.metric("Duplicates stored", 0);
          return `dedup_key ${n.incident_id.slice(0, 8)}…:${n.event_type}`;
        },
      },
    ],
  },
  {
    id: "security",
    short: "Security",
    title: "Security guardrails",
    category: "Security",
    summary: "Try to make the monitor attack its own network (SSRF), send bad input, and reach internal-only routes.",
    hypothesis: () =>
      "Unsafe target URLs and invalid input are rejected with 422 and the standard error body; internal routes are not reachable through the gateway; nothing is stored.",
    services: ["target", "gateway"],
    estimate: "~3 s",
    steps: [
      ...[
        ["Cloud metadata endpoint", "http://169.254.169.254/latest/meta-data/"],
        ["Loopback address", "http://127.0.0.1:8000/health"],
        ["Platform database by container name", "http://postgres:5432/"],
        ["Non-HTTP scheme", "ftp://example.com/file"],
        ["Credentials embedded in the URL", "http://admin:secret@demo-app/"],
      ].map(([what, url]) => ({
        title: `Reject ${what.toLowerCase()}`,
        services: ["target"],
        run: async (ctx) => {
          const res = await expectStatus(ctx, "/targets", { method: "POST", body: { name: `Lab · SSRF ${ctx.runId}`, target_url: url } }, 422);
          ctx.expect(res.data?.error?.correlation_id === ctx.correlationId, "error body lacks the correlation ID");
          const field = res.data.error.details?.[0];
          return `${url} → 422 · ${field?.message ?? res.data.error.message}`;
        },
      })),
      {
        title: "Reject a 1-second check interval (field-level error)",
        services: ["target"],
        run: async (ctx) => {
          const res = await expectStatus(ctx, "/targets", { method: "POST", body: { name: "", target_url: "http://demo-app/", check_interval: 1 } }, 422);
          const fields = (res.data.error.details ?? []).map((d) => d.field);
          ctx.expect(fields.some((f) => f.includes("check_interval")) && fields.some((f) => f.includes("name")), `fields: ${fields.join(", ")}`);
          return fields.join(" · ");
        },
      },
      {
        title: "Internal status route is hidden by the gateway",
        services: ["gateway"],
        run: async (ctx) => {
          await expectStatus(ctx, "/targets/anything/status", { method: "PATCH", body: { status: "UP" } }, 404);
          return "PATCH /api/v1/targets/{id}/status → 404 from the edge";
        },
      },
      {
        title: "Log search is read-only",
        services: ["gateway"],
        run: async (ctx) => {
          await expectStatus(ctx, "/logs/labels", { method: "POST" }, 403);
          return "POST /api/v1/logs/* → 403";
        },
      },
      {
        title: "Nothing was stored",
        services: ["target"],
        run: async (ctx) => {
          const targets = await ctx.call("/targets?limit=500");
          const leaked = targets.filter((t) => t.name.includes(ctx.runId));
          for (const t of leaked) ctx.defer(() => ctx.raw(`/targets/${t.id}`, { method: "DELETE" }));
          ctx.expect(leaked.length === 0, `${leaked.length} target(s) were created`);
          ctx.metric("Attacks blocked", 8);
          return "0 targets created";
        },
      },
    ],
  },
  {
    id: "notification-down",
    short: "Notify outage",
    title: "Notification Service outage",
    category: "Resilience",
    manual: true,
    summary: "Stop a downstream service mid-incident. The incident must still be saved, and the failure recorded.",
    hypothesis: () =>
      "With the Notification Service down, incidents still open; the failed delivery is recorded in the incident's history, and later notifications go through once it is back.",
    services: ["monitoring", "incident", "notification"],
    estimate: "~1 min · needs a terminal",
    steps: [
      {
        title: "Stop the Notification Service",
        services: ["notification"],
        run: async (ctx) => {
          ctx.manual("docker compose stop notification-service", "Run this in the project folder. The lab continues once the service stops answering.");
          await ctx.waitFor(async () => (await ctx.raw("/notifications?limit=1")).status >= 500, { timeout: 300_000, interval: 1500, what: "the service to stop" });
          ctx.manual(null);
          return "Gateway answers 503 for /api/v1/notifications";
        },
      },
      ...provision("notify"),
      inject("Inject fault: the endpoint answers HTTP 503", { mode: "down", status_code: 503 }),
      detectOutage,
      {
        title: "The failed delivery is recorded on the incident",
        services: ["incident"],
        run: async (ctx) => {
          const event = await ctx.waitFor(
            async () => (await ctx.call(`/incidents/${ctx.state.incidentId}/history`)).find((e) => e.event_type === "NOTIFICATION_FAILED"),
            { timeout: 45_000, interval: 2000, what: "a NOTIFICATION_FAILED event (after retries)" },
          );
          return event.message;
        },
      },
      {
        title: "Start the Notification Service again",
        services: ["notification"],
        run: async (ctx) => {
          ctx.manual("docker compose start notification-service", "The lab continues once the service answers again.");
          await ctx.waitFor(async () => (await ctx.raw("/notifications?limit=1")).ok, { timeout: 300_000, interval: 1500, what: "the service to start" });
          ctx.manual(null);
          return "Back online";
        },
      },
      repairStep,
      recover,
      notificationDelivered("INCIDENT_RESOLVED"),
    ],
  },
  {
    id: "incident-down",
    short: "Incident outage",
    title: "Incident Service outage",
    category: "Resilience",
    manual: true,
    summary: "Take the Incident Service away while a target is failing. Monitoring must keep working and catch up afterwards.",
    hypothesis: () =>
      "Health checks keep running without the Incident Service; the incident is opened on the first failed check after it returns.",
    services: ["monitoring", "incident"],
    estimate: "~1 min · needs a terminal",
    steps: [
      ...provision("incsvc"),
      {
        title: "Stop the Incident Service",
        services: ["incident"],
        run: async (ctx) => {
          ctx.manual("docker compose stop incident-service", "Run this in the project folder. The lab continues once the service stops answering.");
          await ctx.waitFor(async () => (await ctx.raw("/incidents?limit=1")).status >= 500, { timeout: 300_000, interval: 1500, what: "the service to stop" });
          ctx.manual(null);
          return "Gateway answers 503 for /api/v1/incidents";
        },
      },
      inject("Inject fault: the endpoint answers HTTP 503", { mode: "down", status_code: 503 }),
      {
        title: (p) => `Checks keep running: ${p.failure_threshold + 1} failures recorded, no incident possible`,
        services: ["monitoring"],
        run: async (ctx) => {
          const n = ctx.policy.failure_threshold + 1;
          let status;
          for (let i = 1; i <= n; i += 1) ({ status } = await check(ctx));
          ctx.expect(status.status === "DOWN" && status.consecutive_failures === n, `counter ${status.consecutive_failures}`);
          ctx.expect(!status.open_incident_id, "an incident id was stored");
          return `failures ${n} · “Could not open incident; will retry” logged`;
        },
      },
      {
        title: "Start the Incident Service again",
        services: ["incident"],
        run: async (ctx) => {
          ctx.manual("docker compose start incident-service", "The lab continues once the service answers again.");
          await ctx.waitFor(async () => (await ctx.raw("/incidents?limit=1")).ok, { timeout: 300_000, interval: 1500, what: "the service to start" });
          ctx.manual(null);
          return "Back online";
        },
      },
      {
        title: "The next failed check opens the incident",
        services: ["monitoring", "incident"],
        run: async (ctx) => {
          const { status } = await check(ctx);
          ctx.expect(status.open_incident_id, "still no incident");
          ctx.state.incidentId = status.open_incident_id;
          return `Incident ${status.open_incident_id.slice(0, 8)} opened on retry`;
        },
      },
      repairStep,
      recover,
    ],
  },
];

export const CATEGORIES = [...new Set(SCENARIOS.map((s) => s.category))];
