import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Header
from app.config import settings
from app.db import SessionLocal
from app.services.ingest import ingest
from app.tasks import process_raw_event


router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def verify_signature(body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    body = await request.body()

    if not verify_signature(body, x_hub_signature_256):
        raise HTTPException(401, "invalid signature")

    if not x_github_delivery:
        raise HTTPException(400, "missing X-GitHub-Delivery header")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON")

    db = SessionLocal()
    try:
        raw, was_created = ingest(
            db,
            source="github",
            external_id=x_github_delivery,
            payload=payload,
        )
    finally:
        db.close()

    if was_created:
        process_raw_event.delay(raw.id)

    return {
        "status": "accepted",
        "created": was_created,
        "delivery": x_github_delivery,
        "raw_event_id": raw.id,
    }
