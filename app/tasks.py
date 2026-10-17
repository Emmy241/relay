from datetime import datetime, timezone
from sqlalchemy import select
from app.celery_app import celery_app
from app.db import SessionLocal
from app import models
from app.services.ingest import ingest
from app.services.frankfurter import fetch_latest
from app.services.normalize import normalize


BASES = ["EUR", "USD"]
SYMBOLS = ["USD", "GBP", "JPY"]
MAX_ATTEMPTS = 3


@celery_app.task(name="relay.ping")
def ping(x: int, y: int) -> int:
    return x + y


@celery_app.task(name="relay.poll_frankfurter")
def poll_frankfurter() -> dict:
    db = SessionLocal()
    created = 0
    duplicates = 0
    errors: list[str] = []

    try:
        for base in BASES:
            symbols = [s for s in SYMBOLS if s != base]
            if not symbols:
                continue
            try:
                data = fetch_latest(base, symbols)
            except Exception as e:
                errors.append(f"{base}: {e}")
                continue

            external_id = f"{base}-{data['date']}"
            raw, was_created = ingest(
                db,
                source="frankfurter",
                external_id=external_id,
                payload=data,
            )
            if was_created:
                created += 1
                process_raw_event.delay(raw.id)
            else:
                duplicates += 1

        return {
            "created": created,
            "duplicates": duplicates,
            "errors": errors,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        db.close()


@celery_app.task(name="relay.process_raw_event", bind=True, max_retries=2)
def process_raw_event(self, raw_event_id: str) -> dict:
    db = SessionLocal()
    try:
        raw = db.get(models.RawEvent, raw_event_id)
        if raw is None:
            return {"status": "missing", "id": raw_event_id}
        if raw.status == "processed":
            return {"status": "already_processed", "id": raw_event_id}

        raw.status = "processing"
        raw.attempts += 1
        db.commit()

        try:
            normalized = normalize(raw)

            existing = db.execute(
                select(models.Event).where(models.Event.raw_event_id == raw.id)
            ).scalar_one_or_none()

            if existing is None:
                db.add(models.Event(
                    raw_event_id=raw.id,
                    source=normalized["source"],
                    event_type=normalized["event_type"],
                    data=normalized["data"],
                    occurred_at=normalized["occurred_at"],
                ))

            raw.status = "processed"
            raw.processed_at = datetime.now(timezone.utc)
            raw.last_error = None

            db.add(models.DeliveryAttempt(
                raw_event_id=raw.id,
                attempt_number=raw.attempts,
                success=True,
            ))
            db.commit()
            return {"status": "processed", "id": raw.id, "attempts": raw.attempts}

        except Exception as e:
            db.rollback()
            raw = db.get(models.RawEvent, raw_event_id)
            raw.last_error = str(e)
            db.add(models.DeliveryAttempt(
                raw_event_id=raw.id,
                attempt_number=raw.attempts,
                success=False,
                error=str(e),
            ))
            db.commit()

            if raw.attempts >= MAX_ATTEMPTS:
                raw.status = "dead"
                db.commit()
                return {"status": "dead", "id": raw.id, "error": str(e)}

            raw.status = "failed"
            db.commit()
            raise self.retry(exc=e, countdown=2 ** raw.attempts)
    finally:
        db.close()


from datetime import timedelta

STUCK_PROCESSING_MINUTES = 5


@celery_app.task(name="relay.requeue_dead_letters")
def requeue_dead_letters() -> dict:
    """
    Reset every dead-lettered raw event back to pending and re-enqueue it.
    Intended for use after fixing a bug in a normalizer.
    """
    db = SessionLocal()
    try:
        dead = db.execute(
            select(models.RawEvent).where(models.RawEvent.status == "dead")
        ).scalars().all()

        requeued = []
        for raw in dead:
            raw.status = "pending"
            raw.attempts = 0
            raw.last_error = None
            db.commit()
            process_raw_event.delay(raw.id)
            requeued.append(raw.id)

        return {"requeued": len(requeued), "ids": requeued}
    finally:
        db.close()


@celery_app.task(name="relay.sweep_stuck_processing")
def sweep_stuck_processing() -> dict:
    """
    Find raw events stuck in 'processing' for longer than the threshold
    (e.g. a worker died mid-task) and reset them to pending.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_PROCESSING_MINUTES)
        stuck = db.execute(
            select(models.RawEvent).where(
                models.RawEvent.status == "processing",
                models.RawEvent.received_at < cutoff,
            )
        ).scalars().all()

        for raw in stuck:
            raw.status = "pending"
            db.commit()
            process_raw_event.delay(raw.id)

        return {"reset": len(stuck)}
    finally:
        db.close()
