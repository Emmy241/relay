import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Integer,
    Boolean, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db import Base


def _uuid():
    return str(uuid.uuid4())


class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    key_hash = Column(String, nullable=False, unique=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)


class RawEvent(Base):
    __tablename__ = "raw_events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    source = Column(String, nullable=False)               # "github" | "frankfurter"
    external_id = Column(String, nullable=False)          # dedup key from source
    payload = Column(JSONB, nullable=False)
    status = Column(String, nullable=False, default="pending")
    # status: pending | processing | processed | failed | dead
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    received_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_source_external_id"),
        Index("ix_raw_events_status_received", "status", "received_at"),
    )


class Event(Base):
    __tablename__ = "events"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    raw_event_id = Column(
        UUID(as_uuid=False),
        ForeignKey("raw_events.id"),
        nullable=False,
        unique=True,
    )
    source = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    data = Column(JSONB, nullable=False)
    occurred_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    raw_event_id = Column(
        UUID(as_uuid=False),
        ForeignKey("raw_events.id"),
        nullable=False,
        index=True,
    )
    attempt_number = Column(Integer, nullable=False)
    success = Column(Boolean, nullable=False)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)