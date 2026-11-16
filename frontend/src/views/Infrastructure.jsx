import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { CloudOff, Cpu, HardDrive, MemoryStick, Server, Timer } from "lucide-react";
import { useInfrastructure } from "../api/hooks.js";
import { Badge, Card, ErrorState, Meter, Segmented, Skeleton, StatusDot, ease } from "../components/ui.jsx";
import { bytes, clockTime, duration, pct } from "../lib/format.js";

const rise = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0, transition: { duration: 0.35, ease } } };

function HostTile({ icon: Icon, label, value, children }) {
  return (
    <motion.div variants={rise} className="host-tile">
      <span className="host-icon">
        <Icon size={16} />
      </span>
      <span className="stat-label">{label}</span>
      <span className="host-value num">{value}</span>
      {children}
    </motion.div>
  );
}

export default function Infrastructure() {
  const infra = useInfrastructure();
  const [sort, setSort] = useState("cpu");
  const data = infra.data;
  const host = data?.host ?? {};

  const containers = useMemo(() => {
    const list = [...(data?.containers ?? [])];
    const key = sort === "cpu" ? "cpu_percent" : sort === "memory" ? "memory_bytes" : null;
    return key ? list.sort((a, b) => (b[key] ?? -1) - (a[key] ?? -1)) : list;
  }, [data, sort]);
  const maxMem = Math.max(...containers.map((c) => c.memory_bytes ?? 0), 1);
  const maxCpu = Math.max(...containers.map((c) => c.cpu_percent ?? 0), 1);
  const firing = data?.alerts?.filter((a) => a.state === "firing") ?? [];

  if (infra.isError) return <ErrorState error={infra.error} source="Monitoring Service" />;
  if (!data) return <Skeleton rows={5} height={64} />;
  if (!data.available)
    return (
      <Card>
        <div className="empty">
          <span className="empty-icon">
            <CloudOff size={20} />
          </span>
          <strong>Metrics temporarily unavailable</strong>
          <p>Prometheus cannot be reached. Values are hidden rather than shown as zero.</p>
        </div>
      </Card>
    );

  return (
    <motion.div className="stack" initial="initial" animate="animate" variants={{ animate: { transition: { staggerChildren: 0.05 } } }}>
      <div className="host-grid">
        <HostTile icon={Cpu} label="Host CPU" value={pct(host.cpu_percent)}>
          <Meter value={host.cpu_percent} warn={60} danger={80} />
        </HostTile>
        <HostTile icon={MemoryStick} label="Host memory" value={pct(host.memory_percent)}>
          <Meter value={host.memory_percent} detail={`of ${bytes(host.memory_total_bytes)}`} />
        </HostTile>
        <HostTile icon={HardDrive} label="Disk (/)" value={pct(host.disk_percent)}>
          <Meter value={host.disk_percent} warn={80} danger={90} />
        </HostTile>
        <HostTile icon={Timer} label="Host uptime" value={duration(host.uptime_seconds == null ? null : host.uptime_seconds * 1000)}>
          <span className="muted small">Updated {clockTime(data.collected_at)}</span>
        </HostTile>
      </div>

      <div className="grid-2">
        <Card title="Alerts" variants={rise} action={<Badge tone={firing.length ? "danger" : "success"}>{firing.length} firing</Badge>}>
          {data.alerts.length === 0 && <p className="muted small">No alerts. Rules: container CPU &gt; 80%, memory &gt; 85%, service down.</p>}
          <ul className="mini-list">
            {data.alerts.map((a, i) => (
              <li key={`${a.name}-${i}`} className="alert-row">
                <Badge tone={a.state === "firing" ? "danger" : "warning"}>{a.state}</Badge>
                <span className="truncate">{a.summary ?? a.name}</span>
                {a.severity && <span className="muted small">{a.severity}</span>}
              </li>
            ))}
          </ul>
        </Card>
        <Card title="MiniOps services" variants={rise}>
          <ul className="service-list">
            {data.services.map((s) => (
              <li key={s.instance}>
                <StatusDot status={s.up ? "UP" : "DOWN"} />
                <span>{s.instance.replace(/:\d+$/, "")}</span>
                <span className={`small ${s.up ? "muted" : "text-danger"}`}>{s.up ? "healthy" : "not responding"}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card
        title={`Containers · ${containers.length}`}
        variants={rise}
        action={
          <Segmented
            size="sm"
            options={[
              { value: "cpu", label: "CPU" },
              { value: "memory", label: "Memory" },
              { value: "name", label: "Name" },
            ]}
            value={sort}
            onChange={setSort}
          />
        }
      >
        <div className="containers">
          {containers.map((c) => (
            <motion.div key={c.service} layout transition={{ type: "spring", stiffness: 400, damping: 36 }} className="container-row">
              <span className="container-name">
                <Server size={14} className="muted" />
                {c.service}
              </span>
              <span className="bar-cell">
                <span className="bar">
                  <motion.span className="bar-fill cpu" animate={{ width: `${((c.cpu_percent ?? 0) / maxCpu) * 100}%` }} transition={{ duration: 0.6, ease }} />
                </span>
                <span className="num small">{pct(c.cpu_percent, 2)}</span>
              </span>
              <span className="bar-cell">
                <span className="bar">
                  <motion.span className="bar-fill mem" animate={{ width: `${((c.memory_bytes ?? 0) / maxMem) * 100}%` }} transition={{ duration: 0.6, ease }} />
                </span>
                <span className="num small">{bytes(c.memory_bytes)}</span>
              </span>
            </motion.div>
          ))}
        </div>
        <p className="muted small legend">
          <span className="legend-swatch cpu" /> CPU, % of one core <span className="legend-swatch mem" /> Memory working set
        </p>
      </Card>
    </motion.div>
  );
}
