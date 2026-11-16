"""Health checking: the scheduler, a single check, and the incident rules.

For each check of a target:
  1. re-validate its URL against the SSRF rules (DNS may have changed since registration);
  2. send the HTTP request and record the result in health_checks;
  3. update target_states (status, consecutive failures);
  4. report UP/DOWN to the Target Service;
  5. open an incident after `failure_threshold` consecutive failures, or resolve it on recovery.

The incident id is stored in target_states, so one outage opens exactly one incident. If the
Incident Service is down, step 5 fails after its retries and simply happens on the next check.

Assumes one Monitoring Service replica: the schedule and per-target locks live in memory.
"""
import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, func, or_, select, true
from sqlalchemy.orm import Session

from app import metrics
from app.clients import IncidentServiceClient, ServiceUnavailable, TargetServiceClient
from app.config import Settings
from app.logging_config import correlation_id_var
from app.models import HealthCheck, TargetState
from app.probe import ProbeResult, probe
from app.prometheus import ContainerUsage, PrometheusClient
from app.url_safety import (
    Resolver,
    UnresolvableHostError,
    UnsafeTargetError,
    system_resolver,
    validate_target_url,
)

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]
PRUNE_EVERY_SECONDS = 3600


@dataclass(frozen=True)
class StateSnapshot:
    target_id: str
    status: str
    consecutive_failures: int
    last_checked_at: datetime | None
    last_response_time_ms: float | None
    open_incident_id: str | None

    @classmethod
    def of(cls, state: TargetState) -> "StateSnapshot":
        return cls(
            state.target_id,
            state.status,
            state.consecutive_failures,
            state.last_checked_at,
            state.last_response_time_ms,
            state.open_incident_id,
        )

    @classmethod
    def unknown(cls, target_id: str) -> "StateSnapshot":
        return cls(target_id, "UNKNOWN", 0, None, None, None)


def host_of(url: str) -> str | None:
    return urlsplit(url).hostname


