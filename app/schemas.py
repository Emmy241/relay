from datetime import datetime
from typing import Any
from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyCreated(BaseModel):
    id: str
    name: str
    api_key: str         # shown once
    created_at: datetime


class ApiKeyOut(BaseModel):
    id: str
    name: str
    active: bool
    created_at: datetime
    last_used_at: datetime | None
    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: str
    source: str
    event_type: str
    data: dict[str, Any]
    occurred_at: datetime
    created_at: datetime
    class Config:
        from_attributes = True
