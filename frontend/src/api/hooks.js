import { useMemo } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSettings } from "../lib/settings.jsx";
import { queryLogs, queryVolume } from "../lib/logs.js";
import { api } from "./client.js";

/** Polling interval from the user's refresh setting. `factor` slows heavier queries down.
 * TanStack Query also pauses polling while the browser tab is hidden. */
function useInterval(factor = 1) {
  const seconds = useSettings().settings.refreshSeconds;
  return seconds ? seconds * 1000 * factor : false;
}

export const keys = {
  targets: ["targets"],
  monitorOverview: ["monitoring", "targets"],
  targetStatus: (id) => ["monitoring", "status", id],
  targetHistory: (id) => ["monitoring", "history", id],
  incidents: ["incidents"],
  incidentHistory: (id) => ["incidents", id, "history"],
  notifications: ["notifications"],
  infrastructure: ["monitoring", "infrastructure"],
  policy: ["monitoring", "config"],
  channels: ["notifications", "channels"],
  spec: (service) => ["openapi", service],
  lab: ["lab", "endpoints"],
  logs: (q, seconds) => ["logs", q, seconds],
  volume: (q, seconds) => ["logs", "volume", q, seconds],
  runs: (repo) => ["github", repo, "runs"],
  jobs: (repo, runId) => ["github", repo, "jobs", runId],
};

export const SERVICES = ["target", "monitoring", "incident", "notification"];

// --- reads ------------------------------------------------------------------------------------

export const useTargets = () =>
  useQuery({ queryKey: keys.targets, queryFn: ({ signal }) => api("/targets?limit=500", { signal }), refetchInterval: useInterval() });

export const useMonitorOverview = () =>
  useQuery({
    queryKey: keys.monitorOverview,
    queryFn: ({ signal }) => api("/monitoring/targets?recent=30", { signal }),
    refetchInterval: useInterval(),
  });

export const useTargetStatus = (id) =>
  useQuery({
    queryKey: keys.targetStatus(id),
    queryFn: ({ signal }) => api(`/monitoring/targets/${id}/status`, { signal }),
    enabled: Boolean(id),
    refetchInterval: useInterval(),
  });

export const useTargetHistory = (id) =>
  useQuery({
    queryKey: keys.targetHistory(id),
    queryFn: ({ signal }) => api(`/monitoring/targets/${id}/history?limit=60`, { signal }),
    enabled: Boolean(id),
    refetchInterval: useInterval(),
  });

export const useIncidents = () =>
  useQuery({ queryKey: keys.incidents, queryFn: ({ signal }) => api("/incidents?limit=500", { signal }), refetchInterval: useInterval() });

export const useIncidentHistory = (id) =>
  useQuery({
    queryKey: keys.incidentHistory(id),
    queryFn: ({ signal }) => api(`/incidents/${id}/history`, { signal }),
    enabled: Boolean(id),
    refetchInterval: useInterval(2),
  });

export const useNotifications = () =>
  useQuery({
    queryKey: keys.notifications,
    queryFn: ({ signal }) => api("/notifications?limit=500", { signal }),
    refetchInterval: useInterval(),
  });

export const useInfrastructure = () =>
  useQuery({
    queryKey: keys.infrastructure,
    queryFn: ({ signal }) => api("/monitoring/infrastructure", { signal }),
    refetchInterval: useInterval(2),
  });

export const usePolicy = () =>
  useQuery({ queryKey: keys.policy, queryFn: ({ signal }) => api("/monitoring/config", { signal }), staleTime: 60_000 });

export const useChannels = () =>
  useQuery({ queryKey: keys.channels, queryFn: ({ signal }) => api("/notifications/channels", { signal }), staleTime: 60_000 });

