import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup, motion } from "framer-motion";
import {
  Check,
  CircleDashed,
  FlaskConical,
  Minus,
  Play,
  ScrollText,
  Siren,
  Square,
  Target,
  Terminal,
  X,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useLabEndpoints, usePolicy } from "../../api/hooks.js";
import { Badge, Button, Spinner, Switch, ease, spring } from "../../components/ui.jsx";
import { clockTime, duration, timeAgo } from "../../lib/format.js";
import { useNow } from "../../lib/hooks.js";
import { Callout, Code } from "../Docs.jsx";
import { abortRun, clearRun, lastResults, runScenario, useLab } from "./runner.js";
import { CATEGORIES, SCENARIOS } from "./scenarios.js";

const NO_LAB = new Set(["contract", "security"]);
const FLOW = [
  { id: "lab", label: "Sandbox app" },
  { id: "gateway", label: "Gateway" },
  { id: "target", label: "Target" },
  { id: "monitoring", label: "Monitoring" },
  { id: "incident", label: "Incident" },
  { id: "notification", label: "Notification" },
];

const resolve = (v, policy) => (typeof v === "function" ? v(policy) : v);

function StepIcon({ status }) {
  const icon = {
    pending: <CircleDashed size={15} />,
    running: <Spinner size={15} />,
    passed: <Check size={14} strokeWidth={3} />,
    failed: <X size={14} strokeWidth={3} />,
    aborted: <Square size={11} fill="currentColor" />,
    skipped: <Minus size={14} />,
  }[status];
  return (
    <motion.span key={status} className={`step-icon step-${status}`} initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={spring}>
      {icon}
    </motion.span>
  );
}

function ResultBadge({ result }) {
  if (!result) return <span className="muted small">Not run yet</span>;
  const tone = { passed: "success", failed: "danger", aborted: "neutral" }[result.status];
  return (
    <span className="lab-result">
      <Badge tone={tone}>{result.status === "passed" ? "Passed" : result.status === "failed" ? "Failed" : "Stopped"}</Badge>
      <span className="muted small">{timeAgo(new Date(result.endedAt).toISOString())}</span>
    </span>
  );
}

/** The services a scenario touches, lit up while the current step uses them. */
function FlowStrip({ involved, active }) {
  return (
    <div className="flow-strip" aria-hidden="true">
      {FLOW.map((node, i) => {
        const on = involved.includes(node.id) || (node.id === "gateway" && involved.length);
        const hot = active.includes(node.id) || (node.id === "gateway" && active.length > 0);
        return (
          <div key={node.id} className="flow-cell">
            {i > 0 && (
              <span className={`flow-link ${hot ? "hot" : ""}`}>
                {hot && <motion.span className="flow-packet" animate={{ x: ["-20%", "120%"] }} transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }} />}
              </span>
            )}
            <motion.span className={`flow-node ${on ? "on" : ""} ${hot ? "hot" : ""}`} animate={hot ? { scale: [1, 1.06, 1] } : { scale: 1 }} transition={hot ? { duration: 1.2, repeat: Infinity } : { duration: 0.2 }}>
              {node.label}
            </motion.span>
          </div>
        );
      })}
    </div>
  );
}

