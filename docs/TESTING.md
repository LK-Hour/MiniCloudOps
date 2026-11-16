# Testing

MiniOps is tested at three levels. Each one answers a different question.

| Level | Question it answers | Where | Runs | Count |
| --- | --- | --- | --- | --- |
| Unit and API | Does each service behave correctly on its own? | `services/*/tests/` | `make test`, CI on every push | 150 |
| Integration | Do the four services work together through the gateway? | `tests/integration/` | `make integration`, CI on every push | 14 |
| Demo Lab | Can a person see the platform detect, investigate and recover from failures? | Dashboard → Demo Lab | By hand, in the browser | 8 scenarios |

Static checks run first: `ruff` for Python style and bugs, `docker compose config` for the Compose file, and a production build of the frontend.

## 1. Unit and API tests

Each service is tested alone with pytest and FastAPI's `TestClient`. No Docker or network is needed:

- **Database:** an in-memory SQLite database replaces PostgreSQL, created fresh for each test.
- **Other services:** calls to other services and to Prometheus or Telegram go through `httpx.MockTransport`, so each test decides what the other side answers, including timeouts and errors.

```bash
make test                          # every service
cd services/monitoring-service && pytest -q     # one service
```

| Service | Tests | What they cover |
| --- | --- | --- |
| Target | 54 | Validation (names, URLs, intervals), CRUD, pagination, duplicate names, enable/disable, status updates, standard error format, **SSRF protection** (loopback, link-local, cloud metadata, MiniOps containers, credentials in URLs, every resolved address, DNS lookup caching), request metrics |
| Monitoring | 54 | Health-check results (2xx/3xx up; 5xx, timeout and DNS failure down; no redirects; SSRF rechecked before each request), **incident rules** (opens after the threshold, no duplicates, a success resets the count, recovery resolves), retries and backoff, missing hosts not retried, scheduler intervals, Target Service outage, Prometheus parsing (missing data is `null`, never `0`), target-name metric |
| Incident | 20 | Validation, one active incident per target, the state machine (OPEN → ACKNOWLEDGED → RESOLVED, no reopening), idempotent resolve, history timeline, incident saved even when the Notification Service is down |
| Notification | 22 | Validation, deduplication per incident event, read state, filters, **Telegram channel** (off by default, forwarded once, a retried call is not sent twice, HTML escaping, a Telegram failure never fails the API, the bot token never appears in logs) |

Every service also passes the same checks for the shared conventions: `/health`, correlation IDs echoed or generated, `/metrics/`, and the standard error body for unknown routes.

## 2. Integration tests

These run against the real stack (all containers, PostgreSQL, Loki) through the gateway, exactly as the dashboard calls it. Failures are injected with the sandbox app (`demo-app/lab.py`). Its endpoints can be switched to answer errors, respond slowly or fail at random.

```bash
make demo          # the stack plus the sandbox app
make integration   # GATEWAY_URL=http://localhost:8080 by default
```

| Test | Shows |
| --- | --- |
| `test_gateway_is_healthy` | The gateway is up |
| `test_every_service_answers_from_its_database` (×4) | Each service and its own database answer through the gateway |
| `test_target_lifecycle` | Register, read, update, delete a target |
| `test_invalid_target_is_rejected` | Bad input gets a 422 with one error per field |
| `test_ssrf_targets_are_blocked` (×3) | Cloud metadata, loopback and MiniOps's own database cannot be registered |
| `test_log_api_is_read_only` | The gateway's Loki proxy refuses writes |
| `test_healthy_target_is_reported_up_to_the_target_service` | Monitoring → Target status reporting |
| `test_failure_creates_incident_and_notification_then_recovers` | **The main workflow** (below) |
| `test_slow_target_is_reported_down` | A response slower than the timeout counts as a failure, without opening an incident |

The main workflow test follows the specification's §3.2, step by step:

1. Register a target that points at a sandbox endpoint, and wait for its first scheduled check (UP).
2. Make the endpoint answer `503`. Below the failure threshold, checks are DOWN but no incident opens (debounce).
3. The threshold-th failure opens exactly one `CRITICAL` incident for that target.
4. The Incident Service has the Notification Service store an `INCIDENT_CREATED` notification.
5. Another failure does not open a second incident.
6. The endpoint recovers. The next check is UP, the incident is `RESOLVED`, and an `INCIDENT_RESOLVED` notification is stored. The incident's history records each step.
7. **Logs:** Loki holds lines from the Monitoring, Incident and Notification services carrying the test's correlation ID. That proves one request can be followed across services.

Each test tags its requests with its own correlation ID (`it-…`) and deletes the targets and sandbox endpoints it creates. Incidents stay in the history because the Incident Service keeps a permanent record. If the stack or the sandbox is not running, the tests are skipped with a message saying how to start it.

## 3. Demo Lab (manual)

Dashboard → **Demo Lab → Scenarios** runs eight experiments against the live stack. Each one states its hypothesis, shows every request and ends in a pass or fail verdict with measurements (time to detect, outage duration):

| Scenario | Proves |
| --- | --- |
| Outage detection & recovery | Down → incident → notification → recovered → resolved |
| Alert debouncing | One failed check does not open an incident |
| Latency & timeouts | Slow answers count as failures |
| Intermittent errors | A flaky app is handled without duplicate incidents |
| API contract | Idempotent calls and the incident state machine |
| Security | SSRF targets, invalid input and internal routes are refused |
| Notification Service outage | Incidents are still saved and the failure is recorded (`docker compose stop notification-service`) |
| Incident Service outage | Monitoring retries without crashing, then catches up (`docker compose stop incident-service`) |

The last two need a terminal: the lab shows the command to run and waits until it sees the service stop.

## 4. Continuous integration

`.github/workflows/ci-cd.yml` runs on every push and pull request to `main` and `develop`:

```
validate ──► unit tests (4 services, in parallel) ──► integration (full stack) ──► build + publish 5 images
         └─► frontend build ──────────────────────────────────────────────────┘
```

Images are published to GHCR only when every test job passes. The integration job starts the stack with `docker compose --profile demo up --wait`, runs `tests/integration` and prints the service logs if anything fails.

## Results

On the final version (Python 3.12, Docker Compose v2):

| Suite | Result |
| --- | --- |
| Unit and API | 150 passed |
| Integration | 14 passed (about 20 s) |
| Demo Lab | 8 of 8 scenarios passed |
| Lint (`ruff check services tests`) | Clean |

## Bugs found by testing

The Demo Lab and the integration tests found two real problems that the unit tests could not. Both are fixed and now covered by unit tests:

- **Slow health checks (about 6 s each).** The SSRF check resolved MiniOps's internal host names on every check, and one of them does not exist on the internal network, so every check waited for a DNS timeout. Lookups are now cached (30 s for hits, 5 min for misses), and a check takes about 50 ms.
- **Manual checks failed while the Incident Service was stopped.** Calls to a container that no longer existed were retried, and every retry waited for another DNS timeout. The total went past the gateway's 10 s limit. A host name that does not resolve is now treated as a final failure and not retried.
