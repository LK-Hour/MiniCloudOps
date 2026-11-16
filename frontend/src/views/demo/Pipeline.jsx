import { useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, CircleDashed, Clock, ExternalLink, GitBranch, GitCommit, Loader2, Package, XCircle } from "lucide-react";
import { REPO_PATTERN, useGithubJobs, useGithubRuns } from "../../api/hooks.js";
import { Badge, Button, Card, ErrorState, Skeleton, ease } from "../../components/ui.jsx";
import { duration, timeAgo } from "../../lib/format.js";
import { useSettings } from "../../lib/settings.jsx";
import { BUILD } from "../About.jsx";
import { C, Callout, Code } from "../Docs.jsx";

const IMAGES = ["target-service", "monitoring-service", "incident-service", "notification-service", "frontend"];
const SERVICES = IMAGES.slice(0, 4);

// Mirrors .github/workflows/ci-cd.yml. Job names match GitHub's, so live runs colour this graph.
const STAGES = [
  {
    id: "validate",
    n: 1,
    title: "Source validation",
    jobs: ["Source validation"],
    steps: ["Checkout", "Python 3.12", "ruff check services tests", "docker compose config -q"],
    local: "make lint\ncp -n .env.example .env && docker compose config -q",
  },
  {
    id: "test",
    n: 2,
    title: "Automated tests",
    jobs: [...SERVICES.map((s) => `Test ${s}`), "Build frontend"],
    steps: ["Matrix: one job per service, fail-fast off", "pip install -r requirements-dev.txt", "pytest -q", "npm ci && npm run build"],
    local: "make test\ncd frontend && npm ci && npm run build",
  },
  {
    id: "build",
    n: 3,
    title: "Build & publish images",
    jobs: IMAGES.map((s) => `Image ${s}`),
    steps: ["Docker Buildx with GitHub Actions layer cache", "Tags from docker/metadata-action", "GIT_SHA build argument", "Push to GHCR (not for pull requests)"],
    local: "make build",
  },
  {
    id: "deploy",
    n: 4,
    title: "Deploy",
    jobs: ["make deploy"],
    manual: true,
    steps: ["docker compose pull", "docker compose up -d --no-build", "scripts/healthcheck.sh through the gateway"],
    local: "make deploy",
  },
];

const TRIGGERS = [
  ["push", "main, develop"],
  ["tag", "v*"],
  ["pull_request", "into main, develop"],
  ["workflow_dispatch", "manual"],
];

const TAGS = [
  ["Push to main", "latest · main · sha-<commit>", true],
  ["Push to develop", "develop · sha-<commit>", true],
  ["Tag v1.2.3", "1.2.3 · sha-<commit>", true],
  ["Pull request", "built to validate, not pushed", false],
];

function jobState(job) {
  if (!job) return "idle";
  if (job.status !== "completed") return job.status === "in_progress" ? "running" : "queued";
  return { success: "success", failure: "failure", cancelled: "cancelled", skipped: "skipped" }[job.conclusion] ?? "neutral";
}

const STATE_ICON = {
  idle: CircleDashed,
  queued: Clock,
  running: Loader2,
  success: CheckCircle2,
  failure: XCircle,
  cancelled: XCircle,
  skipped: CircleDashed,
  neutral: CircleDashed,
};

function runState(run) {
  if (!run) return "idle";
  if (run.status !== "completed") return run.status === "in_progress" ? "running" : "queued";
  return run.conclusion === "success" ? "success" : run.conclusion === "failure" ? "failure" : "cancelled";
}

const elapsed = (a, b) => (a && b ? duration(new Date(b) - new Date(a)) : "—");

