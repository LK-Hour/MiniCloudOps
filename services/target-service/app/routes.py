"""Target Management API: /api/v1/targets (contract from docs/MiniCloudOps.md §5.1)."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import Target
from app.schemas import TargetCreate, TargetRead, TargetStatusUpdate, TargetUpdate
from app.url_safety import Resolver, UnsafeTargetError, system_resolver, validate_target_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/targets", tags=["targets"])


def get_resolver() -> Resolver:
    """DNS resolver used for SSRF checks. Tests override this dependency."""
    return system_resolver


DbSession = Annotated[Session, Depends(get_db)]
HostResolver = Annotated[Resolver, Depends(get_resolver)]


def _get_or_404(db: Session, target_id: str) -> Target:
    target = db.get(Target, target_id)
    if target is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, f"Target '{target_id}' not found")
    return target


def _ensure_safe_url(url: str, resolver: Resolver) -> None:
    settings = get_settings()
    try:
        validate_target_url(
            url,
            blocked_hosts=settings.ssrf_blocked_host_list,
            allow_private=settings.ssrf_allow_private_networks,
            resolver=resolver,
        )
    except UnsafeTargetError as exc:
        logger.warning("Rejected unsafe target URL", extra={"reason": str(exc)})
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Target URL is not allowed",
            [{"field": "body.target_url", "message": str(exc)}],
        ) from exc


def _ensure_unique_name(db: Session, name: str, exclude_id: str | None = None) -> None:
    query = select(Target.id).where(func.lower(Target.name) == name.lower())
    if exclude_id:
        query = query.where(Target.id != exclude_id)
    if db.scalar(query) is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            f"A target named '{name}' already exists",
            [{"field": "body.name", "message": "Name must be unique"}],
        )


@router.post("", response_model=TargetRead, status_code=status.HTTP_201_CREATED)
def register_target(payload: TargetCreate, db: DbSession, resolver: HostResolver, response: Response):
    url = str(payload.target_url)
    _ensure_safe_url(url, resolver)
    _ensure_unique_name(db, payload.name)

    target = Target(**payload.model_dump(exclude={"target_url"}), target_url=url, status="UNKNOWN")
    db.add(target)
    db.commit()
    db.refresh(target)
    response.headers["Location"] = f"{router.prefix}/{target.id}"
    logger.info("Target registered", extra={"target_id": target.id, "target_name": target.name})
    return target


@router.get("", response_model=list[TargetRead])
def list_targets(
    db: DbSession,
    enabled: Annotated[bool | None, Query(description="Filter by enabled state")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = select(Target).order_by(Target.created_at, Target.id).limit(limit).offset(offset)
    if enabled is not None:
        query = query.where(Target.enabled == enabled)
    return db.scalars(query).all()


@router.get("/{target_id}", response_model=TargetRead)
def get_target(target_id: str, db: DbSession):
    return _get_or_404(db, target_id)


@router.put("/{target_id}", response_model=TargetRead)
def update_target(target_id: str, payload: TargetUpdate, db: DbSession, resolver: HostResolver):
    target = _get_or_404(db, target_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)

    if "target_url" in changes:
        changes["target_url"] = str(changes["target_url"])
        _ensure_safe_url(changes["target_url"], resolver)
        if changes["target_url"] != target.target_url:
            target.status = "UNKNOWN"  # the old result says nothing about the new URL
    if "name" in changes:
        _ensure_unique_name(db, changes["name"], exclude_id=target.id)
    if changes.get("enabled") is False:
        target.status = "UNKNOWN"

    for field, value in changes.items():
        setattr(target, field, value)
    db.commit()
    db.refresh(target)
    logger.info("Target updated", extra={"target_id": target.id, "fields": sorted(changes)})
    return target


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(target_id: str, db: DbSession):
    target = _get_or_404(db, target_id)
    db.delete(target)
    db.commit()
    logger.info("Target deleted", extra={"target_id": target_id})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _set_enabled(db: Session, target_id: str, enabled: bool) -> Target:
    target = _get_or_404(db, target_id)
    if target.enabled != enabled:
        target.enabled = enabled
        if not enabled:
            target.status = "UNKNOWN"  # no checks run while disabled, so the last result goes stale
        db.commit()
        db.refresh(target)
        logger.info("Target enabled" if enabled else "Target disabled", extra={"target_id": target_id})
    return target


@router.patch("/{target_id}/enable", response_model=TargetRead)
def enable_target(target_id: str, db: DbSession):
    return _set_enabled(db, target_id, True)


@router.patch("/{target_id}/disable", response_model=TargetRead)
def disable_target(target_id: str, db: DbSession):
    return _set_enabled(db, target_id, False)


@router.patch(
    "/{target_id}/status",
    response_model=TargetRead,
    summary="Record the latest health status (internal)",
    description="Called by the Monitoring Service after each check. The gateway blocks it from outside.",
)
def update_target_status(target_id: str, payload: TargetStatusUpdate, db: DbSession):
    target = _get_or_404(db, target_id)
    if target.status != payload.status:
        logger.info(
            "Target status changed",
            extra={"target_id": target_id, "old_status": target.status, "new_status": payload.status},
        )
        target.status = payload.status
        db.commit()
        db.refresh(target)
    return target
