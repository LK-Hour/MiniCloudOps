import { useEffect, useId } from "react";
import { animate, motion, useMotionValue, useTransform } from "framer-motion";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";

export const spring = { type: "spring", stiffness: 420, damping: 34, mass: 0.8 };
export const ease = [0.22, 1, 0.36, 1];

const STATUS_LABEL = { UP: "Up", DOWN: "Down", UNKNOWN: "Unknown", DISABLED: "Disabled" };

export function StatusDot({ status, size = 10 }) {
  const tone = (status ?? "UNKNOWN").toLowerCase();
  return (
    <span className={`dot dot-${tone}`} style={{ "--size": `${size}px` }} aria-hidden="true">
      {status === "DOWN" && <span className="dot-ring" />}
    </span>
  );
}

export function StatusPill({ status }) {
  return (
    <span className={`pill pill-${(status ?? "UNKNOWN").toLowerCase()}`}>
      <StatusDot status={status} size={7} />
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function Badge({ tone = "neutral", children, title }) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

export const severityTone = { CRITICAL: "danger", WARNING: "warning", INFO: "info" };
export const incidentTone = { OPEN: "danger", ACKNOWLEDGED: "warning", RESOLVED: "success" };

/** Segmented control with a sliding highlight. options: [{value, label, count?}] */
export function Segmented({ options, value, onChange, size = "md" }) {
  const id = useId();
  return (
    <div className={`segmented segmented-${size}`} role="tablist">
      {options.map((o) => (
        <button
          key={o.value}
          role="tab"
          aria-selected={value === o.value}
          className={value === o.value ? "active" : ""}
          onClick={() => onChange(o.value)}
        >
          {value === o.value && <motion.span layoutId={`seg-${id}`} className="segmented-pill" transition={spring} />}
          <span className="segmented-label">
            {o.label}
            {o.count != null && <span className="segmented-count">{o.count}</span>}
          </span>
        </button>
      ))}
    </div>
  );
}

/** A number that tweens to its new value. `format` turns it into text. */
export function AnimatedNumber({ value, format = (v) => Math.round(v).toString() }) {
  const mv = useMotionValue(value ?? 0);
  const text = useTransform(mv, (v) => format(v));
  useEffect(() => {
    if (value == null) return undefined;
    const controls = animate(mv, value, { duration: 0.6, ease });
    return () => controls.stop();
  }, [value, mv]);
  if (value == null) return <span>—</span>;
  return <motion.span>{text}</motion.span>;
}

/** Horizontal usage bar. null renders as "no data", never as an empty 0% bar. */
export function Meter({ value, warn = 70, danger = 85, label, detail }) {
  const tone = value == null ? "none" : value >= danger ? "danger" : value >= warn ? "warning" : "ok";
  return (
    <div className="meter">
      {label && (
        <div className="meter-head">
          <span className="meter-label">{label}</span>
          <span className="meter-value num">{value == null ? "no data" : `${value.toFixed(1)}%`}</span>
        </div>
      )}
      <div className={`meter-track meter-${tone}`}>
        {value != null && (
          <motion.div
            className="meter-fill"
            initial={{ width: 0 }}
            animate={{ width: `${Math.min(100, Math.max(value, 1))}%` }}
            transition={{ duration: 0.8, ease }}
          />
        )}
      </div>
      {detail && <span className="meter-detail">{detail}</span>}
    </div>
  );
}

export function Switch({ checked, onChange, disabled, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className={`switch ${checked ? "on" : ""}`}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
    >
      <motion.span className="switch-thumb" layout transition={spring} />
    </button>
  );
}

export function Card({ title, action, children, className = "", ...rest }) {
  return (
    <motion.section className={`card ${className}`} {...rest}>
      {(title || action) && (
        <header className="card-head">
          {title && <h3>{title}</h3>}
          {action}
        </header>
      )}
      {children}
    </motion.section>
  );
}

export function EmptyState({ icon: Icon = Inbox, title, children }) {
  return (
    <motion.div className="empty" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
      <span className="empty-icon">
        <Icon size={20} />
      </span>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </motion.div>
  );
}

/** Inline error for one data source: the rest of the dashboard keeps working. */
export function ErrorState({ error, source }) {
  return (
    <div className="error-state" role="alert">
      <AlertTriangle size={16} />
      <div>
        <strong>{source} unavailable</strong>
        <p>
          {error?.message ?? "Request failed"}
          {error?.correlationId && <span className="mono"> · {error.correlationId}</span>}
        </p>
      </div>
    </div>
  );
}

export function Skeleton({ rows = 4, height = 44 }) {
  return (
    <div className="skeleton-list">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ height, animationDelay: `${i * 80}ms` }} />
      ))}
    </div>
  );
}

export function Spinner({ size = 14 }) {
  return <Loader2 size={size} className="spin" />;
}

export function Button({ variant = "secondary", size = "md", loading, icon: Icon, children, ...props }) {
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      className={`btn btn-${variant} btn-${size}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? <Spinner /> : Icon && <Icon size={size === "sm" ? 14 : 16} />}
      {children && <span>{children}</span>}
    </motion.button>
  );
}

export const listItem = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.28, ease } },
  exit: { opacity: 0, x: -12, transition: { duration: 0.18 } },
};
