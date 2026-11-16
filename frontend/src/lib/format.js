const units = [
  ["d", 86_400_000],
  ["h", 3_600_000],
  ["m", 60_000],
  ["s", 1_000],
];

/** "2h 5m", "45s" */
export function duration(ms, parts = 2) {
  if (ms == null || Number.isNaN(ms)) return "—";
  if (ms < 1000) return "0s";
  const out = [];
  let rest = ms;
  for (const [label, size] of units) {
    const n = Math.floor(rest / size);
    if (n > 0 || out.length) {
      if (n > 0) out.push(`${n}${label}`);
      rest -= n * size;
    }
    if (out.length === parts) break;
  }
  return out.join(" ");
}

export function timeAgo(iso, now = Date.now()) {
  if (!iso) return "never";
  const diff = now - new Date(iso).getTime();
  if (diff < 5_000) return "just now";
  return `${duration(diff, 1)} ago`;
}

export function clockTime(iso) {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function dateTime(iso) {
  return new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export const ms = (v) => (v == null ? "—" : v < 1000 ? `${Math.round(v)} ms` : `${(v / 1000).toFixed(2)} s`);
export const pct = (v, digits = 1) => (v == null ? "—" : `${v.toFixed(digits)}%`);

export function bytes(v) {
  if (v == null) return "—";
  const steps = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (v >= 1024 && i < steps.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${steps[i]}`;
}

export const shortId = (id) => (id ? id.slice(0, 8) : "—");
