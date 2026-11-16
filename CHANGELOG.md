# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Telegram bot commands: `/status`, `/menu`, `/targets`, `/incidents`, `/check <name>`, `/services`, `/quiet <minutes|off>` and `/help`, registered in Telegram's command menu.
  - Menu buttons edit one message in place.
  - Alerts have **Acknowledge**, **Check now** and **Status** buttons.
  - The bot long-polls Telegram, so it works on localhost, and answers only the configured chat.
  - `TELEGRAM_COMMANDS_ENABLED=false` turns it off.
- Telegram alert templates. They are styled by severity (CRITICAL and WARNING make a sound; INFO and RESOLVED are silent) and show the target, URL, failure, response time, failure streak, when the failures started and the latest checks. They give a likely cause and what to check for each failure kind and HTTP status. The resolved message shows the downtime. Times use `ALERT_TIMEZONE`.
- Monitoring Service: each failed check is classified (`timeout`, `dns`, `connection`, `tls`, `protocol`, `http_4xx`, `http_5xx`, `blocked`). Outage and recovery details are sent with the incident as `context`.
- Incident Service: forwards that `context`, plus the start time and downtime, to the Notification Service as `details`. Neither is stored.
- Dashboard: `#/incidents/<id>` opens that incident directly. Alerts link to it.
- Notification Service: optional Telegram alerts. New notifications are forwarded in the background when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set; duplicates are never sent twice and the token is never logged. `GET /channels` and `POST /channels/telegram/test`, with a Telegram row in Settings.
- All services: API request metrics `miniops_api_requests_total` and `miniops_api_request_duration_seconds`, labelled by route template. Prometheus adds a `service` label.
- Monitoring Service: `miniops_target_info` maps target IDs to names for dashboards.
- Grafana dashboard rebuilt in five rows: overview, monitored targets (by name, with availability), MiniOps APIs (request rate, p95 latency, 5xx), containers, and warning/error logs.
- Integration tests on the live stack: service readiness, target lifecycle, validation, SSRF, read-only log API, and the full failure → incident → notification → recovery flow with the correlation ID traced in Loki. CI runs them on the full stack before publishing images.
- Documentation: project report, presentation slides, testing documentation, architecture diagram.
- Repository structure following docs/MiniCloudOps.md §9.3.
- FastAPI skeletons for the target, monitoring, incident and notification services: health and readiness endpoints, Prometheus metrics, JSON logging with correlation IDs, standard error responses, SQLAlchemy models, and API route stubs.
- React dashboard skeleton (Vite) with targets, incidents and notifications panels.
- nginx API gateway.
- Docker Compose stack: PostgreSQL (four databases), Prometheus, Grafana, Loki, Grafana Alloy, cAdvisor, Node Exporter.
- Prometheus alert rules and a provisioned Grafana overview dashboard.
- GitHub Actions CI/CD: lint, test, build, and publish to GHCR.
- README, CONTRIBUTING, LICENSE (MIT), CODE_OF_CONDUCT, SECURITY.
- Target Service: register, list (filter by `enabled`, paginate), get, update, delete, enable and disable targets. Names are unique (case-insensitive).
- Target Service: SSRF protection for target URLs. Blocks loopback, link-local and cloud-metadata addresses, MiniOps's own hosts and their IPs, and URLs with credentials. `SSRF_ALLOW_PRIVATE_NETWORKS` controls private ranges.
- Target Service: internal `PATCH /api/v1/targets/{id}/status` for the Monitoring Service. The gateway blocks it from outside.
- All services: `ApiError` for errors with field details, and a standard `503` response when the database is unreachable.
- Monitoring Service: scheduler that checks every enabled target at its `check_interval`, manual checks (`POST /check/{id}`), target status (`GET /targets/{id}/status`) and history (`GET /targets/{id}/history`). Results are reported to the Target Service.
- Monitoring Service: opens a `CRITICAL` incident after `FAILURE_THRESHOLD` consecutive failures and resolves it on recovery or when the target is disabled or deleted. One incident per outage, even across restarts.
- Monitoring Service: re-checks SSRF rules before every request; never follows redirects.
- Monitoring Service: container CPU and memory per target from Prometheus (cAdvisor). Reported as `null`, never `0`, when unavailable.
- Monitoring Service: the custom metrics from §7.2 are now recorded. Health checks older than 7 days are deleted.
- Incident Service: create, list (filter by status and target), get, status changes and history. One unresolved incident per target, enforced by a unique index. Status only moves forward; repeating the current status is a no-op.
- Incident Service: notifies the Notification Service in the background. The incident is saved even when that fails, and the outcome is recorded in its history.
- Notification Service: create, list (filter unread and by incident), get, mark as read. One notification per incident event.
- Scheduled checks carry a `check-…` correlation ID through every service they call.
- Monitoring Service: `GET /targets` (all target states with their latest checks, one query) and `GET /infrastructure` (host CPU, memory, disk, uptime; per-container CPU and memory; MiniOps service scrape status; Prometheus alerts).
- Dashboard: sidebar navigation (Monitor / Resources / System), breadcrumbs, command palette (Ctrl/⌘ K), mobile menu.
- Dashboard: Documentation page with guides and an API reference rendered from each service's live OpenAPI document; Settings page (theme, animations, refresh interval, start page, desktop alerts, read-only monitoring policy); About page (version, build commit, live component status, architecture, stack, team).
- Monitoring Service: `GET /config` returns the monitoring policy in effect. Gateway: `/api/docs/<service>-service.json` serves each service's OpenAPI document.
- Frontend image records the build commit (`GIT_SHA` build arg, set by CI).
- Dashboard rebuilt: Overview, Targets, Incidents, Notifications and Infrastructure tabs; target and incident detail drawers; add/edit/delete/enable/disable targets, manual checks, acknowledge/resolve incidents, mark notifications read. TanStack Query polling with per-panel error states and a live/degraded indicator; Framer Motion transitions; light and dark themes; responsive down to phone width.

