import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { ease, spring } from "./ui.jsx";

function useEscape(open, onClose) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
}

function useFocusOnOpen(open) {
  const ref = useRef(null);
  useEffect(() => {
    if (open) ref.current?.focus();
  }, [open]);
  return ref;
}

/** Side sheet for details. */
export function Drawer({ open, onClose, title, subtitle, actions, children }) {
  useEscape(open, onClose);
  const ref = useFocusOnOpen(open);
  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="overlay-root">
          <motion.div className="scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.aside
            ref={ref}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label={typeof title === "string" ? title : undefined}
            className="drawer"
            initial={{ x: "100%" }}
            animate={{ x: 0, transition: { type: "spring", stiffness: 380, damping: 38 } }}
            exit={{ x: "100%", transition: { duration: 0.22, ease } }}
          >
            <header className="drawer-head">
              <div className="drawer-title">
                {title}
                {subtitle && <span className="drawer-subtitle">{subtitle}</span>}
              </div>
              <button className="icon-btn" onClick={onClose} aria-label="Close">
                <X size={18} />
              </button>
            </header>
            {actions && <div className="drawer-actions">{actions}</div>}
            <div className="drawer-body">{children}</div>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

export function Modal({ open, onClose, title, children, width = 460 }) {
  useEscape(open, onClose);
  const ref = useFocusOnOpen(open);
  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="overlay-root center">
          <motion.div className="scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.div
            ref={ref}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className="modal"
            style={{ maxWidth: width }}
            initial={{ opacity: 0, scale: 0.96, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0, transition: spring }}
            exit={{ opacity: 0, scale: 0.97, y: 8, transition: { duration: 0.15 } }}
          >
            <header className="modal-head">
              <h2>{title}</h2>
              <button className="icon-btn" onClick={onClose} aria-label="Close">
                <X size={18} />
              </button>
            </header>
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

// --- toasts -----------------------------------------------------------------------------------

const ToastContext = createContext(() => {});
export const useToast = () => useContext(ToastContext);
const ICONS = { success: CheckCircle2, error: XCircle, info: Info };

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const dismiss = useCallback((id) => setToasts((all) => all.filter((t) => t.id !== id)), []);
  const toast = useCallback(
    ({ tone = "info", title, message, timeout = 4000 }) => {
      const id = crypto.randomUUID();
      setToasts((all) => [...all.slice(-3), { id, tone, title, message }]);
      setTimeout(() => dismiss(id), timeout);
    },
    [dismiss],
  );
  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="toasts" aria-live="polite">
        <AnimatePresence initial={false}>
          {toasts.map((t) => {
            const Icon = ICONS[t.tone];
            return (
              <motion.div
                key={t.id}
                layout
                className={`toast toast-${t.tone}`}
                initial={{ opacity: 0, y: 16, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1, transition: spring }}
                exit={{ opacity: 0, x: 40, transition: { duration: 0.18 } }}
              >
                <Icon size={16} />
                <div>
                  <strong>{t.title}</strong>
                  {t.message && <p>{t.message}</p>}
                </div>
                <button className="icon-btn" onClick={() => dismiss(t.id)} aria-label="Dismiss">
                  <X size={14} />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}
