// Runs Demo Lab scenarios. State lives outside React so a run keeps going (and stays visible)
// while the user moves around the dashboard. One run at a time: scenarios share the platform.

import { useSyncExternalStore } from "react";
import { ApiError, api } from "../../api/client.js";

const RESULTS_KEY = "miniops-lab-results";

let store = { runs: {}, activeId: null };
const listeners = new Set();

function emit(next) {
  store = next;
  listeners.forEach((l) => l());
}

function patchRun(scenarioId, fn) {
  const run = store.runs[scenarioId];
  if (!run) return;
  emit({ ...store, runs: { ...store.runs, [scenarioId]: fn(run) } });
}

function patchStep(scenarioId, index, patch) {
  patchRun(scenarioId, (run) => ({ ...run, steps: run.steps.map((s, i) => (i === index ? { ...s, ...patch } : s)) }));
}

export function useLab() {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => store,
  );
}

export function lastResults() {
  try {
    return JSON.parse(localStorage.getItem(RESULTS_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveResult(scenarioId, result) {
  try {
    localStorage.setItem(RESULTS_KEY, JSON.stringify({ ...lastResults(), [scenarioId]: result }));
  } catch {
    /* storage unavailable: results last for this visit */
  }
}

const controllers = {};

export function abortRun() {
  if (store.activeId) controllers[store.activeId]?.abort();
}

export function clearRun(scenarioId) {
  if (store.activeId === scenarioId) return;
  const runs = { ...store.runs };
  delete runs[scenarioId];
  emit({ ...store, runs });
}

class AssertionFailed extends Error {}

const resolveTitle = (title, policy) => (typeof title === "function" ? title(policy) : title);

export async function runScenario(scenario, { policy, keep = false, onFinish }) {
  if (store.activeId) return;
  const runId = Math.random().toString(36).slice(2, 8);
  const correlationId = `lab-${runId}`;
  const controller = new AbortController();
  controllers[scenario.id] = controller;
  const { signal } = controller;
  const started = Date.now();

  emit({
    activeId: scenario.id,
    runs: {
      ...store.runs,
      [scenario.id]: {
        scenarioId: scenario.id,
        runId,
        correlationId,
        status: "running",
        startedAt: started,
        endedAt: null,
        current: 0,
        steps: scenario.steps.map((s) => ({ title: resolveTitle(s.title, policy), services: s.services, status: "pending" })),
        console: [],
        metrics: [],
        manual: null,
        state: {},
        error: null,
      },
    },
  });

  const log = (text, tone = "info") =>
    patchRun(scenario.id, (run) => {
      const last = run.console[run.console.length - 1];
      // Polling repeats the same request: collapse it into one line with a counter.
      if (last && last.text === text && last.tone === tone) {
        return { ...run, console: [...run.console.slice(0, -1), { ...last, count: (last.count ?? 1) + 1, t: Date.now() }] };
      }
      return { ...run, console: [...run.console.slice(-400), { t: Date.now(), text, tone }] };
    });

  const sleep = (ms) =>
    new Promise((resolve, reject) => {
      const timer = setTimeout(resolve, ms);
      signal.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      }, { once: true });
    });

  let cleaningUp = false; // cleanup must still run after an abort
  const raw = async (path, opts = {}) => {
    const method = opts.method ?? "GET";
    const res = await api(path, { ...opts, raw: true, correlationId, signal: cleaningUp ? undefined : signal });
    log(`${method.padEnd(6)} /api/v1${path}  →  ${res.status} · ${res.ms} ms`, res.status >= 500 ? "error" : res.status >= 400 ? "warn" : "muted");
    return res;
  };

  const call = async (path, opts) => {
    const res = await raw(path, opts);
    if (!res.ok) throw new ApiError(res.status, res.data?.error?.message ?? `HTTP ${res.status}`, res.data?.error?.details, res.correlationId);
    return res.data;
  };

  const cleanups = [];
  const ctx = {
    scenario,
    runId,
    correlationId,
    policy,
    state: {},
    signal,
    log,
    sleep,
    raw,
    call,
    lab: (name, config) => call(`/lab/endpoints/${name}`, { method: "PUT", body: config }),
    expect(condition, message) {
      if (!condition) throw new AssertionFailed(message);
    },
    metric(label, value) {
      patchRun(scenario.id, (run) => ({ ...run, metrics: [...run.metrics.filter(([l]) => l !== label), [label, value]] }));
    },
    manual(command, text) {
      patchRun(scenario.id, (run) => ({ ...run, manual: command ? { command, text } : null }));
    },
    defer(fn, { keepable = false } = {}) {
      cleanups.push({ fn, keepable });
    },
    async waitFor(fn, { timeout = 10_000, interval = 1000, what = "the expected state" } = {}) {
      const deadline = Date.now() + timeout;
      let lastError;
      for (;;) {
        if (signal.aborted) throw new DOMException("Aborted", "AbortError");
        try {
          const value = await fn();
          if (value) return value;
        } catch (err) {
          if (err.name === "AbortError") throw err;
          lastError = err;
        }
        if (Date.now() > deadline) {
          throw new AssertionFailed(`Timed out after ${Math.round(timeout / 1000)} s waiting for ${what}${lastError ? ` (${lastError.message})` : ""}`);
        }
        await sleep(interval);
      }
    },
  };

  log(`Run ${runId} started · correlation ID ${correlationId}`, "accent");
  let status = "passed";
  let error = null;
  for (let i = 0; i < scenario.steps.length; i += 1) {
    const step = scenario.steps[i];
    const t0 = Date.now();
    patchRun(scenario.id, (run) => ({ ...run, current: i }));
    patchStep(scenario.id, i, { status: "running", startedAt: t0 });
    log(`Step ${i + 1}: ${resolveTitle(step.title, policy)}`, "step");
    try {
      const detail = await step.run(ctx);
      patchStep(scenario.id, i, { status: "passed", detail, endedAt: Date.now() });
      patchRun(scenario.id, (run) => ({ ...run, state: { ...ctx.state } }));
    } catch (err) {
      const aborted = err.name === "AbortError";
      status = aborted ? "aborted" : "failed";
      error = aborted ? "Stopped by you" : err instanceof AssertionFailed ? err.message : `${err.message}${err.status ? ` (HTTP ${err.status})` : ""}`;
      patchStep(scenario.id, i, { status: aborted ? "aborted" : "failed", detail: error, endedAt: Date.now() });
      log(aborted ? "Run stopped" : `✗ ${error}`, "error");
      for (let j = i + 1; j < scenario.steps.length; j += 1) patchStep(scenario.id, j, { status: "skipped" });
      break;
    }
  }

  cleaningUp = true;
  patchRun(scenario.id, (run) => ({ ...run, manual: null, cleaning: true }));
  const toRun = cleanups.reverse().filter((c) => !(keep && c.keepable && status === "passed"));
  if (toRun.length) log(`Cleaning up ${toRun.length} lab resource${toRun.length === 1 ? "" : "s"}${keep && status === "passed" ? " (target kept)" : ""}`, "accent");
  for (const c of toRun) {
    try {
      await c.fn();
    } catch {
      /* best effort: a stopped service may refuse; the resource is labelled "Lab" */
    }
  }
  // Lab incidents notify like real ones; keep them out of the unread count.
  try {
    const unread = await api("/notifications?unread_only=true&limit=500", { correlationId });
    const mine = unread.filter((n) => n.title.includes(runId));
    await Promise.all(mine.map((n) => api(`/notifications/${n.id}/read`, { method: "PATCH", correlationId })));
    if (mine.length) log(`Marked ${mine.length} lab notification${mine.length === 1 ? "" : "s"} as read`, "muted");
  } catch {
    /* Notification Service unavailable: they stay unread */
  }

  const endedAt = Date.now();
  const passed = store.runs[scenario.id].steps.filter((s) => s.status === "passed").length;
  log(status === "passed" ? `✓ Hypothesis confirmed in ${((endedAt - started) / 1000).toFixed(1)} s` : `Run ${status}`, status === "passed" ? "success" : "error");
  patchRun(scenario.id, (run) => ({ ...run, status, error, endedAt, cleaning: false, state: { ...ctx.state } }));
  saveResult(scenario.id, { status, endedAt, durationMs: endedAt - started, passed, total: scenario.steps.length, runId });
  delete controllers[scenario.id];
  emit({ ...store, activeId: null });
  onFinish?.();
}
