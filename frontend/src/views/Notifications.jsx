import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BellRing, CheckCheck, CircleAlert, CircleCheck } from "lucide-react";
import { useMarkRead, useNotifications } from "../api/hooks.js";
import { useToast } from "../components/overlay.jsx";
import { Badge, Button, EmptyState, ErrorState, Segmented, Skeleton, listItem, severityTone } from "../components/ui.jsx";
import { dateTime, timeAgo } from "../lib/format.js";
import { useNow } from "../lib/hooks.js";

function dayLabel(iso) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86_400_000);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" });
}

export default function Notifications({ openIncident }) {
  const now = useNow(5000);
  const notifications = useNotifications();
  const markRead = useMarkRead();
  const toast = useToast();
  const [filter, setFilter] = useState("all");

  const list = notifications.data ?? [];
  const unread = list.filter((n) => !n.read);
  const visible = filter === "unread" ? unread : list;
  const groups = useMemo(() => {
    const out = [];
    for (const n of visible) {
      const label = dayLabel(n.created_at);
      if (out.at(-1)?.label !== label) out.push({ label, items: [] });
      out.at(-1).items.push(n);
    }
    return out;
  }, [visible]);

  const open = (n) => {
    if (!n.read) markRead.mutate([n.id]);
    openIncident(n.incident_id);
  };

  return (
    <div className="stack">
      <div className="toolbar">
        <Segmented
          options={[
            { value: "all", label: "All", count: list.length },
            { value: "unread", label: "Unread", count: unread.length },
          ]}
          value={filter}
          onChange={setFilter}
        />
        <Button
          icon={CheckCheck}
          disabled={!unread.length}
          onClick={() =>
            markRead.mutate(
              unread.map((n) => n.id),
              { onError: (err) => toast({ tone: "error", title: "Could not mark as read", message: err.message }) },
            )
          }
        >
          Mark all read
        </Button>
      </div>
      {notifications.isError && <ErrorState error={notifications.error} source="Notification Service" />}
      {!notifications.data && !notifications.isError && <Skeleton rows={4} height={64} />}
      {notifications.data && visible.length === 0 && (
        <EmptyState icon={BellRing} title={filter === "unread" ? "You're all caught up" : "No notifications yet"}>
          Notifications appear when incidents open or resolve.
        </EmptyState>
      )}
      {groups.map((g) => (
        <section key={g.label} className="notif-group">
          <h4 className="section-title">{g.label}</h4>
          <div className="notif-list">
            <AnimatePresence initial={false}>
              {g.items.map((n) => {
                const resolved = n.event_type === "INCIDENT_RESOLVED";
                const Icon = resolved ? CircleCheck : CircleAlert;
                return (
                  <motion.button key={n.id} layout {...listItem} className={`notif ${n.read ? "read" : "unread"}`} onClick={() => open(n)}>
                    <span className={`notif-icon ${resolved ? "tone-success" : "tone-danger"}`}>
                      <Icon size={16} />
                    </span>
                    <div className="notif-main">
                      <div className="notif-top">
                        <strong className="truncate">{n.title}</strong>
                        {n.severity && !resolved && <Badge tone={severityTone[n.severity]}>{n.severity}</Badge>}
                      </div>
                      <p className="notif-msg">{n.message}</p>
                      <span className="muted small" title={dateTime(n.created_at)}>
                        {timeAgo(n.created_at, now)} · {n.channel}
                      </span>
                    </div>
                    <AnimatePresence>
                      {!n.read && (
                        <motion.span className="unread-dot" initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }} aria-label="Unread" />
                      )}
                    </AnimatePresence>
                  </motion.button>
                );
              })}
            </AnimatePresence>
          </div>
        </section>
      ))}
    </div>
  );
}
