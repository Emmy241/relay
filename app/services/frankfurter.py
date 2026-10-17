import httpx
from datetime import datetime, timezone


BASE_URL = "https://api.frankfurter.dev/v1"


def fetch_latest(base: str, symbols: list[str]) -> dict:
    url = f"{BASE_URL}/latest"
    params = {"base": base, "symbols": ",".join(symbols)}

    resp = httpx.get(url, params=params, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()

    return {
        "base": data["base"],
        "date": data["date"],
        "rates": data["rates"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }