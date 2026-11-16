"""Custom Prometheus metrics (docs/MiniCloudOps.md §7.2). Exposed on /metrics."""
from prometheus_client import Counter, Gauge, Histogram

HEALTH_CHECKS = Counter(
    "miniops_health_check_total", "Health checks performed", ["target_id"]
)
HEALTH_CHECK_FAILURES = Counter(
    "miniops_health_check_failures_total", "Failed health checks", ["target_id"]
)
RESPONSE_TIME = Histogram(
    "miniops_http_response_time_seconds", "Response time of monitored targets", ["target_id"]
)
ACTIVE_TARGETS = Gauge("miniops_active_targets", "Enabled targets being monitored")
OPEN_INCIDENTS = Gauge("miniops_open_incidents", "Open incidents as last reported")

# target_id -> current name, so dashboards can show names:
#   ... * on (target_id) group_left (name) miniops_target_info
TARGET_INFO = Gauge(
    "miniops_target_info", "Name of each monitored target (value is always 1)", ["target_id", "name"]
)
_names: dict[str, str] = {}


def set_target_name(target_id: str, name: str) -> None:
    """Record a target's name; a rename replaces the old series so joins stay one-to-one."""
    previous = _names.get(target_id)
    if previous == name:
        return
    if previous is not None:
        TARGET_INFO.remove(target_id, previous)
    TARGET_INFO.labels(target_id, name).set(1)
    _names[target_id] = name


def keep_target_names(target_ids: set[str]) -> None:
    """Drop names of targets that were deleted or disabled, so dashboards list live targets only."""
    for target_id in set(_names) - target_ids:
        TARGET_INFO.remove(target_id, _names.pop(target_id))
