from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.deps import get_db
from app.auth import require_api_key
from app import models, schemas


router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[schemas.EventOut])
def list_events(
    source: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    _key: models.ApiKey = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    q = select(models.Event)
    if source:
        q = q.where(models.Event.source == source)
    if event_type:
        q = q.where(models.Event.event_type == event_type)
    if since:
        q = q.where(models.Event.created_at >= since)

    q = q.order_by(models.Event.created_at.desc()).limit(limit)
    return db.execute(q).scalars().all()


@router.get("/{event_id}", response_model=schemas.EventOut)
def get_event(
    event_id: str,
    _key: models.ApiKey = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    evt = db.get(models.Event, event_id)
    if evt is None:
        raise HTTPException(404, "Event not found")
    return evt
