"""Telegram message templates: one per event, styled by severity, explained by failure kind.

Input is the notification plus its optional `details`, which the Monitoring and Incident services
fill in (README → "Telegram alerts" lists every field). Every field is optional: a template leaves out what
it does not have, and a notification with no details falls back to its title and message.

Output is Telegram HTML (https://core.telegram.org/bots/api#html-style). Everything from the
outside is escaped; only the tags written here are markup.
"""
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TELEGRAM_LIMIT = 4096


@dataclass(frozen=True)
class Style:
    icon: str
    label: str
    silent: bool  # delivered without a sound


SEVERITY = {
    "CRITICAL": Style("🔴", "CRITICAL", silent=False),
    "WARNING": Style("🟠", "WARNING", silent=False),
    "INFO": Style("🔵", "INFO", silent=True),
}
RESOLVED = Style("✅", "RESOLVED", silent=True)
UNKNOWN = Style("⚪", "ALERT", silent=False)


@dataclass(frozen=True)
class Message:
    text: str
    silent: bool


# --- why it failed --------------------------------------------------------------------------------

HTTP_REASONS = {
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    405: "Method Not Allowed", 408: "Request Timeout", 410: "Gone", 429: "Too Many Requests",
    500: "Internal Server Error", 501: "Not Implemented", 502: "Bad Gateway",
    503: "Service Unavailable", 504: "Gateway Timeout",
}

# (likely cause, what to check) per failure kind; HTTP codes refine the http_* kinds.
DIAGNOSIS: dict[str, tuple[str, list[str]]] = {
    "timeout": (
        "The app accepted the connection but did not answer in time. It is hung, overloaded, "
        "or waiting on a slow dependency (database query, external API).",
        ["CPU and memory of its container (MiniOps → Infrastructure)",
         "Slow queries or calls to other services in its logs",
         "Whether the timeout is too short for this endpoint"],
    ),
    "dns": (
        "The host name does not resolve. In Docker this means the container is stopped or was "
        "removed; on the internet, the DNS record changed or the domain expired.",
        ["<code>docker compose ps</code>: is the container running?",
         "The host name in the target URL",
         "The DNS record of the domain"],
    ),
    "connection": (
        "Nothing is accepting connections on that address. The process crashed, is restarting, "
        "listens on another port, or a firewall blocks it.",
        ["<code>docker compose ps</code> and the app's last log lines",
         "Restart loops: <code>docker compose logs --tail 50 &lt;service&gt;</code>",
         "The port in the target URL"],
    ),
    "tls": (
        "The HTTPS handshake failed: the certificate is expired, self-signed, or for another host name.",
        ["Certificate expiry: <code>openssl s_client -connect host:443</code>",
         "Automatic renewal (certbot, the proxy's ACME setup)"],
    ),
    "protocol": (
        "The server hung up mid-answer or answered something that is not HTTP. The app may be "
        "crashing while handling the request, or the URL points at a non-HTTP port.",
        ["The app's logs for a crash at the time of the check",
         "That the port in the URL is the HTTP port"],
    ),
    "blocked": (
        "MiniOps refused to call the URL: its host now resolves to an internal or metadata "
        "address, which SSRF protection blocks.",
        ["Whether the DNS record of the host changed",
         "The target URL, in MiniOps → Targets"],
    ),
    "http_5xx": (
        "The app answered with a server error.",
        ["The app's error logs at the time of the check",
         "Its dependencies (database, cache, other services)",
         "Recent deploys or configuration changes"],
    ),
    "http_4xx": (
        "The app is running but rejected the health check request.",
        ["That the health check URL still exists and allows GET without login",
         "Recent changes to routes or authentication"],
    ),
}

STATUS_CAUSES = {
    500: "The app crashed while handling the request (an unhandled exception).",
    502: "A proxy or load balancer in front of the app cannot reach it: the app process is down or crashed.",
    503: "The app reports itself unavailable: overloaded, in maintenance, or a dependency it needs is down.",
    504: "A proxy in front of the app gave up waiting for it: the app is hung or very slow.",
    401: "The health check URL now requires authentication.",
    403: "The health check URL now refuses access (permissions, IP allow-list or WAF).",
    404: "The health check URL no longer exists: the route moved or was removed in a deploy.",
    405: "The health check URL no longer accepts GET requests.",
    429: "The app is rate-limiting MiniOps: the check interval may be too short.",
}


def diagnose(details: dict) -> tuple[str, list[str]] | None:
    kind = details.get("failure_kind")
    if kind not in DIAGNOSIS:
        return None
    cause, checks = DIAGNOSIS[kind]
    return STATUS_CAUSES.get(details.get("status_code"), cause), checks


def describe_failure(details: dict) -> str | None:
    code = details.get("status_code")
    if code:
        reason = HTTP_REASONS.get(code)
        return f"HTTP {code}" + (f" · {reason}" if reason else "")
    return details.get("error")


