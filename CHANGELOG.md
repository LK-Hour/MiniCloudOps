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
