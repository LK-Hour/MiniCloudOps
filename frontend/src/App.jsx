import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, LayoutGroup, MotionConfig, motion } from "framer-motion";
import {
  Activity,
  Bell,
  BookOpen,
  FlaskConical,
  Info,
  LayoutDashboard,
  Menu,
  Monitor,
  Moon,
  Search,
  Server,
  Settings as SettingsIcon,
  Siren,
  Sun,
  Target,
  X,
} from "lucide-react";
import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useIncidents, useNotifications, useTargets } from "./api/hooks.js";
import CommandPalette from "./components/CommandPalette.jsx";
import { ease, spring } from "./components/ui.jsx";
import { useDesktopAlerts } from "./lib/alerts.js";
import { timeAgo } from "./lib/format.js";
import { useNow, useRoute } from "./lib/hooks.js";
import { useSettings } from "./lib/settings.jsx";
import About, { BUILD } from "./views/About.jsx";
import Demo, { DEMO_TABS } from "./views/Demo.jsx";
import Docs, { DOC_PAGES } from "./views/Docs.jsx";
import Incidents from "./views/Incidents.jsx";
import IncidentDrawer from "./views/IncidentDrawer.jsx";
import Infrastructure from "./views/Infrastructure.jsx";
import Notifications from "./views/Notifications.jsx";
import Overview from "./views/Overview.jsx";
import Settings from "./views/Settings.jsx";
import TargetDrawer from "./views/TargetDrawer.jsx";
import Targets from "./views/Targets.jsx";

const PAGES = [
  { id: "overview", label: "Overview", group: "Monitor", icon: LayoutDashboard, view: Overview, description: "Health of everything MiniOps watches, at a glance." },
  { id: "targets", label: "Targets", group: "Monitor", icon: Target, view: Targets, description: "Applications checked over HTTP on a schedule." },
  { id: "incidents", label: "Incidents", group: "Monitor", icon: Siren, view: Incidents, description: "Outages detected by health checks, from open to resolved." },
  { id: "notifications", label: "Notifications", group: "Monitor", icon: Bell, view: Notifications, description: "Messages sent when incidents open or resolve." },
  { id: "infrastructure", label: "Infrastructure", group: "Monitor", icon: Server, view: Infrastructure, description: "Host and container resources, services and alerts, from Prometheus." },
  { id: "demo", label: "Demo Lab", group: "Lab", icon: FlaskConical, view: Demo, description: "Run experiments against the live platform, follow the logs, and see how it is built and shipped." },
  { id: "docs", label: "Documentation", group: "Resources", icon: BookOpen, view: Docs, description: null },
  { id: "settings", label: "Settings", group: "System", icon: SettingsIcon, view: Settings, description: "Preferences for this browser and the monitoring policy in effect." },
  { id: "about", label: "About", group: "System", icon: Info, view: About, description: "Version, components and how MiniOps is built." },
];
const PAGE_IDS = PAGES.map((p) => p.id);
const GROUPS = [...new Set(PAGES.map((p) => p.group))];
const THEME_ICON = { system: Monitor, light: Sun, dark: Moon };
const NEXT_THEME = { system: "light", light: "dark", dark: "system" };
const MOTION = { system: "user", reduce: "always", full: "never" };
const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** Live / degraded / offline, from every active query in the cache. */
function LiveIndicator({ compact }) {
  const client = useQueryClient();
  const fetching = useIsFetching();
  const now = useNow(1000);
  const { settings } = useSettings();
  const queries = client.getQueryCache().getAll().filter((q) => q.getObserversCount() > 0);
  const failing = queries.filter((q) => q.state.status === "error");
  const lastUpdate = Math.max(0, ...queries.map((q) => q.state.dataUpdatedAt));
  const offline = failing.some((q) => q.state.error?.status === 0);
  const paused = !settings.refreshSeconds;
  const state = offline ? "offline" : failing.length ? "degraded" : paused ? "paused" : "live";
  const label = { live: "Live", degraded: "Degraded", offline: "Offline", paused: "Paused" }[state];
  const title = failing.length ? failing.map((q) => `${q.queryKey.join("/")}: ${q.state.error?.message}`).join("\n") : "All APIs responding";

  return (
    <div className={`live live-${state}`} title={title}>
      <span className="live-dot">
        <motion.span
          className="live-pulse"
          animate={fetching ? { scale: [1, 2.4], opacity: [0.6, 0] } : { scale: 1, opacity: 0 }}
          transition={fetching ? { duration: 1.1, repeat: Infinity, ease: "easeOut" } : { duration: 0.2 }}
        />
      </span>
      <span className="live-label">{label}</span>
      {!compact && lastUpdate > 0 && <span className="live-time">· {timeAgo(new Date(lastUpdate).toISOString(), now)}</span>}
    </div>
  );
}