function Console({ lines }) {
  const ref = useRef(null);
  const [follow, setFollow] = useState(true);
  useEffect(() => {
    if (follow && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines, follow]);
  return (
    <div
      className="console"
      ref={ref}
      onScroll={(e) => {
        const el = e.currentTarget;
        setFollow(el.scrollHeight - el.scrollTop - el.clientHeight < 24);
      }}
    >
      {lines.length === 0 && <span className="muted">Requests and results appear here while the scenario runs.</span>}
      {lines.map((l, i) => (
        <div key={i} className={`console-line tone-${l.tone}`}>
          <span className="console-time">{clockTime(new Date(l.t).toISOString())}</span>
          <span className="console-text">
            {l.text}
            {l.count > 1 && <span className="console-count">×{l.count}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

function ScenarioDetail({ scenario, policy, labUp, go, openTarget, openIncident }) {
  const lab = useLab();
  const client = useQueryClient();
  const now = useNow(500);
  const [keep, setKeep] = useState(false);
  const run = lab.runs[scenario.id];
  const busy = Boolean(lab.activeId);
  const mine = lab.activeId === scenario.id;
  const needsLab = !NO_LAB.has(scenario.id);
  const blocked = (needsLab && !labUp) || !policy;
  const steps = run?.steps ?? scenario.steps.map((s) => ({ title: resolve(s.title, policy ?? {}), services: s.services, status: "pending" }));
  const active = run?.status === "running" ? steps[run.current]?.services ?? [] : [];
  const done = steps.filter((s) => s.status === "passed").length;
  const elapsed = run ? (run.endedAt ?? now) - run.startedAt : 0;

  const start = () =>
    runScenario(scenario, {
      policy,
      keep,
      onFinish: () => client.invalidateQueries(),
    });

  return (
    <motion.div key={scenario.id} className="lab-detail" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0, transition: { duration: 0.28, ease } }}>
      <header className="lab-head">
        <div>
          <span className="eyebrow">
            {scenario.category}
            {scenario.manual && " · needs a terminal"}
          </span>
          <h2>{scenario.title}</h2>
          <p className="muted">{scenario.summary}</p>
        </div>
        <div className="lab-actions">
          {mine ? (
            <Button variant="danger" icon={Square} onClick={abortRun}>
              Stop
            </Button>
          ) : (
            <Button variant="primary" icon={Play} onClick={start} disabled={busy || blocked} title={busy ? "Another scenario is running" : undefined}>
              {run ? "Run again" : "Run scenario"}
            </Button>
          )}
          {needsLab && (
            <label className="keep-toggle muted small">
              <Switch checked={keep} onChange={setKeep} disabled={mine} label="Keep the lab target afterwards" />
              Keep target
            </label>
          )}
        </div>
      </header>

      <div className="hypothesis">
        <span className="eyebrow">Hypothesis</span>
        <p>{policy ? resolve(scenario.hypothesis, policy) : "Loading the monitoring policy…"}</p>
      </div>

      <FlowStrip involved={[...(needsLab ? ["lab"] : []), ...scenario.services]} active={active} />

      {needsLab && !labUp && (
        <Callout tone="warning" title="The sandbox app isn't running">
          This scenario breaks a sandbox app on purpose. Start it with the rest of the stack:
          <Code>make demo</Code>
        </Callout>
      )}

      <AnimatePresence>
        {run?.manual && (
          <motion.div className="manual" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
            <div className="manual-inner">
              <span className="manual-title">
                <Terminal size={15} /> Your turn
              </span>
              <p className="muted small">{run.manual.text}</p>
              <Code>{run.manual.command}</Code>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {run && (
        <div className="run-bar">
          <div className="run-progress">
            <motion.span className={`run-fill run-${run.status}`} animate={{ width: `${(done / steps.length) * 100}%` }} transition={{ duration: 0.4, ease }} />
          </div>
          <span className="mono small muted">
            {done}/{steps.length} · {duration(elapsed) === "0s" ? `${(elapsed / 1000).toFixed(1)}s` : duration(elapsed)} · {run.correlationId}
          </span>
        </div>
      )}

      <ol className="steps">
        {steps.map((step, i) => (
          <motion.li
            key={i}
            className={`step step-row-${step.status}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0, transition: { delay: run ? 0 : i * 0.03, duration: 0.25, ease } }}
          >
            <StepIcon status={step.status} />
            <div className="step-body">
              <div className="step-title">
                <span>{step.title}</span>
                {step.endedAt && step.startedAt && <span className="mono muted small">{((step.endedAt - step.startedAt) / 1000).toFixed(1)}s</span>}
              </div>
              <AnimatePresence initial={false}>
                {step.detail && (
                  <motion.p className={`step-detail ${step.status === "failed" ? "danger" : ""}`} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}>
                    {step.detail}
                  </motion.p>
                )}
              </AnimatePresence>
              {step.status === "running" && <span className="step-shimmer" />}
            </div>
          </motion.li>
        ))}
      </ol>

      <AnimatePresence>
        {run && run.status !== "running" && (
          <motion.section
            className={`verdict verdict-${run.status}`}
            initial={{ opacity: 0, y: 10, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1, transition: spring }}
            exit={{ opacity: 0 }}
          >
            <div className="verdict-head">
              <span className="verdict-icon">{run.status === "passed" ? <Check size={18} strokeWidth={3} /> : <X size={18} strokeWidth={3} />}</span>
              <div>
                <strong>{run.status === "passed" ? "Hypothesis confirmed" : run.status === "failed" ? "Hypothesis rejected" : "Run stopped"}</strong>
                <p className="muted small">
                  {run.status === "passed"
                    ? `All ${steps.length} steps passed in ${(elapsed / 1000).toFixed(1)} s.`
                    : run.error}
                  {run.status !== "passed" && scenario.manual && " If you stopped a service, start it again: docker compose start incident-service notification-service"}
                </p>
              </div>
            </div>
            {run.metrics.length > 0 && (
              <div className="verdict-metrics">
                {run.metrics.map(([label, value]) => (
                  <div key={label} className="metric-tile">
                    <span className="muted small">{label}</span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
            )}
            <div className="verdict-actions">
              <Button size="sm" icon={ScrollText} onClick={() => go("demo", `logs/${run.correlationId}`)}>
                Logs for this run
              </Button>
              {run.state.incidentId && (
                <Button size="sm" icon={Siren} onClick={() => openIncident(run.state.incidentId)}>
                  Open incident
                </Button>
              )}
              {keep && run.state.target && run.status === "passed" && (
                <Button size="sm" icon={Target} onClick={() => openTarget(run.state.target.id)}>
                  Open target
                </Button>
              )}
              <button className="link small" onClick={() => clearRun(scenario.id)}>
                Reset
              </button>
            </div>
          </motion.section>
        )}
      </AnimatePresence>

      <div className="console-wrap">
        <div className="console-head">
          <span className="eyebrow">Run console</span>
          {run && <span className="muted small">every request carries {run.correlationId}</span>}
        </div>
        <Console lines={run?.console ?? []} />
      </div>
    </motion.div>
  );
}

export default function Scenarios({ go, openTarget, openIncident }) {
  const policy = usePolicy();
  const labEndpoints = useLabEndpoints();
  const lab = useLab();
  const [selected, setSelected] = useState(() => lab.activeId ?? SCENARIOS[0].id);
  // Re-read after each run finishes.
  const results = useMemo(() => lastResults(), [lab.activeId]); // eslint-disable-line react-hooks/exhaustive-deps
  const scenario = SCENARIOS.find((s) => s.id === selected) ?? SCENARIOS[0];
  const labUp = labEndpoints.isSuccess;
  const passedCount = Object.values(results).filter((r) => r.status === "passed").length;

  return (
    <div className="lab">
      <aside className="lab-list">
        <div className="lab-summary">
          <span className={`lab-status ${labUp ? "ok" : "off"}`}>
            <span className="lab-dot" /> Sandbox {labUp ? `online · ${labEndpoints.data.length} endpoint${labEndpoints.data.length === 1 ? "" : "s"}` : labEndpoints.isLoading ? "…" : "offline"}
          </span>
          <span className="muted small">
            {passedCount}/{SCENARIOS.length} passing
          </span>
        </div>
        <LayoutGroup id="lab-list">
          {CATEGORIES.map((cat) => (
            <div key={cat} className="lab-group">
              <span className="nav-label">{cat}</span>
              {SCENARIOS.filter((s) => s.category === cat).map((s) => {
                const running = lab.activeId === s.id;
                return (
                  <button key={s.id} className={`lab-item ${s.id === selected ? "active" : ""}`} onClick={() => setSelected(s.id)}>
                    {s.id === selected && <motion.span layoutId="lab-active" className="lab-item-bg" transition={spring} />}
                    <span className="lab-item-top">
                      <span className="lab-item-title">
                        {running ? <Spinner size={13} /> : <FlaskConical size={13} className="muted" />}
                        {s.title}
                      </span>
                      <span className="muted small mono">{s.estimate.split(" ·")[0]}</span>
                    </span>
                    <span className="lab-item-meta">
                      {running ? <Badge tone="info">Running</Badge> : <ResultBadge result={results[s.id]} />}
                      {s.manual && <Badge>Terminal</Badge>}
                    </span>
                  </button>
                );
              })}
            </div>
          ))}
        </LayoutGroup>
      </aside>
      <AnimatePresence mode="wait">
        <ScenarioDetail
          key={scenario.id}
          scenario={scenario}
          policy={policy.data}
          labUp={labUp}
          go={go}
          openTarget={openTarget}
          openIncident={openIncident}
        />
      </AnimatePresence>
    </div>
  );
}
