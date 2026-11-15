# MiniOps

**A lightweight, distributed infrastructure monitoring platform.**

Register your applications, watch their health and resource use, and manage the resulting incidents from one dashboard. MiniOps is built from four FastAPI microservices, runs entirely on localhost with Docker Compose, and is tested and published by a GitHub Actions pipeline.

> Status: **Phase 3 – Microservices.** The Target Service is implemented. The monitoring, incident and notification endpoints still return `501 Not Implemented`. See the [roadmap](#roadmap).

The full specification is in [docs/MiniCloudOps.md](docs/MiniCloudOps.md).

---

## Architecture

```
                    ┌──────────────┐
  Browser ────────► │   Frontend   │  React dashboard        :3000
                    └──────┬───────┘
                           │ /api
                    ┌──────▼───────┐
                    │  API Gateway │  nginx                  :8080
                    └──────┬───────┘
        ┌──────────────────┼──────────────────┬───────────────────┐
        ▼                  ▼                  ▼                   ▼
 ┌─────────────┐   ┌───────────────┐   ┌──────────────┐   ┌────────────────┐
 │   Target    │◄──│  Monitoring   │──►│   Incident   │──►│  Notification  │
 │   Service   │   │   Service     │   │   Service    │   │    Service     │
 └──────┬──────┘   └──────┬────────┘   └──────┬───────┘   └──────┬─────────┘
        │                 │                   │                  │
   target_db       monitoring_db         incident_db      notification_db
        └─────────────────┴──── PostgreSQL ───┴──────────────────┘

 Observability:  Prometheus ◄─ cAdvisor, Node Exporter, service /metrics
                 Grafana Alloy ─► Loki ─► Grafana  (logs + dashboards  :3001)
```

**Main workflow:** a target is registered → the Monitoring Service checks it on a schedule → results go to the Incident Service → a failure opens an incident → the Notification Service records a notification → the dashboard shows it.

| Service | Responsibility | Database | API base path |
| --- | --- | --- | --- |
| `target-service` | Register and manage monitored applications | `target_db` | `/api/v1/targets` |
| `monitoring-service` | Run health checks, query Prometheus, report results | `monitoring_db` | `/api/v1/monitoring` |
| `incident-service` | Open, track and resolve incidents | `incident_db` | `/api/v1/incidents` |
| `notification-service` | Create and track notifications | `notification_db` | `/api/v1/notifications` |

Each service owns its database and never queries another service's database. Services refer to each other's data by ID and talk over REST.

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18 + Vite, served by nginx |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 |
| Database | PostgreSQL 16 (one container, four databases) |
| Gateway | nginx |
| Metrics | Prometheus, cAdvisor, Node Exporter |
| Logs | Grafana Alloy → Loki |
| Dashboards | Grafana |
| Containers | Docker, Docker Compose |
| CI/CD | GitHub Actions → GitHub Container Registry (GHCR) |
| Testing | Pytest |

## Quick start

**Prerequisites:** Docker with Compose v2, `make`, and (for local development) Python 3.12 and Node 20.

```bash
git clone <repo-url> miniops && cd miniops
make env          # creates .env from .env.example — change the passwords
make up           # builds and starts the whole stack
make health       # waits until every service reports healthy
```

| URL | What |
| --- | --- |
| http://localhost:3000 | MiniOps dashboard |
| http://localhost:8080 | API gateway |
| http://localhost:3001 | Grafana (login from `.env`) |
| http://localhost:9090 | Prometheus |

The microservices are not published to the host. To browse a service's OpenAPI docs (`/docs`), run it locally as shown in [Development](#development).

To also start a sample app to monitor: `docker compose --profile demo up -d demo-app` (register it as `http://demo-app/`).

Stop with `make down`. `make clean` also deletes all data volumes.

Run `make help` for every command.

## Project structure

```
.
├── frontend/                   React dashboard (Vite) + nginx config
├── gateway/nginx.conf          API gateway routes
├── services/
│   ├── target-service/
│   ├── monitoring-service/
│   ├── incident-service/
│   └── notification-service/
│       ├── app/
│       │   ├── main.py           FastAPI app, /health, /health/ready, /metrics
│       │   ├── routes.py         API endpoints (contract from the spec)
│       │   ├── schemas.py        Pydantic request/response models
│       │   ├── models.py         SQLAlchemy tables
│       │   ├── db.py             Engine, sessions, readiness check
│       │   ├── config.py         Settings from environment variables
│       │   ├── logging_config.py JSON logs with correlation IDs
│       │   ├── middleware.py     Correlation-ID + request logging
│       │   ├── errors.py         Standard error responses
│       │   └── http_client.py    Service-to-service calls with retry/backoff
│       ├── tests/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── requirements-dev.txt
├── infrastructure/
│   ├── prometheus/             prometheus.yml, alert-rules.yml
│   ├── grafana/                provisioning/ + dashboards/
│   ├── loki/loki-config.yml
│   └── alloy/config.alloy
├── database/init.sh            Creates the four databases and their users
├── tests/integration/          End-to-end tests against the running stack
├── scripts/healthcheck.sh      Post-deploy health verification
├── docs/                       Specification and project documents
├── .github/                    CI/CD workflow, PR and issue templates
├── docker-compose.yml
├── Makefile
└── .env.example
```

## Development

Work on one service without Docker:

```bash
cd services/target-service
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8001     # http://localhost:8001/docs
pytest
```

Frontend with hot reload (expects the gateway on :8080):

```bash
cd frontend && npm install && npm run dev       # http://localhost:5173
```

### Conventions every service follows

- **Health:** `GET /health` (liveness) and `GET /health/ready` (database reachable).
- **Metrics:** Prometheus metrics at `GET /metrics/`.
- **Logs:** one JSON object per line with `timestamp`, `level`, `service`, `correlation_id`, `message`.
- **Correlation IDs:** the `X-Correlation-ID` header is accepted, generated when missing, returned in the response and forwarded on outbound calls.
- **Errors:** `{"error": {"code", "message", "details", "correlation_id"}}`.
- **Config:** environment variables only. No secrets in code or logs.
- **Internal endpoints:** `PATCH /api/v1/targets/{id}/status` is for the Monitoring Service only. The gateway returns 404 for it.

### Target URL safety (SSRF)

The Target Service refuses URLs the platform should never call: loopback, link-local and cloud metadata (`169.254.169.254`), MiniOps's own containers (by name or IP), and URLs with embedded credentials. Private addresses are allowed by default because apps in Docker Compose use them. Set `SSRF_ALLOW_PRIVATE_NETWORKS=false` to allow public addresses only. The rules are in [services/target-service/app/url_safety.py](services/target-service/app/url_safety.py).

See [CONTRIBUTING.md](CONTRIBUTING.md) for branching, commits and pull requests.

## Testing

```bash
make test          # unit + API tests for every service (pytest)
make lint          # ruff
make integration   # end-to-end tests; needs the stack running (make up)
```

## Observability

- **Metrics:** Grafana → *MiniOps / MiniOps Overview* dashboard. Custom metrics: `miniops_health_check_total`, `miniops_health_check_failures_total`, `miniops_http_response_time_seconds`, `miniops_active_targets`, `miniops_open_incidents`.
- **Logs:** Grafana → Explore → Loki. Follow one request across services:

  ```logql
  {compose_project="miniops"} | json | correlation_id="req-12345"
  ```

- **Alert rules:** [infrastructure/prometheus/alert-rules.yml](infrastructure/prometheus/alert-rules.yml) (demo thresholds: CPU > 80 %, memory > 85 %).

## CI/CD

[.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml) runs on every push and pull request:

1. **Validate:** ruff lint and `docker compose config`.
2. **Test:** pytest for each service and a frontend build.
3. **Build:** a Docker image for each service and for the frontend.
4. **Publish:** on push (not PRs), images go to `ghcr.io/<owner>/miniops-<service>`, tagged `latest` (default branch), the branch name, `sha-<commit>`, and the version for `v*` tags.
5. **Local run:** on the demo machine, set `GHCR_OWNER` in `.env` and run `make deploy` (pull, restart, health check).

## Team

| Role | Owns |
| --- | --- |
| Backend Engineer 1 | `target-service` |
| Backend Engineer 2 | `monitoring-service` |
| Backend Engineer 3 | `incident-service`, `notification-service` |
| DevOps & Observability Engineer | Docker, Compose, CI/CD, Prometheus, Grafana, Loki |
| Frontend Engineer | Dashboard and API integration |

## Roadmap

- [x] 1. Planning: requirements, architecture, API design
- [x] 2. Foundation: repository, FastAPI skeletons, database setup
- [ ] 3. Microservices: implement the four services
- [ ] 4. Integration: connect services and databases
- [ ] 5. Containerization: Dockerfiles and Compose (skeleton done)
- [ ] 6. Monitoring: Prometheus, exporters, Grafana (skeleton done)
- [ ] 7. Logging: Loki and Alloy (skeleton done)
- [ ] 8. CI/CD: GitHub Actions and GHCR (skeleton done)
- [ ] 9. Local run: full stack on localhost
- [ ] 10. Validation: failure tests and final documentation

## License

[MIT](LICENSE)
