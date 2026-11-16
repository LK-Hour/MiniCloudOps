import { useState } from "react";
import { motion } from "framer-motion";
import { Pencil, Play, Siren, Trash2 } from "lucide-react";
import { useTargetHistory, useTargetRows, useTargetStatus } from "../api/hooks.js";
import { ResponseChart, UptimeBars } from "../components/charts.jsx";
import { Drawer } from "../components/overlay.jsx";
import { Button, ErrorState, Meter, Skeleton, StatusPill, Switch, ease } from "../components/ui.jsx";
import { clockTime, dateTime, ms, timeAgo } from "../lib/format.js";
import { useNow } from "../lib/hooks.js";
import { TargetTimeSeries } from "./TimeSeriesPanels.jsx";
import TargetForm from "./TargetForm.jsx";
import { DeleteTargetDialog, useTargetActions } from "./Targets.jsx";

function Fact({ label, children }) {
  return (
    <div className="fact">
      <span className="fact-label">{label}</span>
      <span className="fact-value">{children}</span>
    </div>
  );
}

export default function TargetDrawer({ id, onClose, openIncident }) {
  const now = useNow(1000);
  const { rows } = useTargetRows();
  const target = rows?.find((t) => t.id === id);
  const status = useTargetStatus(id);
  const history = useTargetHistory(id);
  const actions = useTargetActions();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const points = history.data ? [...history.data].reverse() : [];
  const s = status.data;

  return (
    <>
      <Drawer
        open={Boolean(id)}
        onClose={onClose}
        title={target?.name ?? "Target"}
        subtitle={target && <span className="mono">{target.target_url}</span>}
        actions={
          target && (
            <>
              <StatusPill status={target.enabled ? target.health : "DISABLED"} />
              <span className="spacer" />
              <Switch checked={target.enabled} onChange={(v) => actions.toggle(target, v)} label="Monitoring enabled" />
              <Button size="sm" icon={Play} disabled={!target.enabled} loading={actions.checking === target.id} onClick={() => actions.check(target)}>
                Check now
              </Button>
              <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setEditing(true)} aria-label="Edit" />
              <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setDeleting(true)} aria-label="Delete" />
            </>
          )
        }
      >
        {!target && rows && <p className="muted">This target no longer exists.</p>}
        {target && (
          <motion.div className="stack" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease }}>
            {s?.open_incident_id && (
              <button className="incident-banner" onClick={() => openIncident(s.open_incident_id)}>
                <Siren size={16} />
                <span>Open incident: {s.consecutive_failures} failed checks in a row</span>
                <span className="link">View</span>
              </button>
            )}

            <div className="facts">
              <Fact label="Response">{ms(s?.last_response_time_ms)}</Fact>
              <Fact label="Uptime (recent)">{target.uptime == null ? "—" : `${target.uptime.toFixed(1)}%`}</Fact>
              <Fact label="Last check">{timeAgo(s?.last_checked_at, now)}</Fact>
              <Fact label="Interval">{target.check_interval}s</Fact>
            </div>

            <section>
              <h4 className="section-title">Response time</h4>
              {history.isError ? <ErrorState error={history.error} source="Monitoring Service" /> : <ResponseChart points={points} />}
              <UptimeBars points={points} slots={60} />
            </section>

            <section>
              <h4 className="section-title">Trends</h4>
              <TargetTimeSeries id={id} />
            </section>

            <section>
              <h4 className="section-title">Container resources (now)</h4>
              {status.isError && <ErrorState error={status.error} source="Monitoring Service" />}
              {s && !s.metrics_available && <p className="muted small">Metrics temporarily unavailable (Prometheus unreachable).</p>}
              {s && s.metrics_available && s.cpu_percent == null && s.memory_percent == null && (
                <p className="muted small">No container data. Metrics exist only for apps running in this Docker Compose stack.</p>
              )}
              <div className="meters">
                <Meter label="CPU (one core)" value={s?.cpu_percent ?? null} warn={60} danger={80} />
                <Meter label="Memory (of host)" value={s?.memory_percent ?? null} warn={50} danger={75} />
              </div>
            </section>

            <section>
              <h4 className="section-title">Check history</h4>
              {!history.data && !history.isError && <Skeleton rows={3} height={32} />}
              {history.data?.length === 0 && <p className="muted small">No checks yet.</p>}
              <ul className="history">
                {history.data?.slice(0, 25).map((c) => (
                  <li key={c.checked_at}>
                    <span className={`history-mark ${c.status === "UP" ? "up" : "down"}`} />
                    <span className="mono small">{clockTime(c.checked_at)}</span>
                    <span className="truncate">{c.status === "UP" ? `HTTP ${c.status_code}` : c.error ?? "Down"}</span>
                    <span className="num muted small">{ms(c.response_time_ms)}</span>
                  </li>
                ))}
              </ul>
            </section>

            <p className="muted small">
              Added {dateTime(target.created_at)} · ID <span className="mono">{target.id}</span>
            </p>
          </motion.div>
        )}
      </Drawer>
      <TargetForm open={editing} target={target} onClose={() => setEditing(false)} />
      <DeleteTargetDialog target={deleting ? target : null} onClose={() => setDeleting(false)} onDeleted={onClose} />
    </>
  );
}
