from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.deps import get_db
from app.auth import require_api_key, create_api_key
from app import models, schemas
from app.tasks import requeue_dead_letters, sweep_stuck_processing


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/keys", response_model=schemas.ApiKeyCreated)
def create_key(
    payload: schemas.ApiKeyCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new API key. Returns the raw key ONCE.
    Intentionally NOT protected by require_api_key so the first key
    can be created. In a real deployment this would be behind a
    separate admin auth path or run out-of-band.
    """
    raw, row = create_api_key(db, payload.name)
    return {
        "id": row.id,
        "name": row.name,
        "api_key": raw,           # shown once
        "created_at": row.created_at,
    }


@router.get("/keys", response_model=list[schemas.ApiKeyOut])
def list_keys(
    _key: models.ApiKey = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    rows = db.execute(select(models.ApiKey).order_by(models.ApiKey.created_at)).scalars().all()
    return rows


@router.post("/requeue-dead")
def trigger_requeue(
    _key: models.ApiKey = Depends(require_api_key),
):
    result = requeue_dead_letters.delay().get(timeout=30)
    return result


@router.post("/sweep-stuck")
def trigger_sweep(
    _key: models.ApiKey = Depends(require_api_key),
):
    result = sweep_stuck_processing.delay().get(timeout=30)
    return result