function PipelineGraph({ jobs }) {
  const byName = Object.fromEntries((jobs ?? []).map((j) => [j.name, j]));
  return (
    <div className="pipe">
      {STAGES.map((stage, i) => (
        <motion.div
          key={stage.id}
          className="pipe-stage"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0, transition: { delay: i * 0.06, duration: 0.3, ease } }}
        >
          {i > 0 && <span className="pipe-link" />}
          <span className="pipe-stage-title">
            <span className="pipe-n">{stage.n}</span>
            {stage.title}
          </span>
          <div className="pipe-jobs">
            {stage.jobs.map((name) => {
              const job = byName[name];
              const state = stage.manual ? "manual" : jobState(job);
              const Icon = STATE_ICON[state] ?? Package;
              return (
                <a
                  key={name}
                  className={`pipe-job job-${state}`}
                  href={job?.html_url}
                  target="_blank"
                  rel="noreferrer"
                  title={job ? `${job.status} ${job.conclusion ?? ""}` : stage.manual ? "Run on the server" : "No run selected"}
                >
                  <Icon size={14} className={state === "running" ? "spin" : ""} />
                  <span className="pipe-job-name">{name.replace(/^(Test|Image) /, "")}</span>
                  {job?.completed_at && <span className="mono muted small">{elapsed(job.started_at, job.completed_at)}</span>}
                </a>
              );
            })}
          </div>
        </motion.div>
      ))}
    </div>
  );
}

function ConnectRepo() {
  const { settings, update } = useSettings();
  const [value, setValue] = useState(settings.githubRepo ?? "");
  const valid = REPO_PATTERN.test(value.trim());
  return (
    <form
      className="repo-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) update({ githubRepo: value.trim() });
      }}
    >
      <label className="search">
        <GitBranch size={15} />
        <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="owner/repository" spellCheck={false} aria-label="GitHub repository" />
      </label>
      <Button type="submit" size="sm" variant="primary" disabled={!valid}>
        Connect
      </Button>
      {settings.githubRepo && (
        <Button type="button" size="sm" onClick={() => { update({ githubRepo: "" }); setValue(""); }}>
          Disconnect
        </Button>
      )}
    </form>
  );
}

