import { LayoutGroup, motion } from "framer-motion";
import { Boxes, FlaskConical, GitBranch, ScrollText } from "lucide-react";
import { spring } from "../components/ui.jsx";
import Logs from "./demo/Logs.jsx";
import Pipeline from "./demo/Pipeline.jsx";
import Scenarios from "./demo/Scenarios.jsx";
import Services from "./demo/Services.jsx";

export const DEMO_TABS = [
  { id: "scenarios", label: "Scenarios", icon: FlaskConical },
  { id: "services", label: "Microservices", icon: Boxes },
  { id: "logs", label: "Logs", icon: ScrollText },
  { id: "pipeline", label: "CI/CD", icon: GitBranch },
];

export default function Demo({ sub, go, openTarget, openIncident }) {
  const [tabId = "scenarios", ...rest] = (sub ?? "").split("/").filter(Boolean);
  const tab = DEMO_TABS.find((t) => t.id === tabId) ?? DEMO_TABS[0];
  const arg = rest.join("/") || undefined;

  return (
    <div className="stack">
      <nav className="tabs" aria-label="Demo sections">
        <LayoutGroup id="demo-tabs">
          {DEMO_TABS.map((t) => {
            const Icon = t.icon;
            const active = t.id === tab.id;
            return (
              <button key={t.id} className={`tab ${active ? "active" : ""}`} onClick={() => go("demo", t.id)} aria-current={active ? "page" : undefined}>
                <Icon size={16} />
                <span>{t.label}</span>
                {active && <motion.span layoutId="demo-tab-line" className="tab-line" transition={spring} />}
              </button>
            );
          })}
        </LayoutGroup>
      </nav>
      <motion.div key={tab.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22 }}>
        {tab.id === "scenarios" && <Scenarios go={go} openTarget={openTarget} openIncident={openIncident} />}
        {tab.id === "services" && <Services service={arg} go={go} />}
        {tab.id === "logs" && <Logs correlationId={arg} />}
        {tab.id === "pipeline" && <Pipeline />}
      </motion.div>
    </div>
  );
}
