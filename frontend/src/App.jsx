import { useEffect, useState } from "react";
import { apiGet } from "./api.js";

const PANELS = [
  { key: "targets", title: "Targets", path: "/targets/", render: (t) => `${t.name} — ${t.status}` },
  { key: "incidents", title: "Incidents", path: "/incidents/", render: (i) => `[${i.severity}] ${i.title} — ${i.status}` },
  { key: "notifications", title: "Notifications", path: "/notifications/", render: (n) => n.title },
];

function Panel({ title, path, render }) {
  const [state, setState] = useState({ loading: true, items: [], error: null });

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      apiGet(path)
        .then((items) => !cancelled && setState({ loading: false, items, error: null }))
        .catch((err) => !cancelled && setState({ loading: false, items: [], error: err.message }));
    load();
    const timer = setInterval(load, 15000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [path]);

  return (
    <section className="panel">
      <h2>{title}</h2>
      {state.loading && <p className="muted">Loading…</p>}
      {state.error && <p className="error">Unavailable: {state.error}</p>}
      {!state.loading && !state.error && state.items.length === 0 && <p className="muted">Nothing yet.</p>}
      <ul>
        {state.items.map((item) => (
          <li key={item.id}>{render(item)}</li>
        ))}
      </ul>
    </section>
  );
}

export default function App() {
  return (
    <main>
      <header>
        <h1>MiniOps</h1>
        <p className="muted">Distributed infrastructure monitoring</p>
      </header>
      <div className="grid">
        {PANELS.map((p) => (
          <Panel key={p.key} {...p} />
        ))}
      </div>
    </main>
  );
}
