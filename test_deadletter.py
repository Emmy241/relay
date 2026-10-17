import time
from datetime import datetime, timezone, timedelta
from app.db import Base, engine, SessionLocal
from app import models
from app.services.ingest import ingest
from app.tasks import (
    process_raw_event,
    requeue_dead_letters,
    sweep_stuck_processing,
)

Base.metadata.create_all(bind=engine)

def clean():
    db = SessionLocal()
    for tbl in (models.DeliveryAttempt.__table__, models.Event.__table__, models.RawEvent.__table__):
        db.execute(tbl.delete())
    db.commit()
    db.close()

clean()

# ---------------------------------------------------------------
# Part 1: a raw event with a broken source goes dead after retries
# ---------------------------------------------------------------
print("=== 1. ingest an event with no normalizer ===")
db = SessionLocal()
raw, _ = ingest(
    db,
    source="unknown-source",
    external_id="test-dead-1",
    payload={"whatever": True},
)
raw_id = raw.id
db.close()
print(f"raw id: {raw_id[:8]}")

print("\n=== 2. process it — should fail 3 times then go dead ===")
try:
    process_raw_event.delay(raw_id).get(timeout=30)
except Exception as e:
    print(f"task raised (expected): {type(e).__name__}")

# wait for retries to finish
time.sleep(8)

db = SessionLocal()
raw = db.get(models.RawEvent, raw_id)
print(f"status={raw.status} attempts={raw.attempts} last_error={raw.last_error}")
assert raw.status == "dead", f"expected dead, got {raw.status}"
assert raw.attempts >= 3

attempts = db.query(models.DeliveryAttempt).filter_by(raw_event_id=raw_id).all()
print(f"delivery_attempts recorded: {len(attempts)}")
for a in attempts:
    print(f"  attempt {a.attempt_number} success={a.success} error={a.error[:50] if a.error else None}")
assert len(attempts) >= 3
assert all(not a.success for a in attempts)
db.close()

# ---------------------------------------------------------------
# Part 2: requeue — should still go dead (source is still broken)
# ---------------------------------------------------------------
print("\n=== 3. requeue dead letters ===")
result = requeue_dead_letters.delay().get(timeout=10)
print(f"requeued: {result['requeued']}")
assert result["requeued"] >= 1

time.sleep(8)

db = SessionLocal()
raw = db.get(models.RawEvent, raw_id)
print(f"after requeue: status={raw.status} attempts={raw.attempts}")
# goes dead again, because the source is still unknown
assert raw.status == "dead"
db.close()

# ---------------------------------------------------------------
# Part 3: sweep stuck processing
# ---------------------------------------------------------------
print("\n=== 4. simulate a stuck 'processing' event ===")
db = SessionLocal()
raw, _ = ingest(
    db,
    source="frankfurter",
    external_id="test-stuck-1",
    payload={"base": "EUR", "date": "2026-10-17", "rates": {"USD": 1.08}},
)
stuck_id = raw.id
raw.status = "processing"
raw.received_at = datetime.now(timezone.utc) - timedelta(minutes=10)
db.commit()
db.close()
print(f"stuck id: {stuck_id[:8]} status=processing received_at=10min ago")

print("\n=== 5. sweep should reset it to pending and re-enqueue ===")
result = sweep_stuck_processing.delay().get(timeout=10)
print(f"swept: {result['reset']}")
assert result["reset"] == 1

time.sleep(3)

db = SessionLocal()
raw = db.get(models.RawEvent, stuck_id)
print(f"after sweep: status={raw.status} attempts={raw.attempts}")
assert raw.status in ("processed", "processing"), f"expected processed/processing, got {raw.status}"

evt = db.query(models.Event).filter_by(raw_event_id=stuck_id).one_or_none()
assert evt is not None, "event should have been normalized"
print(f"normalized event created: {evt.event_type}")
db.close()

clean()
print("\nDEAD-LETTER CHECKS PASSED")
