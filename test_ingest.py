from app.db import Base, engine, SessionLocal
from app import models
from app.services.ingest import ingest

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# clean slate
for tbl in (models.DeliveryAttempt.__table__, models.Event.__table__, models.RawEvent.__table__):
    db.execute(tbl.delete())
db.commit()

print("=== 1. first ingest creates ===")
raw1, created1 = ingest(
    db,
    source="frankfurter",
    external_id="2026-10-17-EUR-USD",
    payload={"base": "EUR", "quote": "USD", "rate": 1.08},
)
print(f"created={created1} id={raw1.id[:8]} status={raw1.status}")
assert created1 is True
assert raw1.status == "pending"

print("\n=== 2. same payload again is a duplicate ===")
raw2, created2 = ingest(
    db,
    source="frankfurter",
    external_id="2026-10-17-EUR-USD",
    payload={"base": "EUR", "quote": "USD", "rate": 1.08},
)
print(f"created={created2} id={raw2.id[:8]}")
assert created2 is False
assert raw2.id == raw1.id, "duplicate should return the original row"

print("\n=== 3. different external_id creates ===")
raw3, created3 = ingest(
    db,
    source="frankfurter",
    external_id="2026-10-17-EUR-GBP",
    payload={"base": "EUR", "quote": "GBP", "rate": 0.85},
)
print(f"created={created3} id={raw3.id[:8]}")
assert created3 is True
assert raw3.id != raw1.id

print("\n=== 4. same external_id, different source creates ===")
raw4, created4 = ingest(
    db,
    source="github",
    external_id="2026-10-17-EUR-USD",
    payload={"action": "push"},
)
print(f"created={created4} id={raw4.id[:8]} source={raw4.source}")
assert created4 is True
assert raw4.source == "github"
assert raw4.id != raw1.id, "different source should not collide"

print("\n=== 5. duplicate does not mutate original payload ===")
raw5, created5 = ingest(
    db,
    source="frankfurter",
    external_id="2026-10-17-EUR-USD",
    payload={"base": "EUR", "quote": "USD", "rate": 999.99},  # different data
)
print(f"created={created5}")
assert created5 is False
db.refresh(raw1)
assert raw1.payload["rate"] == 1.08, "original payload should be unchanged"
print(f"original payload preserved: rate={raw1.payload['rate']}")

print("\n=== 6. count rows ===")
from sqlalchemy import select, func
n = db.execute(select(func.count()).select_from(models.RawEvent)).scalar()
print(f"raw_events rows: {n}")
assert n == 3, f"expected 3 unique events, got {n}"

# cleanup
for tbl in (models.DeliveryAttempt.__table__, models.Event.__table__, models.RawEvent.__table__):
    db.execute(tbl.delete())
db.commit()
db.close()

print("\nALL INGEST CHECKS PASSED")