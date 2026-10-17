import secrets
import hashlib
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone
from app.deps import get_db
from app import models


KEY_PREFIX = "relay_"

# This tells Swagger UI to show the "Authorize" button
bearer_scheme = HTTPBearer(auto_error=False)


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_api_key(db: Session, name: str) -> tuple[str, models.ApiKey]:
    raw = generate_api_key()
    row = models.ApiKey(name=name, key_hash=hash_key(raw))
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.ApiKey:
    if not credentials:
        raise HTTPException(401, "Missing Authorization header")

    raw = credentials.credentials
    if not raw.startswith(KEY_PREFIX):
        raise HTTPException(401, "Invalid key format")

    hashed = hash_key(raw)
    key = db.execute(
        select(models.ApiKey).where(
            models.ApiKey.key_hash == hashed,
            models.ApiKey.active == True,  # noqa: E712
        )
    ).scalar_one_or_none()

    if key is None:
        raise HTTPException(401, "Invalid or inactive key")

    key.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return key