/** A service's OpenAPI document, served by the gateway at /api/docs/<service>-service.json */
async function fetchSpec(service, signal) {
  const response = await fetch(`/api/docs/${service}-service.json`, { signal, headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`${service}-service: HTTP ${response.status}`);
  return response.json();
}

export const useSpec = (service) =>
  useQuery({ queryKey: keys.spec(service), queryFn: ({ signal }) => fetchSpec(service, signal), staleTime: 300_000, retry: 0 });

export const useSpecs = () =>
  useQueries({
    queries: SERVICES.map((service) => ({
      queryKey: keys.spec(service),
      queryFn: ({ signal }) => fetchSpec(service, signal),
      staleTime: 300_000,
      retry: 0,
    })),
  });

/** Demo Lab sandbox endpoints. 503 means the sandbox isn't running (`make demo`). */
export const useLabEndpoints = () =>
  useQuery({
    queryKey: keys.lab,
    queryFn: ({ signal }) => api("/lab/endpoints", { signal }),
    refetchInterval: useInterval(),
    retry: 0,
  });

/** Loki log lines (newest first). `live` polls at the refresh setting. */
export function useLogs({ query, seconds, limit = 300, live = true, enabled = true }) {
  const interval = useInterval();
  return useQuery({
    queryKey: [...keys.logs(query, seconds), limit],
    queryFn: ({ signal }) => queryLogs({ query, seconds, limit, signal }),
    refetchInterval: live ? interval : false,
    placeholderData: (previous) => previous,
    retry: 0,
    enabled,
  });
}

export function useLogVolume({ query, seconds, live = true }) {
  const interval = useInterval(2);
  return useQuery({
    queryKey: keys.volume(query, seconds),
    queryFn: ({ signal }) => queryVolume({ query, seconds, signal }),
    refetchInterval: live ? interval : false,
    placeholderData: (previous) => previous,
    retry: 0,
  });
}

// --- GitHub Actions (public API, called from the browser; 60 requests/hour without a token) ----

export const REPO_PATTERN = /^[\w.-]+\/[\w.-]+$/;

async function github(path, signal) {
  const response = await fetch(`https://api.github.com${path}`, {
    signal,
    headers: { Accept: "application/vnd.github+json" },
  });
  if (!response.ok) {
    const remaining = response.headers.get("x-ratelimit-remaining");
    const message =
      response.status === 404
        ? "Repository not found, or it is private"
        : remaining === "0"
          ? "GitHub rate limit reached (60 requests/hour); try again later"
          : `GitHub answered HTTP ${response.status}`;
    throw new Error(message);
  }
  return response.json();
}

export const useGithubRuns = (repo) =>
  useQuery({
    queryKey: keys.runs(repo),
    queryFn: ({ signal }) => github(`/repos/${repo}/actions/workflows/ci-cd.yml/runs?per_page=12`, signal),
    enabled: REPO_PATTERN.test(repo ?? ""),
    staleTime: 60_000,
    refetchInterval: 120_000,
    retry: 0,
  });

export const useGithubJobs = (repo, runId) =>
  useQuery({
    queryKey: keys.jobs(repo, runId),
    queryFn: ({ signal }) => github(`/repos/${repo}/actions/runs/${runId}/jobs?per_page=30`, signal),
    enabled: Boolean(runId) && REPO_PATTERN.test(repo ?? ""),
    staleTime: 60_000,
    retry: 0,
  });

/**
 * Targets joined with their monitoring state. Each row:
 * { ...target, monitor: {status, consecutive_failures, last_response_time_ms, recent[]} | null, uptime }
 */
export function useTargetRows() {
  const targets = useTargets();
  const overview = useMonitorOverview();
  const rows = useMemo(() => {
    if (!targets.data) return undefined;
    const byId = new Map((overview.data ?? []).map((s) => [s.target_id, s]));
    return targets.data.map((target) => {
      const monitor = byId.get(target.id) ?? null;
      const recent = monitor?.recent ?? [];
      const up = recent.filter((c) => c.status === "UP").length;
      return {
        ...target,
        // The Target Service's status is the source of truth (it resets to UNKNOWN on disable).
        health: target.status,
        monitor,
        uptime: recent.length ? (up / recent.length) * 100 : null,
      };
    });
  }, [targets.data, overview.data]);
  return { rows, targets, overview };
}

// --- writes -----------------------------------------------------------------------------------

function useInvalidating(mutationFn, invalidate) {
  const client = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: () => Promise.all(invalidate.map((queryKey) => client.invalidateQueries({ queryKey }))),
  });
}

export const useCreateTarget = () =>
  useInvalidating((body) => api("/targets", { method: "POST", body }), [keys.targets]);

export const useUpdateTarget = () =>
  useInvalidating(({ id, ...body }) => api(`/targets/${id}`, { method: "PUT", body }), [keys.targets]);

export const useDeleteTarget = () =>
  useInvalidating((id) => api(`/targets/${id}`, { method: "DELETE" }), [keys.targets, keys.monitorOverview]);

export const useToggleTarget = () =>
  useInvalidating(
    ({ id, enabled }) => api(`/targets/${id}/${enabled ? "enable" : "disable"}`, { method: "PATCH" }),
    [keys.targets, keys.monitorOverview],
  );

export const useCheckNow = () =>
  useInvalidating((id) => api(`/monitoring/check/${id}`, { method: "POST" }), [
    keys.targets,
    keys.monitorOverview,
    ["monitoring", "status"],
    ["monitoring", "history"],
    keys.incidents,
  ]);

export const useSetIncidentStatus = () =>
  useInvalidating(
    ({ id, status, note }) => api(`/incidents/${id}/status`, { method: "PATCH", body: { status, note } }),
    [keys.incidents, keys.notifications],
  );

export function useMarkRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (ids) => Promise.all(ids.map((id) => api(`/notifications/${id}/read`, { method: "PATCH" }))),
    // Optimistic: the dot disappears immediately; a failure puts it back.
    onMutate: async (ids) => {
      await client.cancelQueries({ queryKey: keys.notifications });
      const previous = client.getQueryData(keys.notifications);
      const set = new Set(ids);
      client.setQueryData(keys.notifications, (list) => list?.map((n) => (set.has(n.id) ? { ...n, read: true } : n)));
      return { previous };
    },
    onError: (_err, _ids, context) => client.setQueryData(keys.notifications, context?.previous),
    onSettled: () => client.invalidateQueries({ queryKey: keys.notifications }),
  });
}

// --- time series --------------------------------------------------------------------------------

/** Checks grouped into time buckets. Without `id`: all targets (overall + per target). */
export const useCheckSeries = (minutes, id) =>
  useQuery({
    queryKey: ["monitoring", "timeseries", id ?? "all", minutes],
    queryFn: ({ signal }) => api(`/monitoring/${id ? `targets/${id}/` : ""}timeseries?minutes=${minutes}`, { signal }),
    refetchInterval: useInterval(2),
    placeholderData: (previous) => previous,
  });

export const useInfrastructureHistory = (minutes) =>
  useQuery({
    queryKey: ["monitoring", "infrastructure", "history", minutes],
    queryFn: ({ signal }) => api(`/monitoring/infrastructure/history?minutes=${minutes}`, { signal }),
    refetchInterval: useInterval(3),
    placeholderData: (previous) => previous,
  });

export const useResourceHistory = (id, minutes) =>
  useQuery({
    queryKey: ["monitoring", "resources", id, minutes],
    queryFn: ({ signal }) => api(`/monitoring/targets/${id}/resources?minutes=${minutes}`, { signal }),
    enabled: Boolean(id),
    refetchInterval: useInterval(3),
    placeholderData: (previous) => previous,
  });