function Runs({ repo, selectedId, onSelect }) {
  const runs = useGithubRuns(repo);
  if (!repo) {
    return (
      <div className="runs-empty">
        <p className="muted small">
          Connect the public GitHub repository to see live workflow runs. Requests go from your browser to api.github.com
          (60 per hour without a token); nothing else is sent.
        </p>
        <ConnectRepo />
      </div>
    );
  }
  if (runs.isLoading) return <Skeleton rows={4} height={48} />;
  if (runs.isError) return (
    <>
      <ErrorState error={runs.error} source={`GitHub Actions for ${repo}`} />
      <ConnectRepo />
    </>
  );
  const list = runs.data.workflow_runs ?? [];
  if (!list.length) return <p className="muted small">No runs of ci-cd.yml yet. Push a commit to start one.</p>;
  return (
    <ul className="runs">
      {list.map((run) => {
        const state = runState(run);
        const Icon = STATE_ICON[state];
        return (
          <li key={run.id}>
            <button className={`run-row ${run.id === selectedId ? "active" : ""}`} onClick={() => onSelect(run.id)}>
              <Icon size={16} className={`run-icon job-${state} ${state === "running" ? "spin" : ""}`} />
              <span className="run-main">
                <span className="run-title">{run.display_title}</span>
                <span className="muted small">
                  #{run.run_number} · {run.event} · <GitBranch size={11} /> {run.head_branch} · <GitCommit size={11} /> <span className="mono">{run.head_sha.slice(0, 7)}</span>
                </span>
              </span>
              <span className="run-side muted small">
                <span>{timeAgo(run.run_started_at ?? run.created_at)}</span>
                <span className="mono">{state === "running" ? "running" : elapsed(run.run_started_at, run.updated_at)}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export default function Pipeline() {
  const { settings } = useSettings();
  const repo = REPO_PATTERN.test(settings.githubRepo ?? "") ? settings.githubRepo : "";
  const runs = useGithubRuns(repo);
  const [picked, setPicked] = useState(null);
  const latest = runs.data?.workflow_runs?.[0];
  const selectedId = picked ?? latest?.id;
  const selected = runs.data?.workflow_runs?.find((r) => r.id === selectedId);
  const jobs = useGithubJobs(repo, selectedId);
  const owner = repo ? repo.split("/")[0].toLowerCase() : "<owner>";
  const deployedRun = runs.data?.workflow_runs?.find((r) => r.head_sha === BUILD.sha);
  const sha = BUILD.sha.length > 12 ? BUILD.sha.slice(0, 7) : BUILD.sha;

  return (
    <div className="stack">
      <Card
        title="Pipeline"
        action={
          <span className="muted small">
            {selected ? (
              <a className="link small" href={selected.html_url} target="_blank" rel="noreferrer">
                Run #{selected.run_number} on GitHub <ExternalLink size={12} />
              </a>
            ) : (
              <span className="mono">.github/workflows/ci-cd.yml</span>
            )}
          </span>
        }
      >
        <div className="pipe-meta">
          {TRIGGERS.map(([event, scope]) => (
            <span key={event} className="chip">
              <span className="mono">{event}</span> <span className="muted">{scope}</span>
            </span>
          ))}
          <span className="chip muted">Newer pushes cancel older runs on the same branch</span>
        </div>
        <PipelineGraph jobs={jobs.data?.jobs} />
        {!repo && <p className="muted small pipe-hint">Connect the repository below to colour each job with the latest run's result.</p>}
      </Card>

      <div className="grid-2">
        <Card title="Recent runs" action={repo && <span className="mono muted small">{repo}</span>}>
          <Runs repo={repo} selectedId={selectedId} onSelect={setPicked} />
        </Card>

        <div className="stack">
          <Card title="This deployment">
            <dl className="kv">
              <div>
                <dt>Dashboard build</dt>
                <dd className="mono">
                  v{BUILD.version} · {sha}
                </dd>
              </div>
              <div>
                <dt>Built</dt>
                <dd>{new Date(BUILD.time).toLocaleString()}</dd>
              </div>
              <div>
                <dt>Source</dt>
                <dd>
                  {BUILD.sha === "local" ? (
                    <span className="muted">Local build, not from CI</span>
                  ) : deployedRun ? (
                    <a className="link" href={deployedRun.html_url} target="_blank" rel="noreferrer">
                      Run #{deployedRun.run_number} <ExternalLink size={12} />
                    </a>
                  ) : (
                    <span className="muted">Commit {sha}</span>
                  )}
                </dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>
                  {!latest ? (
                    <span className="muted">—</span>
                  ) : latest.head_sha === BUILD.sha ? (
                    <Badge tone="success">Up to date</Badge>
                  ) : (
                    <Badge tone="warning">Newer commit on {latest.head_branch}</Badge>
                  )}
                </dd>
              </div>
            </dl>
          </Card>

          <Card title="Image tags">
            <div className="tag-table">
              {TAGS.map(([event, tags, pushed]) => (
                <div key={event} className="tag-row">
                  <span className="small">{event}</span>
                  <span className="mono small">{tags}</span>
                  <Badge tone={pushed ? "success" : "neutral"}>{pushed ? "pushed" : "build only"}</Badge>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <Card title="Stages in detail">
        <div className="stage-grid">
          {STAGES.map((s) => (
            <section key={s.id} className="stage-card">
              <span className="pipe-stage-title">
                <span className="pipe-n">{s.n}</span>
                {s.title}
              </span>
              <ul className="stage-steps">
                {s.steps.map((step) => (
                  <li key={step} className="small">
                    {step}
                  </li>
                ))}
              </ul>
              <span className="eyebrow">Run it locally</span>
              <Code>{s.local}</Code>
            </section>
          ))}
        </div>
      </Card>

      <div className="grid-2">
        <Card title="Registry">
          <ul className="image-list">
            {IMAGES.map((name) => (
              <li key={name} className="mono small">
                <Package size={13} /> ghcr.io/{owner}/miniops-{name}
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Security of the pipeline">
          <ul className="checklist">
            {[
              <>Workflow token is read-only by default; only the image job gets <C>packages: write</C></>,
              <>Pull requests build images but never push them or log in to the registry</>,
              <>No long-lived secrets: GHCR uses the run's own <C>GITHUB_TOKEN</C></>,
              <>Real passwords live in <C>.env</C>, which is git-ignored; CI uses <C>.env.example</C></>,
            ].map((text, i) => (
              <li key={i}>
                <CheckCircle2 size={14} className="ok" />
                <span>{text}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {repo && (
        <Callout title="Connected repository">
          Live data from <C>{repo}</C>. <ConnectRepo />
        </Callout>
      )}
    </div>
  );
}
