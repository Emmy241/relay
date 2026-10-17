import time
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app import models

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def clean():
    db = SessionLocal()
    for tbl in (models.DeliveryAttempt.__table__, models.Event.__table__, models.RawEvent.__table__, models.ApiKey.__table__):
        db.execute(tbl.delete())
    db.commit()
    db.close()


clean()

print("=== 1. no key -> 401 on /events ===")
r = client.get("/events")
print(r.status_code, r.json())
assert r.status_code == 401

print("\n=== 2. bad key -> 401 ===")
r = client.get("/events", headers={"Authorization": "Bearer relay_notarealkey"})
print(r.status_code, r.json())
assert r.status_code == 401

print("\n=== 3. create key ===")
r = client.post("/admin/keys", json={"name": "demo-consumer"})
print(r.status_code)
data = r.json()
print(f"id={data['id'][:8]} name={data['name']} key_prefix={data['api_key'][:12]}…")
assert r.status_code == 200
assert data["api_key"].startswith("relay_")
raw_key = data["api_key"]
headers = {"Authorization": f"Bearer {raw_key}"}

print("\n=== 4. key stored hashed, not raw ===")
db = SessionLocal()
row = db.query(models.ApiKey).one()
print(f"key_hash={row.key_hash[:16]}…")
assert row.key_hash != raw_key
assert len(row.key_hash) == 64     # sha256 hex
db.close()

print("\n=== 5. valid key lists keys ===")
r = client.get("/admin/keys", headers=headers)
print(r.status_code, [k["name"] for k in r.json()])
assert r.status_code == 200
assert len(r.json()) == 1
assert "api_key" not in r.json()[0]     # never expose raw key in list

print("\n=== 6. seed some events ===")
db = SessionLocal()
raw = models.RawEvent(
    source="frankfurter", external_id="2026-10-17-EUR",
    payload={"base": "EUR", "date": "2026-10-17", "rates": {"USD": 1.08}},
)
db.add(raw); db.commit(); db.refresh(raw)
db.add(models.Event(
    raw_event_id=raw.id, source="frankfurter", event_type="fx.rates",
    data={"base": "EUR", "rates": {"USD": 1.08}},
    occurred_at=raw.received_at,
))
raw2 = models.RawEvent(
    source="github", external_id="abc-123",
    payload={"ref": "refs/heads/main", "repository": {"full_name": "emmy/relay"}, "pusher": {"name": "emmy"}, "commits": [1,2]},
)
db.add(raw2); db.commit(); db.refresh(raw2)
db.add(models.Event(
    raw_event_id=raw2.id, source="github", event_type="push",
    data={"repo": "emmy/relay", "pusher": "emmy", "ref": "refs/heads/main", "commits": 2},
    occurred_at=raw2.received_at,
))
db.commit()
db.close()

print("\n=== 7. list all events ===")
r = client.get("/events", headers=headers)
print(r.status_code, [e["event_type"] for e in r.json()])
assert len(r.json()) == 2

print("\n=== 8. filter by source ===")
r = client.get("/events?source=github", headers=headers)
assert len(r.json()) == 1
print(f"github events: {len(r.json())}, first type={r.json()[0]['event_type']}")

print("\n=== 9. filter by event_type ===")
r = client.get("/events?event_type=fx.rates", headers=headers)
assert len(r.json()) == 1
print(f"fx.rates events: {len(r.json())}")

print("\n=== 10. get single event ===")
event_id = r.json()[0]["id"]
r = client.get(f"/events/{event_id}", headers=headers)
print(r.status_code, r.json()["source"], r.json()["event_type"])
assert r.status_code == 200

print("\n=== 11. 404 for missing event ===")
r = client.get("/events/00000000-0000-0000-0000-000000000000", headers=headers)
print(r.status_code)
assert r.status_code == 404

clean()
print("\nAPI CHECKS PASSED")
