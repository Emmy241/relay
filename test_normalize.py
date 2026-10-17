from app.db import Base, engine, SessionLocal
from app import models
from app.tasks import poll_frankfurter

Base.metadata.create_all(bind=engine)

# clean
db = SessionLocal()
for tbl in (models.DeliveryAttempt.__table__, models.Event.__table__, models.RawEvent.__table__):
    db.execute(tbl.delete())
db.commit()
db.close()

print("=== run poller (also enqueues normalize) ===")
summary = poll_frankfurter.delay().get(timeout=60)
print(summary)

# give the normalize tasks a moment
import time
time.sleep(2)

print("\n=== raw_events ===")
db = SessionLocal()
for r in db.query(models.RawEvent).order_by(models.RawEvent.external_id).all():
    print(f"  {r.external_id:20} status={r.status:10} attempts={r.attempts}")

print("\n=== events (normalized) ===")
for e in db.query(models.Event).order_by(models.Event.event_type).all():
    print(f"  {e.source:12} {e.event_type:10} data={e.data}")

print("\n=== delivery_attempts ===")
for a in db.query(models.DeliveryAttempt).order_by(models.DeliveryAttempt.created_at).all():
    print(f"  raw={a.raw_event_id[:8]} attempt={a.attempt_number} success={a.success}")

# assertions
raw_count = db.query(models.RawEvent).count()
evt_count = db.query(models.Event).count()
processed = db.query(models.RawEvent).filter(models.RawEvent.status == "processed").count()

assert raw_count == 2
assert evt_count == 2
assert processed == 2

print("\nNORMALIZE WORKING")
db.close()
