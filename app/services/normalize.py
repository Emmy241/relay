from datetime import datetime, timezone
from app import models


def normalize_frankfurter(raw: models.RawEvent) -> dict:
    payload = raw.payload
    occurred_at = datetime.fromisoformat(payload["date"]).replace(tzinfo=timezone.utc)
    return {
        "source": "frankfurter",
        "event_type": "fx.rates",
        "data": {
            "base": payload["base"],
            "rates": {k: float(v) for k, v in payload["rates"].items()},
        },
        "occurred_at": occurred_at,
    }


def normalize_github(raw: models.RawEvent) -> dict:
    payload = raw.payload
    occurred_at = datetime.now(timezone.utc)
    return {
        "source": "github",
        "event_type": "push",
        "data": {
            "repo": payload.get("repository", {}).get("full_name"),
            "pusher": payload.get("pusher", {}).get("name"),
            "ref": payload.get("ref"),
            "commits": len(payload.get("commits", [])),
        },
        "occurred_at": occurred_at,
    }


NORMALIZERS = {
    "frankfurter": normalize_frankfurter,
    "github": normalize_github,
}


def normalize(raw: models.RawEvent) -> dict:
    fn = NORMALIZERS.get(raw.source)
    if fn is None:
        raise ValueError(f"no normalizer for source={raw.source}")
    return fn(raw)
