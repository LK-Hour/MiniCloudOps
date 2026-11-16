import { motion } from "framer-motion";
import { Bell, BellOff, CheckCircle2, CircleDot, Eye } from "lucide-react";
import { useIncidentHistory, useIncidents, useSetIncidentStatus } from "../api/hooks.js";
import { Drawer, useToast } from "../components/overlay.jsx";
import { Badge, Button, ErrorState, Skeleton, ease, incidentTone, severityTone } from "../components/ui.jsx";
import { dateTime } from "../lib/format.js";
import { useNow } from "../lib/hooks.js";
import { incidentDuration, useTargetNames } from "./Incidents.jsx";

const EVENT = {
  CREATED: { icon: CircleDot, tone: "danger", label: "Incident opened" },
  ACKNOWLEDGED: { icon: Eye, tone: "warning", label: "Acknowledged" },
  RESOLVED: { icon: CheckCircle2, tone: "success", label: "Resolved" },
  NOTIFICATION_SENT: { icon: Bell, tone: "neutral", label: "Notification sent" },
  NOTIFICATION_FAILED: { icon: BellOff, tone: "danger", label: "Notification failed" },
};

export default function IncidentDrawer({ id, onClose, openTarget }) {
  const now = useNow(1000);
  const incidents = useIncidents();
  const incident = incidents.data?.find((i) => i.id === id);
  const history = useIncidentHistory(id);
  const names = useTargetNames();
  const setStatus = useSetIncidentStatus();
  const toast = useToast();

  const change = (status) =>
    setStatus.mutate(
      { id, status, note: status === "RESOLVED" ? "Resolved from the dashboard" : "Acknowledged from the dashboard" },
      {
        onSuccess: () => toast({ tone: "success", title: status === "RESOLVED" ? "Incident resolved" : "Incident acknowledged" }),
        onError: (err) => toast({ tone: "error", title: "Could not update incident", message: err.message }),
      },
    );

  return (
    <Drawer
      open={Boolean(id)}
      onClose={onClose}
      title={incident?.title ?? "Incident"}
      subtitle={incident && dateTime(incident.created_at)}
      actions={
        incident && (
          <>
            <Badge tone={severityTone[incident.severity]}>{incident.severity}</Badge>
            <Badge tone={incidentTone[incident.status]}>{incident.status}</Badge>
            <span className="spacer" />
            {incident.status === "OPEN" && (
              <Button size="sm" icon={Eye} loading={setStatus.isPending && setStatus.variables?.status === "ACKNOWLEDGED"} onClick={() => change("ACKNOWLEDGED")}>
                Acknowledge
              </Button>
            )}
            {incident.status !== "RESOLVED" && (
              <Button size="sm" variant="primary" icon={CheckCircle2} loading={setStatus.isPending && setStatus.variables?.status === "RESOLVED"} onClick={() => change("RESOLVED")}>
                Resolve
              </Button>
            )}
          </>
        )
      }
    >
      {!incident && incidents.data && <p className="muted">Incident not found.</p>}
      {incident && (
        <motion.div className="stack" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease }}>
          <div className="facts">
            <div className="fact">
              <span className="fact-label">Target</span>
              <button className="fact-value link" onClick={() => openTarget(incident.target_id)}>
                {names.get(incident.target_id) ?? "Deleted target"}
              </button>
            </div>
            <div className="fact">
              <span className="fact-label">{incident.resolved_at ? "Lasted" : "Open for"}</span>
              <span className="fact-value num">{incidentDuration(incident, now)}</span>
            </div>
          </div>
          {incident.description && <p className="description">{incident.description}</p>}
          {incident.status !== "RESOLVED" && (
            <p className="muted small">It resolves automatically when the target's next health check passes.</p>
          )}

          <section>
            <h4 className="section-title">Timeline</h4>
            {history.isError && <ErrorState error={history.error} source="Incident Service" />}
            {!history.data && !history.isError && <Skeleton rows={3} height={36} />}
            <ol className="timeline">
              {history.data?.map((e, idx) => {
                const meta = EVENT[e.event_type] ?? { icon: CircleDot, tone: "neutral", label: e.event_type };
                const Icon = meta.icon;
                return (
                  <motion.li key={e.id} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: idx * 0.05, duration: 0.25, ease }}>
                    <span className={`timeline-icon tone-${meta.tone}`}>
                      <Icon size={13} />
                    </span>
                    <div>
                      <strong>{meta.label}</strong>
                      <p className="muted small">{e.message}</p>
                    </div>
                    <span className="muted small">{dateTime(e.created_at)}</span>
                  </motion.li>
                );
              })}
            </ol>
          </section>
        </motion.div>
      )}
    </Drawer>
  );
}