# --- formatting helpers ---------------------------------------------------------------------------


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _parse(value) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    seconds = int(max(0, seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {seconds} s" if seconds else f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


def _ms(value) -> str | None:
    return None if value is None else f"{round(float(value))} ms"


def _short(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _facts(rows: list[tuple[str, str | None]]) -> str:
    """Aligned key/value block in monospace. Rows without a value are left out."""
    rows = [(k, v) for k, v in rows if v]
    if not rows:
        return ""
    width = max(len(k) for k, _ in rows)
    return "<pre>" + "\n".join(f"{k.ljust(width)}  {escape(v)}" for k, v in rows) + "</pre>"


def _recent(checks: list[dict]) -> str | None:
    marks = []
    for c in checks[:5]:
        ok = c.get("status") == "UP"
        what = str(c.get("status_code") or ("ok" if ok else "no answer"))
        marks.append(f"{'✓' if ok else '✗'} {what}")
    return "  ".join(marks) if marks else None


def _footer(incident_id: str, dashboard_url: str) -> str:
    short = escape(incident_id[:8])
    if not dashboard_url:
        return f"🆔 Incident <code>{short}</code>"
    link = escape(f"{dashboard_url.rstrip('/')}/#/incidents/{incident_id}", quote=True)
    return f'🆔 Incident <code>{short}</code> · <a href="{link}">Open in MiniOps</a>'


# --- templates ------------------------------------------------------------------------------------


def render(
    *,
    incident_id: str,
    event_type: str,
    severity: str | None,
    title: str,
    message: str,
    details: dict | None,
    dashboard_url: str = "",
    timezone: str = "UTC",
    now: datetime | None = None,
) -> Message:
    details = details or {}
    zone = _zone(timezone)
    now = now or datetime.now(UTC)

    def clock(value) -> str | None:
        moment = _parse(value)
        return moment.astimezone(zone).strftime("%H:%M:%S %Z · %d %b") if moment else None

    if event_type == "INCIDENT_RESOLVED":
        text = _resolved(title, message, details, clock)
        style = RESOLVED
    elif details.get("target_url"):
        style = SEVERITY.get(severity or "", UNKNOWN)
        text = _opened(style, title, details, clock, now)
    else:  # created by hand through the API: no check details to show
        style = SEVERITY.get(severity or "", UNKNOWN)
        header = f"{style.icon} <b>{style.label} · Incident opened</b>"
        text = f"{header}\n\n{_headline(title)}\n{escape(message)}"

    text = f"{text}\n\n{_footer(incident_id, dashboard_url)}"
    if len(text) > TELEGRAM_LIMIT:  # cannot happen with bounded inputs; never send a broken message
        text = f"{style.icon} <b>{escape(_short(title, 200))}</b>\n\n{_footer(incident_id, dashboard_url)}"
    return Message(text=text, silent=style.silent)


def _headline(title: str) -> str:
    # Titles arrive as "[CRITICAL] Shop is unavailable"; the header already says the level.
    if title.startswith("[") and "] " in title:
        title = title.split("] ", 1)[1]
    return f"<b>{escape(title)}</b>"


def _opened(style: Style, title: str, d: dict, clock, now: datetime) -> str:
    failures, threshold = d.get("consecutive_failures"), d.get("failure_threshold")
    streak = None
    if failures:
        streak = f"{failures} failed checks in a row" + (f" (threshold {threshold})" if threshold else "")
    interval = d.get("check_interval_seconds")
    response = _ms(d.get("response_time_ms"))
    if response is None and d.get("failure_kind") == "timeout" and d.get("check_timeout_seconds"):
        response = f"no answer within {d['check_timeout_seconds']:g} s"
    since = clock(d.get("first_failed_at"))
    started = _parse(d.get("first_failed_at"))
    if since and started:
        since = f"{since} ({duration((now - started).total_seconds())} ago)"

    parts = [
        f"{style.icon} <b>{style.label} · Incident opened</b>",
        _headline(title),
        _facts([
            ("Target", d.get("target_name")),
            ("URL", _short(str(d.get("target_url") or ""), 120)),
            ("Failure", describe_failure(d)),
            ("Response", response),
            ("Streak", streak),
            ("Checked", f"every {duration(interval)}" if interval else None),
            ("Failing", since),
        ]),
    ]
    recent = _recent(d.get("recent_checks") or [])
    if recent:
        parts.append(f"📊 <b>Latest checks</b> (newest first)\n<code>{escape(recent)}</code>")
    diagnosis = diagnose(d)
    if diagnosis:
        cause, checks = diagnosis
        parts.append(f"🔎 <b>Likely cause</b>\n{escape(cause)}")
        # The check list is written here (trusted markup), never taken from the input.
        parts.append("🛠 <b>What to check</b>\n" + "\n".join(f"• {c}" for c in checks))
    return "\n\n".join(p for p in parts if p)


def _resolved(title: str, message: str, d: dict, clock) -> str:
    name = d.get("target_name")
    now_ok = None
    if d.get("status_code"):
        took = _ms(d.get("response_time_ms"))
        now_ok = f"HTTP {d['status_code']}" + (f" in {took}" if took else "")
    parts = [
        f"{RESOLVED.icon} <b>RESOLVED · Back to normal</b>",
        f"<b>{escape(name)} is back up</b>" if name else _headline(title),
        _facts([
            ("Target", name),
            ("URL", _short(str(d.get("target_url") or ""), 120)),
            ("Now", now_ok),
            ("Downtime", duration(d.get("duration_seconds"))),
            ("Started", clock(d.get("started_at"))),
            ("Resolved", clock(d.get("resolved_at"))),
        ]),
    ]
    if not d:
        parts.append(escape(message))
    return "\n\n".join(p for p in parts if p)
