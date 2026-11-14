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
