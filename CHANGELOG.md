# Changelog

All notable changes to this project are recorded here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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

### Fixed
- List and create endpoints work without a trailing slash. Before, `/api/v1/targets` redirected to an address without the gateway port.
- The gateway returned two `X-Correlation-ID` headers. It now returns one.
- Gateway 404 and backend-down (503) responses use the standard JSON error body.
