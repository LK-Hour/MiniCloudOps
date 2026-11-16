import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

// Per-browser preferences. Saved in localStorage when available; the app works without it.
const KEY = "miniops-settings";
export const DEFAULTS = {
  theme: "system", // system | light | dark
  motion: "system", // system | reduce | full
  refreshSeconds: 5, // 0 = paused
  startPage: "overview",
  desktopAlerts: false,
  githubRepo: "", // owner/name, for the CI/CD tab
};

function load() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return DEFAULTS;
  }
}

const SettingsContext = createContext(null);

export function SettingsProvider({ children }) {
  const [settings, setSettings] = useState(load);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(settings));
    } catch {
      /* private mode: preferences last for this visit only */
    }
    const root = document.documentElement;
    if (settings.theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", settings.theme);
  }, [settings]);

  const update = useCallback((patch) => setSettings((s) => ({ ...s, ...patch })), []);
  const reset = useCallback(() => setSettings(DEFAULTS), []);
  const value = useMemo(() => ({ settings, update, reset }), [settings, update, reset]);
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export const useSettings = () => useContext(SettingsContext);
