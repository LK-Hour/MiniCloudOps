import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useCreateTarget, useUpdateTarget } from "../api/hooks.js";
import { Modal, useToast } from "../components/overlay.jsx";
import { Button, Switch } from "../components/ui.jsx";

const EMPTY = { name: "", target_url: "", check_interval: 30, enabled: true };

function Field({ label, error, hint, children }) {
  return (
    <label className={`field ${error ? "has-error" : ""}`}>
      <span className="field-label">{label}</span>
      {children}
      <AnimatePresence initial={false} mode="wait">
        {error ? (
          <motion.span key="e" className="field-error" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            {error}
          </motion.span>
        ) : (
          hint && <span className="field-hint">{hint}</span>
        )}
      </AnimatePresence>
    </label>
  );
}

/** Add or edit a target. `target` null = create. */
export default function TargetForm({ open, target, onClose }) {
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const create = useCreateTarget();
  const update = useUpdateTarget();
  const toast = useToast();
  const saving = create.isPending || update.isPending;

  useEffect(() => {
    if (open) {
      setForm(target ? { name: target.name, target_url: target.target_url, check_interval: target.check_interval, enabled: target.enabled } : EMPTY);
      setErrors({});
    }
  }, [open, target]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e?.target ? e.target.value : e }));

  const submit = async (e) => {
    e.preventDefault();
    const body = { ...form, name: form.name.trim(), target_url: form.target_url.trim(), check_interval: Number(form.check_interval) };
    try {
      if (target) await update.mutateAsync({ id: target.id, ...body });
      else await create.mutateAsync(body);
      toast({ tone: "success", title: target ? "Target updated" : "Target added", message: body.name });
      onClose();
    } catch (err) {
      const fields = err.fieldErrors ?? {};
      setErrors(fields);
      if (!Object.keys(fields).length) toast({ tone: "error", title: "Could not save target", message: err.message });
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={target ? "Edit target" : "Add target"}>
      <form className="form" onSubmit={submit} noValidate>
        <Field label="Name" error={errors.name}>
          <input autoFocus value={form.name} onChange={set("name")} placeholder="Payments API" maxLength={120} required />
        </Field>
        <Field label="Health check URL" error={errors.target_url} hint="http or https. Internal and metadata addresses are blocked.">
          <input value={form.target_url} onChange={set("target_url")} placeholder="http://demo-app/health" inputMode="url" required />
        </Field>
        <Field label="Check every (seconds)" error={errors.check_interval} hint="10 – 3600">
          <input type="number" min={10} max={3600} value={form.check_interval} onChange={set("check_interval")} required />
        </Field>
        <div className="field-row">
          <span>
            <span className="field-label">Monitoring enabled</span>
            <span className="field-hint">Disabled targets are not checked.</span>
          </span>
          <Switch checked={form.enabled} onChange={set("enabled")} label="Monitoring enabled" />
        </div>
        <footer className="form-actions">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={saving}>
            {target ? "Save changes" : "Add target"}
          </Button>
        </footer>
      </form>
    </Modal>
  );
}
