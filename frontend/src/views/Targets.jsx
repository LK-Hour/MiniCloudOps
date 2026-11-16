import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Pencil, Play, Plus, Search, Target as TargetIcon, Trash2 } from "lucide-react";
import { useCheckNow, useDeleteTarget, useTargetRows, useToggleTarget } from "../api/hooks.js";
import { Sparkline } from "../components/charts.jsx";
import { Modal, useToast } from "../components/overlay.jsx";
import { Button, EmptyState, ErrorState, Segmented, Skeleton, StatusPill, Switch, listItem } from "../components/ui.jsx";
import { ms, timeAgo } from "../lib/format.js";
import { useNow } from "../lib/hooks.js";
import TargetForm from "./TargetForm.jsx";

const FILTERS = ["all", "UP", "DOWN", "UNKNOWN", "disabled"];
const LABELS = { all: "All", UP: "Up", DOWN: "Down", UNKNOWN: "Pending", disabled: "Disabled" };

function matches(row, filter) {
  if (filter === "all") return true;
  if (filter === "disabled") return !row.enabled;
  return row.enabled && row.health === filter;
}

export function useTargetActions() {
  const toast = useToast();
  const check = useCheckNow();
  const toggle = useToggleTarget();
  return {
    check: (t) =>
      check.mutate(t.id, {
        onSuccess: (r) =>
          toast({
            tone: r.status === "UP" ? "success" : "error",
            title: `${t.name} is ${r.status === "UP" ? "up" : "down"}`,
            message: r.status === "UP" ? `Responded in ${ms(r.response_time_ms)}` : r.error,
          }),
        onError: (err) => toast({ tone: "error", title: "Check failed", message: err.message }),
      }),
    checking: check.isPending ? check.variables : null,
    toggle: (t, enabled) =>
      toggle.mutate(
        { id: t.id, enabled },
        {
          onSuccess: () => toast({ tone: "info", title: `${t.name} ${enabled ? "enabled" : "disabled"}` }),
          onError: (err) => toast({ tone: "error", title: "Could not update target", message: err.message }),
        },
      ),
  };
}

export function DeleteTargetDialog({ target, onClose, onDeleted }) {
  const remove = useDeleteTarget();
  const toast = useToast();
  return (
    <Modal open={Boolean(target)} onClose={onClose} title="Delete target?" width={420}>
      <p className="modal-text">
        <strong>{target?.name}</strong> will stop being monitored. Its check history and incidents are kept.
      </p>
      <footer className="form-actions">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="danger"
          loading={remove.isPending}
          onClick={() =>
            remove.mutate(target.id, {
              onSuccess: () => {
                toast({ tone: "success", title: "Target deleted", message: target.name });
                onClose();
                onDeleted?.();
              },
              onError: (err) => toast({ tone: "error", title: "Could not delete", message: err.message }),
            })
          }
        >
          Delete
        </Button>
      </footer>
    </Modal>
  );
}

export default function Targets({ openTarget, sub, go }) {
  const now = useNow(1000);
  const { rows, targets } = useTargetRows();
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(undefined); // undefined closed, null new, object edit
  const creating = sub === "new"; // #/targets/new, used by links and the command palette
  const [deleting, setDeleting] = useState(null);
  const actions = useTargetActions();

  const counts = useMemo(
    () => Object.fromEntries(FILTERS.map((f) => [f, rows?.filter((r) => matches(r, f)).length ?? 0])),
    [rows],
  );
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (rows ?? []).filter(
      (r) => matches(r, filter) && (!q || r.name.toLowerCase().includes(q) || r.target_url.toLowerCase().includes(q)),
    );
  }, [rows, filter, query]);

  return (
    <div className="stack">
      <div className="toolbar">
        <Segmented
          options={FILTERS.map((f) => ({ value: f, label: LABELS[f], count: counts[f] }))}
          value={filter}
          onChange={setFilter}
        />
        <div className="toolbar-right">
          <label className="search">
            <Search size={15} />
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search targets" />
          </label>
          <Button variant="primary" icon={Plus} onClick={() => go("targets", "new")}>
            Add target
          </Button>
        </div>
      </div>

      {targets.isError && <ErrorState error={targets.error} source="Target Service" />}

      <div className="table" role="table">
        <div className="table-head" role="row">
          <span>Target</span>
          <span>Status</span>
          <span className="hide-sm">Response</span>
          <span className="hide-md">Trend</span>
          <span className="hide-md">Last check</span>
          <span>Monitor</span>
          <span />
        </div>
        {!rows && !targets.isError && <Skeleton rows={4} height={56} />}
        {rows && visible.length === 0 && (
          <EmptyState icon={TargetIcon} title={rows.length ? "No matching targets" : "No targets yet"}>
            {rows.length ? "Try another filter or search." : "Add an application's health URL to start monitoring it."}
          </EmptyState>
        )}
        <AnimatePresence initial={false}>
          {visible.map((t) => (
            <motion.div key={t.id} layout {...listItem} className={`table-row ${t.enabled ? "" : "is-disabled"}`} role="row" onClick={() => openTarget(t.id)}>
              <span className="cell-main">
                <strong className="truncate">{t.name}</strong>
                <span className="mono muted truncate">{t.target_url}</span>
              </span>
              <span>
                <StatusPill status={t.enabled ? t.health : "DISABLED"} />
                {t.monitor?.consecutive_failures > 0 && t.enabled && (
                  <span className="fail-count" title="Consecutive failed checks">
                    ×{t.monitor.consecutive_failures}
                  </span>
                )}
              </span>
              <span className="num hide-sm">{t.enabled ? ms(t.monitor?.last_response_time_ms) : "—"}</span>
              <span className="hide-md">
                <Sparkline points={t.monitor?.recent} />
              </span>
              <span className="muted small hide-md">
                {t.enabled ? timeAgo(t.monitor?.last_checked_at, now) : "paused"}
                <span className="block">every {t.check_interval}s</span>
              </span>
              <span>
                <Switch checked={t.enabled} onChange={(v) => actions.toggle(t, v)} label={`Monitor ${t.name}`} />
              </span>
              <span className="row-actions" onClick={(e) => e.stopPropagation()}>
                <button className="icon-btn" title="Check now" disabled={!t.enabled} onClick={() => actions.check(t)}>
                  <motion.span animate={actions.checking === t.id ? { rotate: 360 } : { rotate: 0 }} transition={actions.checking === t.id ? { repeat: Infinity, duration: 0.8, ease: "linear" } : {}}>
                    <Play size={15} />
                  </motion.span>
                </button>
                <button className="icon-btn" title="Edit" onClick={() => setEditing(t)}>
                  <Pencil size={15} />
                </button>
                <button className="icon-btn danger" title="Delete" onClick={() => setDeleting(t)}>
                  <Trash2 size={15} />
                </button>
              </span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      <TargetForm
        open={creating || editing !== undefined}
        target={creating ? null : editing}
        onClose={() => (creating ? go("targets") : setEditing(undefined))}
      />
      <DeleteTargetDialog target={deleting} onClose={() => setDeleting(null)} />
    </div>
  );
}