- Dashboard: **Demo Lab** page with four tabs. *Scenarios* runs eight experiments against the live stack (outage & recovery, debouncing, latency & timeouts, intermittent errors, idempotency & state machine, security guardrails, and two service-outage drills) with live steps, assertions, a request console, measurements and a correlation-ID trace. *Microservices* shows a live service map and per-service guarantees, dependencies, data, resources, endpoints, configuration, metrics and logs. *Logs* searches Loki with a volume chart and live tail. *CI/CD* shows the pipeline, image tags and registry, with live GitHub Actions runs once a repository is entered.
- Demo Lab sandbox (`demo-app`, `make demo`): standard-library Python app with per-endpoint fault injection (down, slow, flaky), replacing the nginx placeholder.
- Gateway: `/api/v1/lab/…` for the sandbox and read-only `/api/v1/logs/…` for Loki queries.

### Changed
- Dashboard visual design after Minimals: Public Sans (bundled, no external font requests), green accent, soft-shadow cards, tinted labels and summary widgets, filled navigation, dark contained buttons; matching dark theme.
- `monitoring_db`: `metric_snapshots` and `monitoring_configurations` replaced by `target_states`. `notification_db`: `notification_templates` removed, `notifications.severity` added. `incident_db`: new unique index. No migrations yet, so drop the old tables (or run `docker compose down -v`) on an existing stack.
- Outbound service calls ignore proxy environment variables, and retries can be limited per call.
- Logs: uvicorn access lines and httpx request lines are no longer emitted, because the request middleware already logs each request with its correlation ID.

### Fixed
- SSRF check took ~6 s per health check and per target registration: blocked internal names that don't resolve from the container (e.g. `frontend`, on another network) hit a DNS timeout every time. Their addresses are now cached (30 s; 5 min for names that don't resolve).
- Calls between services no longer retry when the host name doesn't resolve (container stopped): retries only added DNS timeouts, and a manual check during an Incident Service outage exceeded the gateway's 10 s limit.
- List and create endpoints work without a trailing slash. Before, `/api/v1/targets` redirected to an address without the gateway port.
- The gateway returned two `X-Correlation-ID` headers. It now returns one.
- Gateway 404 and backend-down (503) responses use the standard JSON error body.
