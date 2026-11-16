import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ShieldCheck } from "lucide-react";
import { useIncidents, useTargets } from "../api/hooks.js";
import { Badge, EmptyState, ErrorState, Segmented, Skeleton, incidentTone, listItem, severityTone } from "../components/ui.jsx";
import { dateTime, duration, shortId } from "../lib/format.js";
import { useNow } from "../lib/hooks.js";

const FILTERS = ["active", "OPEN", "ACKNOWLEDGED", "RESOLVED", "all"];
const LABELS = { active: "Active", OPEN: "Open", ACKNOWLEDGED: "Acknowledged", RESOLVED: "Resolved", all: "All" };
const matches = (i, f) => f === "all" || (f === "active" ? i.status !== "RESOLVED" : i.status === f);

export function useTargetNames() {
  const targets = useTargets();
  return useMemo(() => new Map((targets.data ?? []).map((t) => [t.id, t.name])), [targets.data]);
}

export function incidentDuration(i, now) {
  const end = i.resolved_at ? new Date(i.resolved_at).getTime() : now;
  return duration(end - new Date(i.created_at).getTime());
}

export default function Incidents({ openIncident }) {
  const now = useNow(1000);
  const incidents = useIncidents();
  const names = useTargetNames();
  const [filter, setFilter] = useState("active");

  const counts = useMemo(
    () => Object.fromEntries(FILTERS.map((f) => [f, incidents.data?.filter((i) => matches(i, f)).length ?? 0])),
    [incidents.data],
  );
  const visible = (incidents.data ?? []).filter((i) => matches(i, filter));

  return (
    <div className="stack">
      <div className="toolbar">
        <Segmented options={FILTERS.map((f) => ({ value: f, label: LABELS[f], count: counts[f] }))} value={filter} onChange={setFilter} />
      </div>
      {incidents.isError && <ErrorState error={incidents.error} source="Incident Service" />}
      {!incidents.data && !incidents.isError && <Skeleton rows={4} height={72} />}
      {incidents.data && visible.length === 0 && (
        <EmptyState icon={ShieldCheck} title={filter === "active" ? "All clear" : "Nothing here"}>
          {filter === "active" ? "No open incidents. Incidents open after 3 failed checks in a row." : "No incidents match this filter."}
        </EmptyState>
      )}
      <div className="incident-list">
        <AnimatePresence initial={false}>
          {visible.map((i) => (
            <motion.button key={i.id} layout {...listItem} className={`incident incident-${i.status.toLowerCase()}`} onClick={() => openIncident(i.id)}>
              <span className={`incident-rail tone-${severityTone[i.severity]}`} />
              <div className="incident-main">
                <div className="incident-top">
                  <Badge tone={severityTone[i.severity]}>{i.severity}</Badge>
                  <Badge tone={incidentTone[i.status]}>{i.status}</Badge>
                  <span className="muted small mono">{shortId(i.id)}</span>
                </div>
                <strong className="incident-title">{i.title}</strong>
                {i.description && <p className="incident-desc">{i.description}</p>}
              </div>
              <div className="incident-side">
                <span className="small muted">{names.get(i.target_id) ?? `target ${shortId(i.target_id)}`}</span>
                <span className="num">{incidentDuration(i, now)}</span>
                <span className="small muted">{i.resolved_at ? "lasted" : "ongoing"} · {dateTime(i.created_at)}</span>
              </div>
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
