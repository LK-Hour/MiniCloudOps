import { motion } from "framer-motion";
import { Activity, ArrowRight, Bell, Gauge, Siren } from "lucide-react";
import { useIncidents, useInfrastructure, useNotifications, useTargetRows } from "../api/hooks.js";
import { Sparkline, UptimeBars } from "../components/charts.jsx";
import {
  AnimatedNumber,
  Badge,
  Card,
  EmptyState,
  ErrorState,
  Meter,
  Skeleton,
  StatusDot,
  ease,
  severityTone,
} from "../components/ui.jsx";
import { duration, ms, timeAgo } from "../lib/format.js";
import { useNow } from "../lib/hooks.js";

const stagger = { animate: { transition: { staggerChildren: 0.05 } } };
const rise = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0, transition: { duration: 0.35, ease } } };

function Stat({ icon: Icon, label, value, format, sub, tone, onClick }) {
  return (
    <motion.button variants={rise} className={`stat stat-${tone ?? "neutral"}`} onClick={onClick} whileHover={{ y: -2 }}>
      <span className="stat-icon">
        <Icon size={16} />
      </span>
      <span className="stat-label">{label}</span>
      <span className="stat-value num">
        <AnimatedNumber value={value} format={format} />
      </span>
      <span className="stat-sub">{sub}</span>
    </motion.button>
  );
}

export default function Overview({ go, openTarget, openIncident }) {
  const now = useNow(1000);
  const { rows, targets } = useTargetRows();
  const incidents = useIncidents();
  const notifications = useNotifications();
  const infra = useInfrastructure();

  const enabled = rows?.filter((t) => t.enabled) ?? [];
  const up = enabled.filter((t) => t.health === "UP").length;
  const down = enabled.filter((t) => t.health === "DOWN").length;
  const open = incidents.data?.filter((i) => i.status !== "RESOLVED") ?? [];
  const unread = notifications.data?.filter((n) => !n.read).length;
  const times = enabled.map((t) => t.monitor?.last_response_time_ms).filter((v) => v != null);
  const avg = times.length ? times.reduce((a, b) => a + b, 0) / times.length : null;
  const host = infra.data?.available ? infra.data.host : null;

  return (
    <motion.div className="stack" variants={stagger} initial="initial" animate="animate">
      <motion.div className="stats" variants={stagger}>
        <Stat
          icon={Activity}
          label="Targets up"
          value={rows ? up : null}
          sub={rows ? `${enabled.length} monitored · ${down} down` : "loading"}
          tone={down ? "danger" : "success"}
          onClick={() => go("targets")}
        />
        <Stat
          icon={Siren}
          label="Open incidents"
          value={incidents.data ? open.length : null}
          sub={open.length ? `${open.filter((i) => i.severity === "CRITICAL").length} critical` : "all clear"}
          tone={open.length ? "danger" : "success"}
          onClick={() => go("incidents")}
        />
        <Stat
          icon={Gauge}
          label="Avg response"
          value={avg}
          format={(v) => ms(v)}
          sub={times.length ? `across ${times.length} targets` : "no data yet"}
          tone={avg != null && avg > 2000 ? "warning" : "neutral"}
          onClick={() => go("targets")}
        />
        <Stat
          icon={Bell}
          label="Unread notifications"
          value={unread ?? null}
          sub={notifications.data ? `${notifications.data.length} total` : "loading"}
          tone={unread ? "accent" : "neutral"}
          onClick={() => go("notifications")}
        />
      </motion.div>

      <div className="grid-2">
        <Card
          title="Target health"
          variants={rise}
          action={
            <button className="link" onClick={() => go("targets")}>
              All targets <ArrowRight size={14} />
            </button>
          }
        >
          {targets.isError && <ErrorState error={targets.error} source="Target Service" />}
          {!rows && !targets.isError && <Skeleton rows={3} height={58} />}
          {rows && enabled.length === 0 && <EmptyState title="No monitored targets">Add one in the Targets tab.</EmptyState>}
          <div className="health-list">
            {enabled.map((t) => (
              <motion.button key={t.id} layout className="health-row" onClick={() => openTarget(t.id)} whileHover={{ x: 2 }}>
                <StatusDot status={t.health} />
                <div className="health-main">
                  <span className="health-name">{t.name}</span>
                  <UptimeBars points={t.monitor?.recent} />
                </div>
                <div className="health-side">
                  <span className="num">{ms(t.monitor?.last_response_time_ms)}</span>
                  <span className="muted small">{t.uptime == null ? "—" : `${t.uptime.toFixed(0)}% up`}</span>
                </div>
              </motion.button>
            ))}
          </div>
        </Card>

        <div className="stack">
          <Card
            title="Active incidents"
            variants={rise}
            action={
              <button className="link" onClick={() => go("incidents")}>
                View all <ArrowRight size={14} />
              </button>
            }
          >
            {incidents.isError && <ErrorState error={incidents.error} source="Incident Service" />}
            {!incidents.data && !incidents.isError && <Skeleton rows={2} />}
            {incidents.data && open.length === 0 && <EmptyState title="All clear">No open incidents.</EmptyState>}
            <ul className="mini-list">
              {open.slice(0, 5).map((i) => (
                <motion.li key={i.id} layout>
                  <button onClick={() => openIncident(i.id)}>
                    <Badge tone={severityTone[i.severity]}>{i.severity}</Badge>
                    <span className="truncate">{i.title}</span>
                    <span className="muted small num">{duration(now - new Date(i.created_at).getTime(), 1)}</span>
                  </button>
                </motion.li>
              ))}
            </ul>
          </Card>

          <Card
            title="Host"
            variants={rise}
            action={
              <button className="link" onClick={() => go("infrastructure")}>
                Infrastructure <ArrowRight size={14} />
              </button>
            }
          >
            {infra.data && !infra.data.available && (
              <p className="muted small">Metrics temporarily unavailable (Prometheus unreachable).</p>
            )}
            <div className="meters">
              <Meter label="CPU" value={host?.cpu_percent ?? null} warn={60} danger={80} />
              <Meter label="Memory" value={host?.memory_percent ?? null} />
              <Meter label="Disk" value={host?.disk_percent ?? null} warn={80} danger={90} />
            </div>
          </Card>
        </div>
      </div>

      {notifications.data?.length > 0 && (
        <Card
          title="Latest activity"
          variants={rise}
          action={
            <button className="link" onClick={() => go("notifications")}>
              Notifications <ArrowRight size={14} />
            </button>
          }
        >
          <ul className="activity">
            {notifications.data.slice(0, 4).map((n) => (
              <li key={n.id}>
                <span className={`activity-mark ${n.event_type === "INCIDENT_RESOLVED" ? "ok" : "bad"}`} />
                <span className="truncate">{n.title}</span>
                <span className="muted small">{timeAgo(n.created_at, now)}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {rows?.some((t) => t.enabled && t.monitor?.recent?.length) && (
        <Card title="Response time trends" variants={rise}>
          <div className="trend-grid">
            {enabled.map((t) => (
              <button key={t.id} className="trend" onClick={() => openTarget(t.id)}>
                <span className="trend-name truncate">{t.name}</span>
                <Sparkline points={t.monitor?.recent} width={160} height={36} />
              </button>
            ))}
          </div>
        </Card>
      )}
    </motion.div>
  );
}
