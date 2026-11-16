import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import { CornerDownLeft, FileText, Moon, Plus, Search, Siren, Target } from "lucide-react";
import { useIncidents, useTargets } from "../api/hooks.js";
import { DOC_PAGES } from "../views/Docs.jsx";
import { StatusDot, spring } from "./ui.jsx";

/** Ctrl/⌘ K: jump to any page, target, incident or doc, or run a quick action. */
export default function CommandPalette({ open, onClose, pages, go, openTarget, openIncident, cycleTheme }) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef(null);
  const listRef = useRef(null);
  const targets = useTargets();
  const incidents = useIncidents();

  useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
      setTimeout(() => input.current?.focus(), 10);
    }
  }, [open]);

  const items = useMemo(() => {
    const all = [
      ...pages.map((p) => ({ group: "Pages", label: p.label, hint: p.group, icon: p.icon, run: () => go(p.id) })),
      { group: "Actions", label: "Add target", icon: Plus, run: () => go("targets", "new") },
      { group: "Actions", label: "Switch theme", icon: Moon, run: cycleTheme },
      ...(targets.data ?? []).map((t) => ({
        group: "Targets",
        label: t.name,
        hint: t.target_url,
        dot: t.enabled ? t.status : "DISABLED",
        icon: Target,
        run: () => openTarget(t.id),
      })),
      ...(incidents.data ?? [])
        .filter((i) => i.status !== "RESOLVED")
        .map((i) => ({ group: "Active incidents", label: i.title, hint: i.severity, icon: Siren, run: () => openIncident(i.id) })),
      ...DOC_PAGES.map((d) => ({ group: "Documentation", label: d.title, hint: d.group, icon: FileText, run: () => go("docs", d.id) })),
    ];
    const q = query.trim().toLowerCase();
    if (!q) return all.filter((i) => i.group !== "Documentation" || i.hint === "Guides").slice(0, 40);
    return all.filter((i) => `${i.label} ${i.hint ?? ""} ${i.group}`.toLowerCase().includes(q)).slice(0, 40);
  }, [query, pages, targets.data, incidents.data, go, openTarget, openIncident, cycleTheme]);

  useEffect(() => setIndex(0), [query]);
  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: "nearest" });
  }, [index]);

  const run = (item) => {
    onClose();
    item?.run();
  };

  const onKey = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIndex((i) => Math.min(items.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIndex((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(items[index]);
    } else if (e.key === "Escape") {
      onClose();
    }
  };

  let lastGroup = null;
  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="overlay-root palette-root">
          <motion.div className="scrim" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.div
            className="palette"
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            initial={{ opacity: 0, scale: 0.97, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0, transition: spring }}
            exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.12 } }}
          >
            <label className="palette-input">
              <Search size={17} />
              <input
                ref={input}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onKey}
                placeholder="Search pages, targets, incidents, docs…"
                aria-activedescendant={`cmd-${index}`}
              />
              <kbd>Esc</kbd>
            </label>
            <div className="palette-list" ref={listRef} role="listbox">
              {items.length === 0 && <p className="palette-empty">No results for “{query}”</p>}
              {items.map((item, i) => {
                const header = item.group !== lastGroup ? item.group : null;
                lastGroup = item.group;
                const Icon = item.icon;
                return (
                  <div key={`${item.group}-${item.label}-${i}`}>
                    {header && <div className="palette-group">{header}</div>}
                    <button
                      id={`cmd-${i}`}
                      data-index={i}
                      role="option"
                      aria-selected={i === index}
                      className={`palette-item ${i === index ? "active" : ""}`}
                      onMouseMove={() => setIndex(i)}
                      onClick={() => run(item)}
                    >
                      {i === index && <motion.span layoutId="palette-active" className="palette-active" transition={{ type: "spring", stiffness: 600, damping: 40 }} />}
                      <span className="palette-icon">{item.dot ? <StatusDot status={item.dot} size={8} /> : Icon && <Icon size={15} />}</span>
                      <span className="palette-label truncate">{item.label}</span>
                      {item.hint && <span className="palette-hint truncate">{item.hint}</span>}
                      {i === index && <CornerDownLeft size={13} className="palette-enter" />}
                    </button>
                  </div>
                );
              })}
            </div>
            <footer className="palette-foot">
              <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
              <span><kbd>↵</kbd> open</span>
              <span><kbd>1</kbd>–<kbd>8</kbd> pages</span>
            </footer>
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
