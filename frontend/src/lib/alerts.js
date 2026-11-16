import { useEffect, useRef } from "react";
import { useNotifications } from "../api/hooks.js";
import { useSettings } from "./settings.jsx";

/** Desktop alert for each notification that arrives while the dashboard is open. */
export function useDesktopAlerts(onOpen) {
  const { settings } = useSettings();
  const { data } = useNotifications();
  const seen = useRef(null);

  useEffect(() => {
    if (!data) return;
    const ids = new Set(data.map((n) => n.id));
    if (seen.current === null) {
      seen.current = ids; // first load: only alert on what arrives from now on
      return;
    }
    const fresh = data.filter((n) => !seen.current.has(n.id));
    seen.current = ids;
    if (!settings.desktopAlerts || typeof Notification === "undefined" || Notification.permission !== "granted") return;
    for (const n of fresh.slice(0, 3)) {
      const alert = new Notification(n.title, { body: n.message, tag: n.id });
      alert.onclick = () => {
        window.focus();
        onOpen(n.incident_id);
      };
    }
  }, [data, settings.desktopAlerts, onOpen]);
}