class Monitor:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: SessionFactory,
        targets: TargetServiceClient,
        incidents: IncidentServiceClient,
        prometheus: PrometheusClient,
        resolver: Resolver = system_resolver,
        transport: httpx.AsyncBaseTransport | None = None,  # tests: fake monitored apps
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.targets = targets
        self.incidents = incidents
        self.prometheus = prometheus
        self.resolver = resolver
        self.transport = transport

        self._locks: dict[str, asyncio.Lock] = {}
        self._last_started: dict[str, float] = {}  # target id -> time.monotonic() of last scheduled check
        self._in_flight: set[str] = set()
        self._tasks: set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_checks)
        self._last_prune = 0.0

    # --- one check ------------------------------------------------------------------------------

    async def check_target(self, target: dict) -> HealthCheck:
        """Check one target now and apply the incident rules. Returns the stored check."""
        target_id = target["id"]
        lock = self._locks.setdefault(target_id, asyncio.Lock())
        async with lock:
            result = await self._probe_safely(target)
            check, state = self._record(target_id, result)
            self._observe(target_id, result)
            metrics.set_target_name(target_id, target.get("name") or target_id)
            await self.targets.report_status(target_id, result.status)
            await self._apply_incident_rules(target, state, check)
            return check

    async def _probe_safely(self, target: dict) -> ProbeResult:
        url = target["target_url"]
        try:
            await asyncio.to_thread(
                validate_target_url,
                url,
                blocked_hosts=self.settings.ssrf_blocked_host_list,
                allow_private=self.settings.ssrf_allow_private_networks,
                resolver=self.resolver,
            )
        except UnresolvableHostError:
            # A stopped Docker container's name stops resolving: an outage, not an attack.
            return ProbeResult("DOWN", error=f"DNS lookup failed for '{host_of(url)}'")
        except UnsafeTargetError as exc:
            logger.warning(
                "Check blocked by SSRF protection", extra={"target_id": target["id"], "reason": str(exc)}
            )
            return ProbeResult("DOWN", error=f"Blocked: {exc}")
        return await probe(url, timeout=self.settings.check_timeout_seconds, transport=self.transport)

    def _record(self, target_id: str, result: ProbeResult) -> tuple[HealthCheck, StateSnapshot]:
        now = datetime.now(UTC)
        with self.session_factory() as db:
            check = HealthCheck(
                target_id=target_id,
                status=result.status,
                status_code=result.status_code,
                response_time_ms=result.response_time_ms,
                error=result.error[:500] if result.error else None,
                checked_at=now,
            )
            db.add(check)
            state = db.get(TargetState, target_id)
            if state is None:
                state = TargetState(target_id=target_id, consecutive_failures=0)
                db.add(state)
            state.status = result.status
            state.consecutive_failures = 0 if result.status == "UP" else state.consecutive_failures + 1
            state.last_checked_at = now
            state.last_response_time_ms = result.response_time_ms
            db.commit()
            return check, StateSnapshot.of(state)

    def _observe(self, target_id: str, result: ProbeResult) -> None:
        metrics.HEALTH_CHECKS.labels(target_id).inc()
        if result.status == "DOWN":
            metrics.HEALTH_CHECK_FAILURES.labels(target_id).inc()
        if result.response_time_ms is not None:
            metrics.RESPONSE_TIME.labels(target_id).observe(result.response_time_ms / 1000)

        extra = {
            "target_id": target_id,
            "status": result.status,
            "status_code": result.status_code,
            "response_time_ms": result.response_time_ms,
        }
        if result.status == "DOWN":
            logger.warning("Health check failed", extra={**extra, "error": result.error})
        elif (result.response_time_ms or 0) > (threshold := self.settings.response_time_threshold_ms):
            logger.warning("Slow response", extra={**extra, "threshold_ms": threshold})
        else:
            logger.info("Health check passed", extra=extra)

    # --- incidents --------------------------------------------------------------------------------

    async def _apply_incident_rules(self, target: dict, state: StateSnapshot, check: HealthCheck) -> None:
        threshold = self.settings.failure_threshold
        if check.status == "DOWN" and state.consecutive_failures >= threshold and not state.open_incident_id:
            try:
                incident_id = await self.incidents.open_incident(
                    target_id=target["id"],
                    title=f"{target.get('name') or target['id']} is unavailable"[:200],
                    severity="CRITICAL",
                    description=(
                        f"HTTP health check of {target['target_url']} failed {state.consecutive_failures} "
                        f"times in a row. Last error: {check.error}"
                    ),
                )
            except ServiceUnavailable as exc:
                logger.error(
                    "Could not open incident; will retry on the next check",
                    extra={"target_id": target["id"], "error": str(exc)},
                )
                return
            self._set_incident(target["id"], incident_id)
            logger.error("Incident opened", extra={"target_id": target["id"], "incident_id": incident_id})

        elif check.status == "UP" and state.open_incident_id:
            note = "Target recovered: health check passed"
            if await self._resolve(state.open_incident_id, target["id"], note):
                self._set_incident(target["id"], None)

    async def _resolve(self, incident_id: str, target_id: str, note: str) -> bool:
        try:
            await self.incidents.resolve_incident(incident_id, note)
        except ServiceUnavailable as exc:
            logger.error(
                "Could not resolve incident; will retry",
                extra={"target_id": target_id, "incident_id": incident_id, "error": str(exc)},
            )
            return False
        logger.info("Incident resolved", extra={"target_id": target_id, "incident_id": incident_id})
        return True

    def _set_incident(self, target_id: str, incident_id: str | None) -> None:
        with self.session_factory() as db:
            state = db.get(TargetState, target_id)
            if state is not None:
                state.open_incident_id = incident_id
                db.commit()
        self._refresh_open_incidents_gauge()

    def _refresh_open_incidents_gauge(self) -> None:
        with self.session_factory() as db:
            open_count = db.scalar(
                select(func.count()).select_from(TargetState).where(TargetState.open_incident_id.is_not(None))
            )
        metrics.OPEN_INCIDENTS.set(open_count or 0)

    # --- reads used by the API --------------------------------------------------------------------

    def get_state(self, target_id: str) -> StateSnapshot | None:
        with self.session_factory() as db:
            state = db.get(TargetState, target_id)
            return StateSnapshot.of(state) if state else None

    def history(self, target_id: str, limit: int) -> list[HealthCheck]:
        with self.session_factory() as db:
            query = (
                select(HealthCheck)
                .where(HealthCheck.target_id == target_id)
                .order_by(HealthCheck.checked_at.desc())
                .limit(limit)
            )
            return list(db.scalars(query))

    def overview(self, recent: int) -> list[tuple[StateSnapshot, list[HealthCheck]]]:
        """Every known target state with its `recent` latest checks (oldest first), in two queries."""
        with self.session_factory() as db:
            states = [StateSnapshot.of(s) for s in db.scalars(select(TargetState))]
            rank = (
                func.row_number()
                .over(partition_by=HealthCheck.target_id, order_by=HealthCheck.checked_at.desc())
                .label("rank")
            )
            ranked = select(HealthCheck.id, rank).subquery()
            checks = db.scalars(
                select(HealthCheck)
                .join(ranked, ranked.c.id == HealthCheck.id)
                .where(ranked.c.rank <= recent)
                .order_by(HealthCheck.checked_at)
            ).all()
        by_target: dict[str, list[HealthCheck]] = {}
        for check in checks:
            by_target.setdefault(check.target_id, []).append(check)
        return [(state, by_target.get(state.target_id, [])) for state in states]

    async def container_usage(self, target: dict) -> ContainerUsage:
        return await self.prometheus.container_usage(host_of(target["target_url"]))

    # --- scheduler --------------------------------------------------------------------------------

    async def run_forever(self, stop: asyncio.Event) -> None:
        logger.info("Scheduler started", extra={"tick_seconds": self.settings.scheduler_tick_seconds})
        while not stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception("Scheduler tick failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.settings.scheduler_tick_seconds)
            except TimeoutError:
                pass
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("Scheduler stopped")

    async def tick(self) -> None:
        """Start a check for every enabled target that is due. Checks run in the background."""
        correlation_id_var.set(f"sched-{uuid.uuid4().hex[:12]}")
        try:
            targets = await self.targets.list_enabled()
        except ServiceUnavailable as exc:
            # Nothing is reset while the Target Service is away: we just don't know the targets.
            logger.warning("Target Service unavailable; skipping this round", extra={"error": str(exc)})
            return
        metrics.ACTIVE_TARGETS.set(len(targets))
        metrics.keep_target_names({t["id"] for t in targets})

        now = time.monotonic()
        for target in targets:
            interval = target.get("check_interval") or self.settings.default_check_interval_seconds
            last = self._last_started.get(target["id"])
            if target["id"] in self._in_flight or (last is not None and now - last < interval):
                continue
            self._last_started[target["id"]] = now
            task = asyncio.create_task(self._scheduled_check(target))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        await self._release_inactive({t["id"] for t in targets})
        self._refresh_open_incidents_gauge()
        self._prune_history(now)

    async def wait_for_checks(self) -> None:
        """Wait until every running check has finished (used by tests)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _scheduled_check(self, target: dict) -> None:
        correlation_id_var.set(f"check-{uuid.uuid4().hex[:12]}")  # follows the check across services
        self._in_flight.add(target["id"])
        try:
            async with self._semaphore:
                await self.check_target(target)
        except Exception:
            logger.exception("Health check crashed", extra={"target_id": target["id"]})
        finally:
            self._in_flight.discard(target["id"])

    async def _release_inactive(self, active_ids: set[str]) -> None:
        """Targets that were disabled or deleted: resolve their incident and forget their state."""
        with self.session_factory() as db:
            stale = db.scalars(
                select(TargetState).where(
                    TargetState.target_id.not_in(active_ids) if active_ids else true(),
                    or_(TargetState.status != "UNKNOWN", TargetState.open_incident_id.is_not(None)),
                )
            ).all()
            stale = [StateSnapshot.of(s) for s in stale]

        for state in stale:
            if state.open_incident_id and not await self._resolve(
                state.open_incident_id, state.target_id, "Monitoring stopped: target disabled or deleted"
            ):
                continue  # keep the incident id and try again next round
            with self.session_factory() as db:
                row = db.get(TargetState, state.target_id)
                if row is not None:
                    row.status, row.consecutive_failures, row.open_incident_id = "UNKNOWN", 0, None
                    db.commit()
            self._last_started.pop(state.target_id, None)
            self._locks.pop(state.target_id, None)
            logger.info("Stopped monitoring target", extra={"target_id": state.target_id})

    def _prune_history(self, now: float) -> None:
        if self._last_prune and now - self._last_prune < PRUNE_EVERY_SECONDS:
            return
        self._last_prune = now
        cutoff = datetime.now(UTC) - timedelta(days=self.settings.history_retention_days)
        with self.session_factory() as db:
            deleted = db.execute(delete(HealthCheck).where(HealthCheck.checked_at < cutoff)).rowcount
            db.commit()
        if deleted:
            logger.info("Pruned old health checks", extra={"deleted": deleted})