function useBadges() {
  const targets = useTargets();
  const incidents = useIncidents();
  const notifications = useNotifications();
  return {
    targets: targets.data?.filter((t) => t.enabled && t.status === "DOWN").length || null,
    incidents: incidents.data?.filter((i) => i.status !== "RESOLVED").length || null,
    notifications: notifications.data?.filter((n) => !n.read).length || null,
  };
}

function Sidebar({ page, go, badges, onNavigate }) {
  return (
    <div className="sidebar-inner">
      <a className="brand" href="#/overview" onClick={onNavigate}>
        <span className="brand-mark">
          <Activity size={16} strokeWidth={2.5} />
        </span>
        <span>MiniOps</span>
        <span className="env-chip" title="Environment">{window.location.hostname === "localhost" ? "local" : window.location.hostname}</span>
      </a>
      <nav className="nav" aria-label="Main">
        <LayoutGroup id="nav">
          {GROUPS.map((group) => (
            <div key={group} className="nav-group">
              <span className="nav-label">{group}</span>
              {PAGES.filter((p) => p.group === group).map((p) => {
                const Icon = p.icon;
                const active = p.id === page;
                const n = PAGE_IDS.indexOf(p.id) + 1;
                return (
                  <button
                    key={p.id}
                    className={`nav-item ${active ? "active" : ""}`}
                    onClick={() => {
                      go(p.id);
                      onNavigate?.();
                    }}
                    aria-current={active ? "page" : undefined}
                    title={`${p.label} (${n})`}
                  >
                    {active && <motion.span layoutId="nav-active" className="nav-active" transition={spring} />}
                    <Icon size={16} className="nav-icon" />
                    <span className="nav-text">{p.label}</span>
                    <AnimatePresence>
                      {badges[p.id] && (
                        <motion.span
                          key={badges[p.id]}
                          className={`nav-badge ${p.id === "notifications" ? "accent" : "danger"}`}
                          initial={{ scale: 0.5, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          exit={{ scale: 0.5, opacity: 0 }}
                          transition={spring}
                        >
                          {badges[p.id]}
                        </motion.span>
                      )}
                    </AnimatePresence>
                  </button>
                );
              })}
            </div>
          ))}
        </LayoutGroup>
      </nav>
      <div className="sidebar-foot">
        <LiveIndicator />
        <span className="mono muted version">v{BUILD.version} · {BUILD.sha.slice(0, 7)}</span>
      </div>
    </div>
  );
}

export default function App() {
  const { settings, update } = useSettings();
  const [route, go] = useRoute(PAGE_IDS, settings.startPage);
  const [targetId, setTargetId] = useState(null);
  const [incidentId, setIncidentId] = useState(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const badges = useBadges();

  const openTarget = useCallback((id) => {
    setIncidentId(null);
    setTargetId(id);
  }, []);
  const openIncident = useCallback((id) => {
    setTargetId(null);
    setIncidentId(id);
  }, []);
  const cycleTheme = useCallback(() => update({ theme: NEXT_THEME[settings.theme] }), [settings.theme, update]);
  useDesktopAlerts(openIncident);

  // Ctrl/⌘ K opens the palette; 1–9 switch pages when not typing.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey || /input|textarea|select/i.test(e.target.tagName) || document.querySelector("[role=dialog]")) return;
      const index = Number(e.key) - 1;
      if (index >= 0 && index < PAGES.length) go(PAGES[index].id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

  const down = badges.targets;
  const page = PAGES.find((p) => p.id === route.page);
  useEffect(() => {
    document.title = `${down ? `(${down} down) ` : ""}${page.label} · MiniOps`;
  }, [down, page.label]);

  const View = page.view;
  const ThemeIcon = THEME_ICON[settings.theme];
  const docTitle =
    route.page === "docs"
      ? (DOC_PAGES.find((d) => d.id === route.sub) ?? DOC_PAGES[0]).title
      : route.page === "demo"
        ? (DEMO_TABS.find((t) => t.id === route.sub?.split("/")[0]) ?? DEMO_TABS[0]).label
        : null;

  return (
    <MotionConfig reducedMotion={MOTION[settings.motion]}>
      <div className="app">
        <aside className="sidebar">
          <Sidebar page={route.page} go={go} badges={badges} />
        </aside>

        <AnimatePresence>
          {menuOpen && (
            <div className="overlay-root mobile-nav">
              <motion.div className="scrim" onClick={() => setMenuOpen(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
              <motion.aside
                className="sidebar sidebar-mobile"
                initial={{ x: "-100%" }}
                animate={{ x: 0, transition: { type: "spring", stiffness: 380, damping: 38 } }}
                exit={{ x: "-100%", transition: { duration: 0.2, ease } }}
              >
                <button className="icon-btn sidebar-close" onClick={() => setMenuOpen(false)} aria-label="Close menu">
                  <X size={18} />
                </button>
                <Sidebar page={route.page} go={go} badges={badges} onNavigate={() => setMenuOpen(false)} />
              </motion.aside>
            </div>
          )}
        </AnimatePresence>

        <div className="main">
          <header className="topbar">
            <button className="icon-btn menu-btn" onClick={() => setMenuOpen(true)} aria-label="Open menu">
              <Menu size={18} />
            </button>
            <nav className="crumbs" aria-label="Breadcrumb">
              <span className="muted">{page.group}</span>
              <span className="crumb-sep">/</span>
              <span className={docTitle ? "muted" : ""}>{page.label}</span>
              {docTitle && (
                <>
                  <span className="crumb-sep">/</span>
                  <span>{docTitle}</span>
                </>
              )}
            </nav>
            <div className="topbar-right">
              <button className="search-trigger" onClick={() => setPaletteOpen(true)}>
                <Search size={15} />
                <span className="hide-sm">Search…</span>
                <kbd className="hide-sm">{isMac ? "⌘" : "Ctrl"} K</kbd>
              </button>
              <span className="topbar-live">
                <LiveIndicator compact />
              </span>
              <button className="icon-btn" onClick={cycleTheme} title={`Theme: ${settings.theme}`} aria-label={`Theme: ${settings.theme}`}>
                <AnimatePresence mode="wait" initial={false}>
                  <motion.span key={settings.theme} initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.2 }} style={{ display: "flex" }}>
                    <ThemeIcon size={17} />
                  </motion.span>
                </AnimatePresence>
              </button>
            </div>
          </header>

          <main className="content">
            <AnimatePresence mode="wait">
              <motion.div
                key={route.page}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0, transition: { duration: 0.3, ease } }}
                exit={{ opacity: 0, y: -6, transition: { duration: 0.15 } }}
              >
                {page.description && (
                  <div className="page-head">
                    <h1>{page.label}</h1>
                    <p>{page.description}</p>
                  </div>
                )}
                <View go={go} sub={route.sub} openTarget={openTarget} openIncident={openIncident} />
              </motion.div>
            </AnimatePresence>
          </main>
        </div>

        <TargetDrawer id={targetId} onClose={() => setTargetId(null)} openIncident={openIncident} />
        <IncidentDrawer id={incidentId} onClose={() => setIncidentId(null)} openTarget={openTarget} />
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          pages={PAGES}
          go={go}
          openTarget={openTarget}
          openIncident={openIncident}
          cycleTheme={cycleTheme}
        />
      </div>
    </MotionConfig>
  );
}
