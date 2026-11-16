"""Screens of the Telegram bot: text (Telegram HTML) plus inline buttons. Pure functions, no I/O.

Callback data (64 bytes max) names what a button does:
    menu | status | targets | incidents | services | help      navigate (the message is edited)
    tgt:<target_id>                                           one target's details
    chk:<target_id> | ack:<incident_id> | res:<incident_id>    actions from a screen
    a-chk:<target_id> | a-ack:<incident_id>                   actions from an alert (answered below it)
    quiet:<minutes> | quiet:off                               alerts without sound
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape

from app.alert_templates import _parse, _recent, _zone, duration
from app.platform import SERVICES, Snapshot

MAX_ROWS = 20  # targets or incidents listed with their own button


@dataclass(frozen=True)
class View:
    text: str
    buttons: list[list[dict]]


def button(text: str, data: str) -> dict:
    return {"text": text, "callback_data": data}


NAV = [button("📊 Status", "status"), button("📋 Targets", "targets"), button("🚨 Incidents", "incidents")]
BACK = [button("⬅ Menu", "menu")]

COMMANDS = [
    ("status", "Overview: targets, incidents, services"),
    ("menu", "Main menu with buttons"),
    ("targets", "Every target and its health"),
    ("incidents", "Active incidents, with acknowledge and resolve"),
    ("check", "Check a target now: /check <name>"),
    ("services", "Health of the MiniOps services"),
    ("quiet", "Alerts without sound: /quiet 30, /quiet off"),
    ("help", "What this bot can do"),
]


class Clock:
    """Formats times in the configured zone, relative to one `now`."""

    def __init__(self, timezone: str, now: datetime | None = None):
        self.zone = _zone(timezone)
        self.now = now or datetime.now(UTC)

    def time(self, value) -> str:
        moment = _parse(value)
        return moment.astimezone(self.zone).strftime("%H:%M") if moment else "—"

    def ago(self, value) -> str:
        moment = _parse(value)
        return f"{duration((self.now - moment).total_seconds())} ago" if moment else "never"

    def stamp(self) -> str:
        return self.now.astimezone(self.zone).strftime("%H:%M %Z")


def _ms(value) -> str:
    return "—" if value is None else f"{round(value)} ms"


def target_icon(target: dict, state: dict | None) -> str:
    if not target.get("enabled", True):
        return "⏸"
    status = (state or {}).get("status") or target.get("status")
    return {"UP": "🟢", "DOWN": "🔴"}.get(status, "⚪")


def _unavailable(snap: Snapshot) -> str:
    if not snap.errors:
        return ""
    return "\n\n⚠️ <i>" + escape("; ".join(snap.errors)) + "</i>"


# --- screens ----------------------------------------------------------------------------------------


def menu(quiet_until: datetime | None, clock: Clock) -> View:
    sound = f"🔕 Quiet until {clock.time(quiet_until)}" if quiet_until else "🔔 Alerts with sound"
    text = "🤖 <b>MiniOps</b>\n" "Monitoring for your applications. Pick what you want to see.\n\n" f"{sound}"
    quiet = button("🔔 Sound on", "quiet:off") if quiet_until else button("🔕 Quiet 30 min", "quiet:30")
    return View(
        text,
        [
            [button("📊 Status", "status"), button("📋 Targets", "targets")],
            [button("🚨 Incidents", "incidents"), button("🩺 Services", "services")],
            [quiet, button("❓ Help", "help")],
        ],
    )


def status(
    snap: Snapshot, health: dict[str, bool] | None, quiet_until: datetime | None, clock: Clock
) -> View:
    lines = [f"📊 <b>MiniOps status</b> · {clock.stamp()}", ""]

    if snap.targets is None:
        lines.append("Targets    ⚠️ unavailable")
        down = []
    else:
        counts = {"🟢": 0, "🔴": 0, "⚪": 0, "⏸": 0}
        down = []
        for t in snap.targets:
            icon = target_icon(t, (snap.states or {}).get(t["id"]))
            counts[icon] += 1
            if icon == "🔴":
                down.append(t)
        parts = [f"🟢 {counts['🟢']} up", f"🔴 {counts['🔴']} down"]
        if counts["⚪"]:
            parts.append(f"⚪ {counts['⚪']} not checked yet")
        if counts["⏸"]:
            parts.append(f"⏸ {counts['⏸']} paused")
        lines.append("Targets    " + " · ".join(parts))

    if snap.incidents is None:
        lines.append("Incidents  ⚠️ unavailable")
    else:
        opened = sum(1 for i in snap.incidents if i["status"] == "OPEN")
        acked = len(snap.incidents) - opened
        lines.append(
            "Incidents  "
            + ("✅ none active" if not snap.incidents else f"🚨 {opened} open · 👀 {acked} acknowledged")
        )

    if health is not None:
        healthy = sum(health.values())
        mark = "✅" if healthy == len(health) else "⚠️"
        lines.append(f"Services   {mark} {healthy}/{len(health)} healthy")
    lines.append(
        "Alerts     " + (f"🔕 quiet until {clock.time(quiet_until)}" if quiet_until else "🔔 with sound")
    )

    if down:
        lines += ["", "<b>Down now</b>"]
        for t in down[:MAX_ROWS]:
            state = (snap.states or {}).get(t["id"]) or {}
            failures = state.get("consecutive_failures")
            detail = f" · {failures} failed checks" if failures else ""
            lines.append(
                f"🔴 {escape(t['name'])}{detail} · last check {clock.ago(state.get('last_checked_at'))}"
            )

    buttons = [[button("🔄 Refresh", "status"), button("📋 Targets", "targets")]]
    if snap.incidents:
        buttons[0].append(button(f"🚨 Incidents ({len(snap.incidents)})", "incidents"))
    buttons.append(BACK)
    return View("\n".join(lines) + _unavailable(snap), buttons)


def targets(snap: Snapshot, clock: Clock) -> View:
    if snap.targets is None:
        return View("📋 <b>Targets</b>\n\n⚠️ The Target Service is unavailable." + _unavailable(snap), [BACK])
    if not snap.targets:
        return View("📋 <b>Targets</b>\n\nNo targets yet. Add one in the dashboard.", [BACK])

    order = {"🔴": 0, "⚪": 1, "🟢": 2, "⏸": 3}
    rows = sorted(
        snap.targets,
        key=lambda t: (order[target_icon(t, (snap.states or {}).get(t["id"]))], t["name"].lower()),
    )
    lines = [f"📋 <b>Targets</b> ({len(rows)}) · {clock.stamp()}", ""]
    for t in rows:
        state = (snap.states or {}).get(t["id"]) or {}
        icon = target_icon(t, state)
        if icon == "⏸":
            detail = "paused"
        elif icon == "🔴":
            detail = f"down · {state.get('consecutive_failures', 0)} failed checks"
        elif icon == "🟢":
            detail = _ms(state.get("last_response_time_ms"))
        else:
            detail = "not checked yet"
        lines.append(f"{icon} <b>{escape(t['name'])}</b> — {detail}")
    buttons = [
        [button(f"{target_icon(t, (snap.states or {}).get(t['id']))} {t['name'][:28]}", f"tgt:{t['id']}")]
        for t in rows[:MAX_ROWS]
    ]
    buttons.append([button("🔄 Refresh", "targets"), *BACK])
    return View("\n".join(lines) + _unavailable(snap), buttons)


def target(snap: Snapshot, target_id: str, history: list[dict] | None, clock: Clock) -> View:
    t = snap.target(target_id)
    if t is None:
        return View("This target no longer exists.", [[button("📋 Targets", "targets"), *BACK]])
    state = (snap.states or {}).get(target_id) or {}
    icon = target_icon(t, state)
    status_text = {"🟢": "UP", "🔴": "DOWN", "⚪": "not checked yet", "⏸": "paused"}[icon]
    rows = [
        ("Status", f"{status_text}"),
        ("URL", t["target_url"]),
        ("Every", duration(t.get("check_interval"))),
        ("Last check", clock.ago(state.get("last_checked_at"))),
        ("Response", _ms(state.get("last_response_time_ms"))),
    ]
    if state.get("consecutive_failures"):
        rows.append(("Failures", f"{state['consecutive_failures']} in a row"))
    width = max(len(k) for k, _ in rows)
    facts = "\n".join(f"{k.ljust(width)}  {escape(str(v))}" for k, v in rows)
    text = f"{icon} <b>{escape(t['name'])}</b>\n<pre>{facts}</pre>"

    if history:
        marks = _recent(history)
        text += f"\n📊 <b>Latest checks</b> (newest first)\n<code>{escape(marks)}</code>"
        error = next((c.get("error") for c in history if c["status"] == "DOWN" and c.get("error")), None)
        if error and icon == "🔴":
            text += f"\n❌ {escape(error)}"
    incident_id = state.get("open_incident_id")
    if incident_id:
        text += f"\n\n🚨 Open incident <code>{escape(incident_id[:8])}</code>"

    buttons = []
    if t.get("enabled", True):
        buttons.append([button("▶ Check now", f"chk:{target_id}"), button("🔄 Refresh", f"tgt:{target_id}")])
    if incident_id:
        buttons.append(
            [button("✅ Acknowledge", f"ack:{incident_id}"), button("✔ Resolve", f"res:{incident_id}")]
        )
    buttons.append([button("📋 Targets", "targets"), *BACK])
    return View(text, buttons)


def incidents(snap: Snapshot, clock: Clock) -> View:
    if snap.incidents is None:
        return View(
            "🚨 <b>Incidents</b>\n\n⚠️ The Incident Service is unavailable." + _unavailable(snap), [BACK]
        )
    if not snap.incidents:
        return View(
            "🚨 <b>Incidents</b>\n\n✅ No active incidents. Everything is fine.",
            [[button("🔄 Refresh", "incidents"), *BACK]],
        )
    lines = [f"🚨 <b>Active incidents</b> ({len(snap.incidents)}) · {clock.stamp()}", ""]
    buttons = []
    for i in snap.incidents[:MAX_ROWS]:
        state = "🚨 OPEN" if i["status"] == "OPEN" else "👀 ACKNOWLEDGED"
        target = snap.target(i["target_id"])
        name = target["name"] if target else i["title"]
        lines.append(
            f"{state} · <b>{escape(i['title'])}</b>\n"
            f"    {escape(i['severity'])} · since {clock.time(i['created_at'])} "
            f"({clock.ago(i['created_at'])}) · <code>{escape(i['id'][:8])}</code>"
        )
        row = []
        if i["status"] == "OPEN":
            row.append(button(f"✅ Ack {name[:18]}", f"ack:{i['id']}"))
        row.append(button(f"✔ Resolve {name[:18]}", f"res:{i['id']}"))
        buttons.append(row)
    buttons.append([button("🔄 Refresh", "incidents"), *BACK])
    return View("\n".join(lines) + _unavailable(snap), buttons)


def services(health: dict[str, bool], clock: Clock) -> View:
    lines = [f"🩺 <b>MiniOps services</b> · {clock.stamp()}", ""]
    for name in SERVICES:
        lines.append(f"{'✅' if health.get(name) else '❌'} {name.capitalize()} Service")
    if not all(health.values()):
        lines += [
            "",
            "A ❌ service is stopped or cannot reach its database.",
            "Check with <code>docker compose ps</code>.",
        ]
    return View("\n".join(lines), [[button("🔄 Refresh", "services"), *BACK]])


def help_view() -> View:
    lines = ["❓ <b>What I can do</b>", ""]
    lines += [f"/{name} — {escape(text)}" for name, text in COMMANDS]
    lines += [
        "",
        "Alerts arrive here when an incident opens or resolves, with buttons to acknowledge it or "
        "check the target again.",
    ]
    return View("\n".join(lines), [BACK])


def check_result(name: str, ok: bool, message: str, result: dict | None) -> str:
    if not ok:
        return f"⚠️ Could not check <b>{escape(name)}</b>: {escape(message)}"
    up = result["status"] == "UP"
    code = (
        f"HTTP {result['status_code']}" if result.get("status_code") else (result.get("error") or "no answer")
    )
    took = f" in {_ms(result['response_time_ms'])}" if result.get("response_time_ms") is not None else ""
    return f"{'🟢' if up else '🔴'} <b>{escape(name)}</b> is {'UP' if up else 'DOWN'}: {escape(code)}{took}"


def choose_target(snap: Snapshot, query: str) -> View:
    """/check without a match: buttons for every enabled target."""
    options = [t for t in snap.targets or [] if t.get("enabled", True)]
    head = f"No target matches “{escape(query)}”. " if query else ""
    if not options:
        return View(head + "There is no enabled target to check.", [BACK])
    buttons = [[button(f"▶ {t['name'][:30]}", f"chk:{t['id']}")] for t in options[:MAX_ROWS]]
    return View(head + "Which target should I check?", [*buttons, BACK])


def unknown_command() -> View:
    help_ = help_view()
    return View("I don't know that command.\n\n" + help_.text, help_.buttons)
