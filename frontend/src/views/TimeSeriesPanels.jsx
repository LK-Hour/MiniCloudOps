import { useMemo, useState } from "react";
import { useCheckSeries, useInfrastructureHistory, useResourceHistory, useTargetRows } from "../api/hooks.js";
import { RangeSelect, Stat, TimeSeriesChart } from "../components/timeseries.jsx";
import { ErrorState, Skeleton } from "../components/ui.jsx";
import { ms, pct } from "../lib/format.js";

const toPoints = (rows, key) => rows.map((r) => ({ t: new Date(r.t).getTime(), v: r[key] }));
const sample = (list) => list.map((p) => ({ t: new Date(p.t).getTime(), v: p.v }));
const availability = (buckets) => buckets.map((b) => ({ t: new Date(b.t).getTime(), v: b.checks ? ((b.checks - b.failures) / b.checks) * 100 : null }));

function summarize(buckets) {
  const checks = buckets.reduce((a, b) => a + b.checks, 0);
  const failures = buckets.reduce((a, b) => a + b.failures, 0);
  const weighted = buckets.filter((b) => b.avg_ms != null);
  const n = weighted.reduce((a, b) => a + b.checks - b.failures, 0);
  const avg = n ? weighted.reduce((a, b) => a + b.avg_ms * (b.checks - b.failures), 0) / n : null;
  const peak = Math.max(0, ...buckets.map((b) => b.max_ms ?? 0));
  return { checks, failures, avg, peak: peak || null, uptime: checks ? ((checks - failures) / checks) * 100 : null };
}

const domainOf = (data) => {
  const first = data?.overall?.[0];
  return first ? [new Date(first.t).getTime(), new Date(first.t).getTime() + data.minutes * 60_000] : undefined;
};

const uptimeTone = (u) => (u == null ? undefined : u >= 99 ? "success" : u < 95 ? "danger" : undefined);

