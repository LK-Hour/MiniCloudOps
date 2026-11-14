# Contributing to MiniOps

Thanks for helping build MiniOps. This guide covers how we work as a team: setup, branches, commits, pull requests, and the rules every service follows.

## 1. Setup

```bash
git clone <repo-url> miniops && cd miniops
make env      # creates .env from .env.example, then change the passwords
make up       # build and start everything
make health
```

You need Docker with Compose v2, `make`, Python 3.12 and Node 20. See the [README](README.md#development) to run a single service or the frontend without Docker.

## 2. Branches

- `main` is always deployable. It is protected: no direct pushes, and CI must pass before merging.
- `develop` is the integration branch. Feature branches merge here first.
- Create your branch from `develop`:

| Type | Name |
| --- | --- |
| Feature | `feature/<service>-<short-description>` e.g. `feature/target-ssrf-validation` |
| Bug fix | `fix/<service>-<short-description>` |
| Infra / CI | `chore/<short-description>` |
| Docs | `docs/<short-description>` |

Keep branches short-lived. Rebase on `develop` (or merge it in) before opening a PR.

## 3. Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org/). The scope is the service or area:

```
feat(target): validate target URLs against internal addresses
fix(monitoring): retry incident submission with backoff
chore(ci): cache pip dependencies
docs(readme): add Loki query examples
test(incident): cover duplicate-incident prevention
```

Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`, `ci`, `perf`.
Scopes: `target`, `monitoring`, `incident`, `notification`, `frontend`, `gateway`, `infra`, `ci`, `docs`.

## 4. Pull requests

1. Open the PR against `develop` and fill in the template.
2. Keep it focused: one feature or fix per PR. Smaller PRs get reviewed faster.
3. CI must be green: lint, tests, frontend build and image build.
4. You need **at least one approval**. Changes that touch another person's service need that service owner's approval.
5. Squash-merge, using a Conventional Commit title.

Merging `develop` into `main` is done together before demos and milestones, so that the images published to GHCR are stable.

## 5. Code standards

### Python services

- Python 3.12, FastAPI, SQLAlchemy 2.
- Lint with `make lint` (ruff, configured in [ruff.toml](ruff.toml)).
- Put endpoints in `app/routes.py`, request and response models in `app/schemas.py`, and tables in `app/models.py`.
- Validate every input with Pydantic models. Do not accept raw dicts.
- Raise `HTTPException`. The handlers in `app/errors.py` turn it into the standard error body.
- Call other services only through `app/http_client.request_with_retry`, which adds timeouts, retries, backoff and the correlation ID.

### Service boundaries (required)

- A service reads and writes **only its own database**.
- Refer to other services' data by ID only (`target_id`, `incident_id`). Fetch details from the owning service's API.
- A failing dependency must not crash the caller. For example, if the Notification Service is down, the incident is still saved.
- Missing metrics are reported as unavailable (`null`), **never as `0`**.

### Logging

- Use `logging.getLogger(__name__)`. Output is already JSON.
- Add context with `extra={...}`, for example `logger.info("Incident created", extra={"incident_id": id})`.
- **Never log** passwords, tokens, connection strings or full request bodies that may contain them.

### Frontend

- Go through `src/api.js`. It calls the gateway at `/api/v1/...` and sends a correlation ID.
- Every panel needs loading, empty and error states.

## 6. Tests

- Every new endpoint needs tests in that service's `tests/` folder.
- Unit tests must not need a running database or other services. Mock outbound HTTP calls.
- Cross-service flows go in `tests/integration/` and run against the live stack with `make integration`.
- Run `make test` before pushing.

## 7. Configuration and secrets

- Configuration comes from environment variables only.
- When you add a variable, add it to `.env.example` with a safe placeholder, to the service's `app/config.py`, and to `docker-compose.yml`.
- **Never commit `.env`** or any real credential. If you commit one by accident, tell the team and rotate it straight away. Deleting the commit is not enough.

## 8. Adding a new service

1. Copy an existing service folder and rename it.
2. Update `config.py`, the `SERVICE_NAME` and `pyproject.toml`.
3. Add its database and user to `database/init.sh` and `.env.example`.
4. Add it to `docker-compose.yml`, `gateway/nginx.conf` if it is public, `infrastructure/prometheus/prometheus.yml`, the CI matrices in `.github/workflows/ci-cd.yml`, and the `SERVICES` list in the `Makefile`.

## 9. Reporting issues

Use the GitHub issue templates. For bugs, include the correlation ID and the related Loki logs, with any secrets removed. For security problems, see [SECURITY.md](SECURITY.md).

By contributing, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md) and that your contributions are licensed under the [MIT License](LICENSE).
