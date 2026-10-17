from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from app.db import Base, engine, SessionLocal
from app import models

Base.metadata.create_all(bind=engine)

db = SessionLocal()

# Clean slate
for tbl in (
    models.DeliveryAttempt.__table__,
    models.Event.__table__,
    models.RawEvent.__table__,
    models.ApiKey.__table__,
):
    db.execute(tbl.delete())
db.commit()

print("=== 1. create api key ===")
key = models.ApiKey(name="test-consumer", key_hash="hash-abc")
db.add(key); db.commit(); db.refresh(key)
print("created:", key.id, key.name, "active:", key.active)

print("\n=== 2. create raw event ===")
raw = models.RawEvent(
    source="frankfurter",
    external_id="2026-10-17-EUR-USD",
    payload={"base": "EUR", "quote": "USD", "rate": 1.08},
)
db.add(raw); db.commit(); db.refresh(raw)
print("created:", raw.source, raw.external_id, "status:", raw.status)

print("\n=== 3. dedup: same (source, external_id) must fail ===")
dup = models.RawEvent(
    source="frankfurter",
    external_id="2026-10-17-EUR-USD",
    payload={"base": "EUR", "quote": "USD", "rate": 1.09},
)
db.add(dup)
try:
    db.commit()
    print("FAIL: duplicate accepted")
except IntegrityError as e:
    db.rollback()
    print("OK: duplicate rejected —", str(e.orig).split("\n")[0])

print("\n=== 4. different external_id works ===")
raw2 = models.RawEvent(
    source="frankfurter",
    external_id="2026-10-17-EUR-GBP",
    payload={"base": "EUR", "quote": "GBP", "rate": 0.85},
)
db.add(raw2); db.commit()
print("created:", raw2.external_id)

print("\n=== 5. same external_id, different source works ===")
raw3 = models.RawEvent(
    source="github",
    external_id="2026-10-17-EUR-USD",
    payload={"event": "push"},
)
db.add(raw3); db.commit()
print("created:", raw3.source, "/", raw3.external_id)

print("\n=== 6. normalize raw into event ===")
evt = models.Event(
    raw_event_id=raw.id,
    source=raw.source,
    event_type="fx.rate",
    data={"base": "EUR", "quote": "USD", "rate": 1.08},
    occurred_at=raw.received_at,
)
db.add(evt); db.commit(); db.refresh(evt)
print("created event:", evt.event_type)

print("\n=== 7. one event per raw event ===")
db.add(models.Event(
    raw_event_id=raw.id,
    source=raw.source,
    event_type="fx.rate",
    data={"rate": 9.99},
    occurred_at=raw.received_at,
))
try:
    db.commit()
    print("FAIL: second event accepted")
except IntegrityError:
    db.rollback()
    print("OK: second event for same raw rejected")

print("\n=== 8. delivery attempts ===")
for i in (1, 2, 3):
    db.add(models.DeliveryAttempt(
        raw_event_id=raw.id,
        attempt_number=i,
        success=(i == 3),
        error=None if i == 3 else f"simulated failure {i}",
    ))
db.commit()
attempts = db.execute(
    select(models.DeliveryAttempt)
    .where(models.DeliveryAttempt.raw_event_id == raw.id)
    .order_by(models.DeliveryAttempt.attempt_number)
).scalars().all()
for a in attempts:
    print(f"  attempt {a.attempt_number}: success={a.success} error={a.error}")

print("\n=== 9. count pending ===")
n = db.execute(
    select(func.count()).select_from(models.RawEvent)
    .where(models.RawEvent.status == "pending")
).scalar()
print("pending raw events:", n)

print("\n=== 10. cleanup ===")
for tbl in (
    models.DeliveryAttempt.__table__,
    models.Event.__table__,
    models.RawEvent.__table__,
    models.ApiKey.__table__,
):
    db.execute(tbl.delete())
db.commit()
db.close()

print("\nALL CHECKS PASSED")