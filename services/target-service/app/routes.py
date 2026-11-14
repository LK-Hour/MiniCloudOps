"""Target Management API: /api/v1/targets (contract from docs/MiniCloudOps.md §5.1)."""
from fastapi import APIRouter, status

from app.errors import not_implemented
from app.schemas import TargetCreate, TargetRead, TargetUpdate

router = APIRouter(prefix="/api/v1/targets", tags=["targets"])


@router.post("/", response_model=TargetRead, status_code=status.HTTP_201_CREATED)
def register_target(payload: TargetCreate):
    raise not_implemented()


@router.get("/", response_model=list[TargetRead])
def list_targets():
    raise not_implemented()


@router.get("/{target_id}", response_model=TargetRead)
def get_target(target_id: str):
    raise not_implemented()


@router.put("/{target_id}", response_model=TargetRead)
def update_target(target_id: str, payload: TargetUpdate):
    raise not_implemented()


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(target_id: str):
    raise not_implemented()


@router.patch("/{target_id}/enable", response_model=TargetRead)
def enable_target(target_id: str):
    raise not_implemented()


@router.patch("/{target_id}/disable", response_model=TargetRead)
def disable_target(target_id: str):
    raise not_implemented()
