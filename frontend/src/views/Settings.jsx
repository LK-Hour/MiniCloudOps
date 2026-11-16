import { useState } from "react";
import { motion } from "framer-motion";
import { BellRing, RotateCcw, Send } from "lucide-react";
import { api } from "../api/client.js";
import { useChannels, usePolicy } from "../api/hooks.js";
import { useToast } from "../components/overlay.jsx";
import { Badge, Button, ErrorState, Segmented, Skeleton, Switch, ease } from "../components/ui.jsx";
import { DEFAULTS, useSettings } from "../lib/settings.jsx";

const rise = { initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease } } };

function Section({ title, description, children }) {
  return (
    <motion.section variants={rise} className="settings-section">
      <div className="settings-intro">
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </div>
      <div className="settings-body">{children}</div>
    </motion.section>
  );
}

function Row({ label, hint, children }) {
  return (
    <div className="setting-row">
      <div>
        <span className="setting-label">{label}</span>
        {hint && <span className="setting-hint">{hint}</span>}
      </div>
      <div className="setting-control">{children}</div>
    </div>
  );
}

const permission = () => (typeof Notification === "undefined" ? "unsupported" : Notification.permission);

const POLICY_ROWS = [
  ["default_check_interval_seconds", "Default check interval", (v) => `${v} s`, "DEFAULT_CHECK_INTERVAL_SECONDS"],
  ["failure_threshold", "Failures before an incident", (v) => `${v} in a row`, "FAILURE_THRESHOLD"],
  ["response_time_threshold_ms", "Slow response threshold", (v) => `${v} ms`, "RESPONSE_TIME_THRESHOLD_MS"],
  ["check_timeout_seconds", "Request timeout", (v) => `${v} s`, "CHECK_TIMEOUT_SECONDS"],
  ["scheduler_tick_seconds", "Scheduler tick", (v) => `${v} s`, "SCHEDULER_TICK_SECONDS"],
  ["history_retention_days", "Check history kept", (v) => `${v} days`, "HISTORY_RETENTION_DAYS"],
  ["ssrf_allow_private_networks", "Private-network targets", (v) => (v ? "Allowed" : "Blocked"), "SSRF_ALLOW_PRIVATE_NETWORKS"],
];

export const PAGE_OPTIONS = [
  { value: "overview", label: "Overview" },
  { value: "targets", label: "Targets" },
  { value: "incidents", label: "Incidents" },
  { value: "infrastructure", label: "Infrastructure" },
];

