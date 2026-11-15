"""Incident Management API: /api/v1/incidents (contract from docs/MiniCloudOps.md §5.3).

Rules to implement:
  - Do not open a duplicate incident while one is already OPEN for the same target.
  - Save the incident first, then call the Notification Service; if that call fails,
    the incident must still be stored (log the failure, don't roll back).
"""
from fastapi import APIRouter, status

from app.errors import not_implemented
from app.schemas import IncidentCreate, IncidentEventRead, IncidentRead, IncidentStatusUpdate

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentRead])
def list_incidents(status_filter: str | None = None):
    raise not_implemented()


@router.get("/{incident_id}", response_model=IncidentRead)
def get_incident(incident_id: str):
    raise not_implemented()


@router.post("", response_model=IncidentRead, status_code=status.HTTP_201_CREATED)
async def create_incident(payload: IncidentCreate):
    raise not_implemented()


@router.patch("/{incident_id}/status", response_model=IncidentRead)
async def update_incident_status(incident_id: str, payload: IncidentStatusUpdate):
    raise not_implemented()


@router.get("/{incident_id}/history", response_model=list[IncidentEventRead])
def incident_history(incident_id: str):
    raise not_implemented()
