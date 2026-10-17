from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app import models


def ingest(
    db: Session,
    source: str,
    external_id: str,
    payload: dict,
) -> tuple[models.RawEvent, bool]:
    """
    Ingest one raw event. Idempotent on (source, external_id).

    Returns (raw_event, was_created).
      - was_created=True  -> new event, stored as status=pending
      - was_created=False -> duplicate, returns the existing row unchanged
    """
    raw = models.RawEvent(
        source=source,
        external_id=external_id,
        payload=payload,
    )
    db.add(raw)
    try:
        db.commit()
        db.refresh(raw)
        return raw, True
    except IntegrityError:
        db.rollback()
        existing = db.execute(
            select(models.RawEvent).where(
                models.RawEvent.source == source,
                models.RawEvent.external_id == external_id,
            )
        ).scalar_one()
        return existing, False