export default function Settings() {
  const { settings, update, reset } = useSettings();
  const policy = usePolicy();
  const toast = useToast();
  const [perm, setPerm] = useState(permission);
  const channels = useChannels();
  const [testing, setTesting] = useState(false);
  const telegramOn = channels.data?.telegram?.enabled;

  const testTelegram = async () => {
    setTesting(true);
    try {
      await api("/notifications/channels/telegram/test", { method: "POST" });
      toast({ tone: "success", title: "Test message sent to Telegram" });
    } catch (err) {
      toast({ tone: "error", title: "Telegram test failed", message: err.message });
    } finally {
      setTesting(false);
    }
  };

  const toggleAlerts = async (on) => {
    if (!on) return update({ desktopAlerts: false });
    if (perm === "unsupported") return toast({ tone: "error", title: "This browser does not support notifications" });
    const result = perm === "granted" ? "granted" : await Notification.requestPermission();
    setPerm(result);
    if (result === "granted") {
      update({ desktopAlerts: true });
      toast({ tone: "success", title: "Desktop alerts on", message: "You'll be alerted when an incident opens or resolves." });
    } else {
      toast({ tone: "error", title: "Permission denied", message: "Allow notifications for this site in your browser settings." });
    }
  };

  return (
    <motion.div className="settings" initial="initial" animate="animate" variants={{ animate: { transition: { staggerChildren: 0.05 } } }}>
      <Section title="Appearance" description="Stored in this browser only.">
        <Row label="Theme">
          <Segmented
            options={[
              { value: "system", label: "System" },
              { value: "light", label: "Light" },
              { value: "dark", label: "Dark" },
            ]}
            value={settings.theme}
            onChange={(theme) => update({ theme })}
          />
        </Row>
        <Row label="Animations" hint="System follows your OS “reduce motion” setting.">
          <Segmented
            options={[
              { value: "system", label: "System" },
              { value: "full", label: "Full" },
              { value: "reduce", label: "Reduced" },
            ]}
            value={settings.motion}
            onChange={(motion) => update({ motion })}
          />
        </Row>
      </Section>

      <Section title="Data" description="How often the dashboard asks the APIs for fresh data.">
        <Row label="Refresh interval" hint="Refreshing pauses automatically while this tab is in the background.">
          <Segmented
            options={[
              { value: 5, label: "5s" },
              { value: 10, label: "10s" },
              { value: 30, label: "30s" },
              { value: 60, label: "1m" },
              { value: 0, label: "Paused" },
            ]}
            value={settings.refreshSeconds}
            onChange={(refreshSeconds) => update({ refreshSeconds })}
          />
        </Row>
        <Row label="Start page" hint="Opened when you visit the dashboard without a link.">
          <select className="select" value={settings.startPage} onChange={(e) => update({ startPage: e.target.value })}>
            {PAGE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </Row>
      </Section>

      <Section title="Notifications" description="Incident notifications always appear in the Notifications page. Desktop alerts and Telegram are optional extra channels.">
        <Row
          label="Desktop alerts"
          hint={
            perm === "denied"
              ? "Blocked by the browser. Allow notifications for this site to turn this on."
              : perm === "unsupported"
                ? "Not supported by this browser."
                : "Show a system notification when an incident opens or resolves, while this dashboard is open."
          }
        >
          <Switch checked={settings.desktopAlerts && perm === "granted"} onChange={toggleAlerts} disabled={perm === "unsupported"} label="Desktop alerts" />
        </Row>
        {settings.desktopAlerts && perm === "granted" && (
          <Row label="Test" hint="Sends a sample alert to this device.">
            <Button size="sm" icon={BellRing} onClick={() => new Notification("MiniOps test alert", { body: "Desktop alerts are working." })}>
              Send test
            </Button>
          </Row>
        )}
        <Row
          label="Telegram alerts"
          hint={
            channels.isError
              ? "Could not reach the Notification Service."
              : telegramOn
                ? "On: every new incident and recovery is also sent to your Telegram chat."
                : "Off. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env, then restart the Notification Service."
          }
        >
          {telegramOn ? (
            <Button size="sm" icon={Send} onClick={testTelegram} disabled={testing}>
              {testing ? "Sending…" : "Send test"}
            </Button>
          ) : (
            <Badge>{channels.isLoading ? "…" : "Not configured"}</Badge>
          )}
        </Row>
      </Section>

      <Section title="Monitoring policy" description="Applies to every target. Set by the administrator through environment variables; read-only here.">
        {policy.isError && <ErrorState error={policy.error} source="Monitoring Service" />}
        {policy.isLoading && <Skeleton rows={4} height={40} />}
        {policy.data && (
          <div className="policy">
            {POLICY_ROWS.map(([key, label, fmt, env]) => (
              <div key={key} className="policy-row">
                <span>{label}</span>
                <span className="num policy-value">{fmt(policy.data[key])}</span>
                <span className="mono muted">{env}</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section title="Reset" description="Restore every preference on this page to its default.">
        <Row label="Preferences">
          <Button
            icon={RotateCcw}
            disabled={JSON.stringify(settings) === JSON.stringify(DEFAULTS)}
            onClick={() => {
              reset();
              toast({ tone: "info", title: "Preferences reset" });
            }}
          >
            Reset to defaults
          </Button>
        </Row>
      </Section>
    </motion.div>
  );
}
