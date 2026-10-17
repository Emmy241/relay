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

print("=== run poller via Celery (queued) ===")
result = poll_frankfurter.delay()
summary = result.get(timeout=30)
print(summary)

print("\n=== rows in raw_events ===")
db = SessionLocal()
rows = db.query(models.RawEvent).all()
for r in rows:
    print(f"  {r.source} | {r.external_id} | status={r.status} | rate_data={r.payload.get('rates')}")

print(f"\ntotal: {len(rows)}")
assert len(rows) == 2, f"expected 2 events (EUR, USD), got {len(rows)}"

print("\n=== run poller again — should be all duplicates ===")
result2 = poll_frankfurter.delay()
summary2 = result2.get(timeout=30)
print(summary2)
assert summary2["created"] == 0
assert summary2["duplicates"] == 2

print("\nPOLLER WORKING")
db.close()
