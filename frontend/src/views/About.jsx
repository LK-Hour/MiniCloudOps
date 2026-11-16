import { motion } from "framer-motion";
import { ArrowRight, BookOpen, ExternalLink, GitCommit } from "lucide-react";
import { SERVICES, useInfrastructure, useSpecs } from "../api/hooks.js";
import { Badge, Card, StatusDot, ease } from "../components/ui.jsx";
import { dateTime } from "../lib/format.js";

/* global __APP_VERSION__, __BUILD_SHA__, __BUILD_TIME__ */
export const BUILD = { version: __APP_VERSION__, sha: __BUILD_SHA__, time: __BUILD_TIME__ };

const rise = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0, transition: { duration: 0.35, ease } } };

const SERVICE_ROLE = {
  target: "Registers and validates monitored applications",
  monitoring: "Runs health checks, reads Prometheus",
  incident: "Opens, tracks and resolves incidents",
  notification: "Stores and deduplicates notifications",
};

const PLATFORM = [
  { name: "postgres", label: "PostgreSQL 16", role: "One database per service" },
  { name: "prometheus", label: "Prometheus", role: "Metrics and alert rules", port: 9090 },
  { name: "grafana", label: "Grafana", role: "Dashboards and log search", port: 3001 },
  { name: "loki", label: "Loki", role: "Log storage" },
  { name: "alloy", label: "Grafana Alloy", role: "Ships container logs to Loki" },
  { name: "cadvisor", label: "cAdvisor", role: "Container metrics" },
  { name: "node-exporter", label: "Node Exporter", role: "Host metrics" },
  { name: "gateway", label: "nginx gateway", role: "Single entry point for the APIs" },
];

const STACK = [
  ["Backend", "Python 3.12 · FastAPI · SQLAlchemy 2 · httpx"],
  ["Frontend", "React 18 · Vite · TanStack Query · Framer Motion"],
  ["Data", "PostgreSQL 16"],
  ["Observability", "Prometheus · Grafana · Loki · Alloy · cAdvisor · Node Exporter"],
  ["Delivery", "Docker · Docker Compose · GitHub Actions · GHCR"],
];

const TEAM = [
  ["Backend Engineer", "Target Service"],
  ["Backend Engineer", "Monitoring Service"],
  ["Backend Engineer", "Incident & Notification Services"],
  ["DevOps & Observability Engineer", "Docker, CI/CD, Prometheus, Grafana, Loki"],
  ["Frontend Engineer", "Dashboard and API integration"],
];

const local = (port) => `${window.location.protocol}//${window.location.hostname}:${port}`;

export default function About({ go }) {
  const specs = useSpecs();
  const infra = useInfrastructure();
  const running = new Set((infra.data?.containers ?? []).map((c) => c.service));
  const scrapeUp = Object.fromEntries((infra.data?.services ?? []).map((s) => [s.instance.split(":")[0], s.up]));
  const metricsKnown = Boolean(infra.data?.available);
  const sha = BUILD.sha.length > 12 ? BUILD.sha.slice(0, 7) : BUILD.sha;

  return (
    <motion.div className="stack" initial="initial" animate="animate" variants={{ animate: { transition: { staggerChildren: 0.05 } } }}>
      <motion.section variants={rise} className="about-hero">
        <img className="about-mark about-logo" src="/assets/logo-256.png" alt="MiniOps logo" width="64" height="64" />
        <div className="about-copy">
          <h2>MiniOps</h2>
          <p>
            Distributed infrastructure monitoring for teams that run their own services: health checks, incidents,
            notifications and host metrics in one place, on infrastructure you control.
          </p>
          <div className="about-meta">
            <Badge tone="info">v{BUILD.version}</Badge>
            <span className="mono muted">
              <GitCommit size={13} /> {sha}
            </span>
            <span className="muted small">Built {dateTime(BUILD.time)}</span>
          </div>
        </div>
        <div className="about-links">
          <button className="link" onClick={() => go("docs", "getting-started")}>
            <BookOpen size={14} /> Documentation
          </button>
          <button className="link" onClick={() => go("docs", "api-target")}>
            API reference <ArrowRight size={14} />
          </button>
        </div>
      </motion.section>

      <div className="grid-2">
        <Card title="Services" variants={rise} action={<span className="muted small">live</span>}>
          <ul className="component-list">
            {SERVICES.map((s, i) => {
              const spec = specs[i];
              const up = spec.isSuccess && scrapeUp[`${s}-service`] !== false;
              const status = spec.isLoading ? "UNKNOWN" : up ? "UP" : "DOWN";
              return (
                <li key={s}>
                  <StatusDot status={status} />
                  <div className="component-main">
                    <span className="component-name">{s}-service</span>
                    <span className="muted small">{SERVICE_ROLE[s]}</span>
                  </div>
                  <span className="mono muted small">{spec.data ? `v${spec.data.info.version}` : status === "DOWN" ? "unreachable" : "…"}</span>
                </li>
              );
            })}
            <li>
              <StatusDot status="UP" />
              <div className="component-main">
                <span className="component-name">dashboard</span>
                <span className="muted small">This web app</span>
              </div>
              <span className="mono muted small">v{BUILD.version}</span>
            </li>
          </ul>
        </Card>

        <Card title="Platform" variants={rise} action={<span className="muted small">{metricsKnown ? "from cAdvisor" : "metrics unavailable"}</span>}>
          <ul className="component-list">
            {PLATFORM.map((c) => (
              <li key={c.name}>
                <StatusDot status={!metricsKnown ? "UNKNOWN" : running.has(c.name) ? "UP" : "DOWN"} />
                <div className="component-main">
                  <span className="component-name">{c.label}</span>
                  <span className="muted small">{c.role}</span>
                </div>
                {c.port && (
                  <a className="link small" href={local(c.port)} target="_blank" rel="noreferrer">
                    Open <ExternalLink size={12} />
                  </a>
                )}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="Architecture" variants={rise}>
        <div className="arch">
          <div className="arch-col">
            <span className="arch-node">Browser</span>
          </div>
          <span className="arch-arrow" />
          <div className="arch-col">
            <span className="arch-node">Dashboard</span>
            <span className="arch-node">API gateway</span>
          </div>
          <span className="arch-arrow" />
          <div className="arch-col">
            {SERVICES.map((s) => (
              <span key={s} className="arch-node accent">
                {s}
              </span>
            ))}
          </div>
          <span className="arch-arrow" />
          <div className="arch-col">
            <span className="arch-node">PostgreSQL</span>
            <span className="arch-node">Prometheus</span>
            <span className="arch-node">Loki</span>
          </div>
        </div>
        <p className="muted small arch-note">
          Services talk over REST and own their data: each has its own database and never reads another's. Every request
          carries a correlation ID, so one action can be followed through all logs.
        </p>
      </Card>

      <div className="grid-2">
        <Card title="Technology" variants={rise}>
          <dl className="kv">
            {STACK.map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title="Team" variants={rise}>
          <dl className="kv">
            {TEAM.map(([role, owns], i) => (
              <div key={i}>
                <dt>{role}</dt>
                <dd>{owns}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>

      <motion.p variants={rise} className="muted small about-foot">
        Released under the MIT License. Built with open-source software, including React, FastAPI, SQLAlchemy, PostgreSQL,
        Prometheus, Grafana and Loki.
      </motion.p>
    </motion.div>
  );
}