/** Overview: response time of every target, availability and checks over time. */
export function FleetTimeSeries() {
  const [minutes, setMinutes] = useState(60);
  const { rows } = useTargetRows();
  const query = useCheckSeries(minutes);
  const data = query.data;
  const names = useMemo(() => new Map((rows ?? []).map((t) => [t.id, t.name])), [rows]);
  const sum = data ? summarize(data.overall) : null;
  const domain = domainOf(data);

  const series = (data?.targets ?? [])
    .filter((t) => names.has(t.target_id))
    .map((t) => ({ key: t.target_id, label: names.get(t.target_id), points: toPoints(t.buckets, "avg_ms") }));

  return (
    <div>
      <div className="ts-head">
        <span className="muted small">{data ? `${data.bucket_seconds >= 60 ? `${Math.round(data.bucket_seconds / 60)} min` : `${data.bucket_seconds}s`} buckets · averages` : " "}</span>
        <RangeSelect value={minutes} onChange={setMinutes} />
      </div>
      {query.isError && <ErrorState error={query.error} source="Monitoring Service" />}
      {!data && !query.isError && <Skeleton rows={3} height={60} />}
      {data && (
        <>
          <div className="ts-stats">
            <Stat label="Availability" value={pct(sum.uptime)} tone={uptimeTone(sum.uptime)} />
            <Stat label="Avg response" value={ms(sum.avg)} />
            <Stat label="Peak response" value={ms(sum.peak)} />
            <Stat label="Checks" value={sum.checks} />
            <Stat label="Failed" value={sum.failures} tone={sum.failures ? "danger" : undefined} />
          </div>
          <div className="ts-panels">
            <div>
              <h4 className="ts-panel-title">Response time per target</h4>
              <TimeSeriesChart series={series} format={ms} domain={domain} height={210} empty="No checks in this range yet." />
            </div>
            <div>
              <h4 className="ts-panel-title">Availability</h4>
              <TimeSeriesChart
                series={[
                  { key: "all", label: "All targets", area: true, points: availability(data.overall) },
                  ...(data.targets.length > 1 && data.targets.length <= 6
                    ? data.targets.filter((t) => names.has(t.target_id)).map((t) => ({ key: `a-${t.target_id}`, label: names.get(t.target_id), points: availability(t.buckets) }))
                    : []),
                ]}
                format={(v) => `${Math.round(v)}%`}
                max={100}
                domain={domain}
                height={210}
                empty="No checks in this range yet."
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

const HOST_SERIES = (host) => [
  { key: "cpu", label: "CPU", color: "var(--accent)", area: true, points: sample(host.cpu ?? []) },
  { key: "memory", label: "Memory", color: "var(--info)", points: sample(host.memory ?? []) },
  { key: "disk", label: "Disk", color: "var(--warning)", points: sample(host.disk ?? []) },
];

/** Host CPU / memory / disk over time. `compact` is for the overview card. */
export function HostTimeSeries({ compact = false, withContainers = false }) {
  const [minutes, setMinutes] = useState(60);
  const query = useInfrastructureHistory(minutes);
  const data = query.data;
  return (
    <div>
      <div className="ts-head">
        <span className="muted small">{data ? `${data.step_seconds}s resolution` : " "}</span>
        <RangeSelect value={minutes} onChange={setMinutes} />
      </div>
      {query.isError && <ErrorState error={query.error} source="Monitoring Service" />}
      {!data && !query.isError && <Skeleton rows={2} height={60} />}
      {data && !data.available && <p className="muted small">History unavailable (Prometheus unreachable).</p>}
      {data?.available && (
        <div className={compact ? undefined : "ts-panels"}>
          <div>
            {!compact && <h4 className="ts-panel-title">Host usage</h4>}
            <TimeSeriesChart
              series={HOST_SERIES(data.host).filter((s) => !compact || s.key !== "disk")}
              format={(v) => `${Math.round(v)}%`}
              max={100}
              thresholds={[{ value: 80, label: "80% alert" }]}
              height={compact ? 170 : 220}
            />
          </div>
          {withContainers && (
            <div>
              <h4 className="ts-panel-title">Busiest containers (CPU, % of one core)</h4>
              <TimeSeriesChart
                series={Object.entries(data.containers).map(([name, pts]) => ({ key: name, label: name, points: sample(pts) }))}
                format={(v) => `${v < 10 ? v.toFixed(1) : Math.round(v)}%`}
                height={220}
                empty="No container data."
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Target drawer: response time with failure markers, availability, container CPU/memory. */
export function TargetTimeSeries({ id }) {
  const [minutes, setMinutes] = useState(60);
  const checks = useCheckSeries(minutes, id);
  const resources = useResourceHistory(id, minutes);
  const buckets = checks.data?.targets?.[0]?.buckets ?? [];
  const sum = summarize(buckets);
  const domain = domainOf(checks.data) ?? undefined;
  const failures = buckets.filter((b) => b.failures).map((b) => ({ t: new Date(b.t).getTime() }));
  const domainFixed = checks.data && buckets.length ? [new Date(buckets[0].t).getTime(), new Date(buckets[0].t).getTime() + minutes * 60_000] : domain;
  const r = resources.data;

  return (
    <div>
      <div className="ts-head">
        <span className="muted small">Last {minutes >= 60 ? `${minutes / 60}h` : `${minutes}m`}</span>
        <RangeSelect value={minutes} onChange={setMinutes} />
      </div>
      {checks.isError && <ErrorState error={checks.error} source="Monitoring Service" />}
      {!checks.data && !checks.isError && <Skeleton rows={3} height={60} />}
      {checks.data && (
        <>
          <div className="ts-stats">
            <Stat label="Availability" value={pct(sum.uptime)} tone={uptimeTone(sum.uptime)} />
            <Stat label="Avg response" value={ms(sum.avg)} />
            <Stat label="Peak" value={ms(sum.peak)} />
            <Stat label="Checks" value={sum.checks} />
            <Stat label="Failed" value={sum.failures} tone={sum.failures ? "danger" : undefined} />
          </div>
          <h4 className="ts-panel-title">Response time (red ticks: failed checks)</h4>
          <TimeSeriesChart
            series={[
              { key: "avg", label: "Average", area: true, points: toPoints(buckets, "avg_ms") },
              { key: "max", label: "Slowest", color: "var(--warning)", points: toPoints(buckets, "max_ms") },
            ]}
            format={ms}
            marks={failures}
            domain={domainFixed}
            height={190}
            empty="No checks in this range yet."
          />
          <h4 className="ts-panel-title" style={{ marginTop: 16 }}>Availability</h4>
          <TimeSeriesChart
            series={[{ key: "up", label: "Availability", area: true, points: availability(buckets) }]}
            format={(v) => `${Math.round(v)}%`}
            max={100}
            domain={domainFixed}
            height={130}
            empty="No checks in this range yet."
          />
        </>
      )}
      <h4 className="ts-panel-title" style={{ marginTop: 16 }}>Container resources</h4>
      {resources.isError && <ErrorState error={resources.error} source="Monitoring Service" />}
      {r && !r.available && <p className="muted small">History unavailable (Prometheus unreachable).</p>}
      {r?.available && r.cpu.length === 0 && r.memory.length === 0 && (
        <p className="muted small">No container data. Metrics exist only for apps running in this Docker Compose stack.</p>
      )}
      {r?.available && (r.cpu.length > 0 || r.memory.length > 0) && (
        <TimeSeriesChart
          series={[
            { key: "cpu", label: "CPU (of one core)", points: sample(r.cpu) },
            { key: "mem", label: "Memory (of host)", color: "var(--info)", points: sample(r.memory) },
          ]}
          format={(v) => `${v < 10 ? v.toFixed(1) : Math.round(v)}%`}
          domain={domainFixed}
          height={160}
        />
      )}
    </div>
  );
}
