"""Request/response models for the Target Management API."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

TargetType = Literal["http", "docker"]


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # TODO(security): reject loopback, link-local, metadata (169.254.169.254) and other
    # internal addresses before saving, to prevent SSRF through monitoring targets.
    target_url: HttpUrl
    type: TargetType = "http"
    check_interval: int = Field(default=30, ge=10, le=3600)
    enabled: bool = True


class TargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_url: HttpUrl | None = None
    type: TargetType | None = None
    check_interval: int | None = Field(default=None, ge=10, le=3600)
    enabled: bool | None = None


class TargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    target_url: str
    type: TargetType
    check_interval: int
    enabled: bool
    status: str
    created_at: datetime
    updated_at: datetime
