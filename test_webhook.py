import json
import hmac
import hashlib
import uuid
import time
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.db import Base, engine, SessionLocal
from app import models

Base.metadata.create_all(bind=engine)
client = TestClient(app)


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()


def clean():
    db = SessionLocal()
    for tbl in (models.DeliveryAttempt.__table__, models.Event.__table__, models.RawEvent.__table__):
        db.execute(tbl.delete())
    db.commit()
    db.close()


clean()

push_payload = {
    "ref": "refs/heads/main",
    "repository": {"full_name": "emmy241/relay"},
    "pusher": {"name": "emmy"},
    "commits": [
        {"id": "abc123", "message": "first"},
        {"id": "def456", "message": "second"},
    ],
}

print("=== 1. missing signature -> 401 ===")
r = client.post("/webhooks/github", json=push_payload)
print(r.status_code, r.json())
assert r.status_code == 401

print("\n=== 2. wrong signature -> 401 ===")
r = client.post(
    "/webhooks/github",
    content=json.dumps(push_payload).encode(),
    headers={
        "X-Hub-Signature-256": "sha256=deadbeef",
        "X-GitHub-Delivery": str(uuid.uuid4()),
        "X-GitHub-Event": "push",
        "Content-Type": "application/json",
    },
)
print(r.status_code, r.json())
assert r.status_code == 401

print("\n=== 3. valid signature, missing delivery -> 400 ===")
body = json.dumps(push_payload).encode()
r = client.post(
    "/webhooks/github",
    content=body,
    headers={
        "X-Hub-Signature-256": sign(body),
        "X-GitHub-Event": "push",
        "Content-Type": "application/json",
    },
)
print(r.status_code, r.json())
assert r.status_code == 400

print("\n=== 4. valid request -> 200, created=true ===")
delivery = str(uuid.uuid4())
body = json.dumps(push_payload).encode()
r = client.post(
    "/webhooks/github",
    content=body,
    headers={
        "X-Hub-Signature-256": sign(body),
        "X-GitHub-Delivery": delivery,
        "X-GitHub-Event": "push",
        "Content-Type": "application/json",
    },
)
print(r.status_code, r.json())
assert r.status_code == 200
assert r.json()["created"] is True
raw_id = r.json()["raw_event_id"]

print("\n=== 5. same delivery twice -> created=false ===")
r = client.post(
    "/webhooks/github",
    content=body,
    headers={
        "X-Hub-Signature-256": sign(body),
        "X-GitHub-Delivery": delivery,
        "X-GitHub-Event": "push",
        "Content-Type": "application/json",
    },
)
print(r.status_code, r.json())
assert r.status_code == 200
assert r.json()["created"] is False
assert r.json()["raw_event_id"] == raw_id

print("\n=== 6. wait for normalize, check event ===")
time.sleep(3)
db = SessionLocal()
raw = db.get(models.RawEvent, raw_id)
print(f"raw status={raw.status} attempts={raw.attempts}")

evt = db.query(models.Event).filter_by(raw_event_id=raw_id).one_or_none()
assert evt is not None, "normalized event missing"
print(f"event: {evt.event_type} data={evt.data}")
assert evt.event_type == "push"
assert evt.data["repo"] == "emmy241/relay"
assert evt.data["commits"] == 2

clean()
print("\nWEBHOOK CHECKS PASSED")
db.close()
