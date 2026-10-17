# Relay

A reliable event-driven integration service. Relay collects data from multiple sources, normalizes it, and makes it available to downstream applications.

Relay is the infrastructure layer *behind* an application: the part that handles webhooks, background jobs, retries, and dead letters so you don't have to build them from scratch.

## Why it exists

Most integrations break when a webhook fires twice, an API goes down, or a worker crashes. Relay handles these cases structurally:

1. **Idempotency**: no duplicate processing
2. **HMAC verification**: no spoofed webhooks
3. **Retries and dead letters**: no silently lost data

## Architecture

### Data flow diagram

Numbered flows follow a webhook event end to end. Trust boundaries show where input is verified before it is trusted.

```mermaid
flowchart LR
    GH(["External entity<br/>GitHub"])
    SM(["External entity<br/>smee.io tunnel"])
    FX(["External entity<br/>Frankfurter API"])
    DS(["External entity<br/>Downstream app"])
    OP(["External entity<br/>Operator"])

    subgraph TB1["Trust boundary 1: API service (FastAPI)"]
        P1["P1 Webhook receiver<br/>HMAC verify"]
        P5["P5 Events API<br/>API key auth"]
        P6["P6 Admin and recovery<br/>keys, requeue, sweep"]
    end

    subgraph TB2["Trust boundary 2: Worker service (Celery)"]
        P2["P2 Poller<br/>fetch rates"]
        P3["P3 ingest()<br/>shared by all producers"]
        P4["P4 Normalize worker<br/>retry 2s, 4s, 8s, then dead"]
    end

    subgraph TB3["Trust boundary 3: Data tier (Docker)"]
        Q[("Q Redis<br/>task broker")]
        D1[("D1 raw_events<br/>unique source + external_id")]
        D2[("D2 events")]
        D3[("D3 delivery_attempts")]
        D4[("D4 api_keys<br/>SHA-256 hashes")]
    end

    GH -->|"1. push event + X-Hub-Signature-256"| SM
    SM -->|"2. forward"| P1
    P1 -->|"3. verified payload<br/>(401 if signature fails)"| P3
    FX -->|"rates JSON"| P2
    P2 -->|"base-date external_id"| P3

    P3 <-->|"4. insert or dedup<br/>(created: false = stop)"| D1
    P3 -->|"5. enqueue normalize<br/>(new events only)"| Q
    Q -->|"6. deliver task<br/>(late ack)"| P4
    P4 <-->|"7. read raw, set status"| D1
    P4 -->|"8. write normalized"| D2
    P4 -->|"9. log every attempt"| D3

    DS -->|"10. GET /events + Bearer key"| P5
    P5 <-->|"11. hash and compare"| D4
    P5 <-->|"12. read"| D2

    OP -->|"create key, requeue dead,<br/>sweep stuck"| P6
    P6 -->|"store hash"| D4
    P6 <-->|"reset status"| D1
    P6 -->|"re-enqueue"| Q
```

**Legend:** `P#` processes (rectangles), `D#` and `Q` data stores (cylinders), external entities (stadium shapes). Arrows with a two-way head are read and write.

**What each boundary enforces**
- **External to API:** webhooks are rejected with `401` unless the HMAC signature matches. Downstream reads require a valid API key.
- **Producers to ingest():** polling and webhooks share one `ingest()` path, so dedup behaves identically for both.
- **Worker to data tier:** `task_acks_late=True` means a crashed worker's task is redelivered, not lost.
- **Credentials at rest:** only SHA-256 hashes of API keys are stored, so a DB leak exposes no working credentials.

### raw_events lifecycle

`pending` → `processing` → `processed`
`processing` → `failed` (retry with backoff) → `dead` after 3 failed attempts
`dead` → `pending` via the recovery endpoint

## Core features

**Two producers, one pipeline**
- **Polling:** a Celery task fetches exchange rates from the Frankfurter API.
- **Webhooks:** a FastAPI endpoint receives GitHub push events via a smee.io tunnel.
- Both producers call the same `ingest()` function.

**Idempotency by design**
- Dedup is enforced by a unique constraint on `(source, external_id)` in the database.
- GitHub webhooks dedup on `X-GitHub-Delivery`. Polling dedups on `base-date`.
- Duplicate requests return `created: false` and do not re-enqueue the worker.

**Fault tolerance**
- **HMAC verification:** GitHub webhooks are rejected with `401` if `X-Hub-Signature-256` doesn't match the payload.
- **Exponential backoff:** if normalization fails, Celery retries the task (2s, 4s, 8s).
- **Dead letters:** after 3 failed attempts, the raw event is marked `dead` to stop log spam.
- **Recovery:** API endpoints can requeue dead events or sweep stuck events.
- **Late acks:** `task_acks_late=True` ensures tasks aren't lost if a worker crashes mid-execution.

**Downstream security**
- Downstream apps authenticate with API keys (`Authorization: Bearer <key>`).
- Keys are hashed with SHA-256 before storage.

## Data model

| Table | Purpose |
|---|---|
| `raw_events` | Every incoming payload. Unique on `(source, external_id)`. Drives the retry loop via `status` (`pending`, `processing`, `processed`, `failed`, `dead`). |
| `events` | Normalized output. One per raw event. This is what consumers read. |
| `delivery_attempts` | Audit trail of every processing attempt, success or failure. |
| `api_keys` | Downstream auth. Keys are stored as SHA-256 hashes, never raw. |

## Configuration

Copy `.env.example` to `.env`:

```bash
DATABASE_URL=postgresql+psycopg2://relay:relay@localhost:5433/relay
REDIS_URL=redis://localhost:6380/0
CELERY_BROKER_URL=redis://localhost:6380/0
CELERY_RESULT_BACKEND=redis://localhost:6380/1
GITHUB_WEBHOOK_SECRET=dev-secret-change-me
```

`.gitignore` should exclude `.venv/`, `__pycache__/`, `.pytest_cache/`, `.env`, `.env.*` (keeping `!.env.example`), `.DS_Store`, and `*.log`.

## Running locally

**Prerequisites:** Docker, Python 3.11+, Node.js (for smee).

### 1. Start infrastructure

```bash
docker compose up -d
```

Postgres runs on `5433` and Redis on `6380` to avoid clashing with other local projects.

### 2. Start the backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi "uvicorn[standard]" sqlalchemy psycopg2-binary pydantic-settings python-dotenv "celery[redis]" redis httpx

cp .env.example .env

python -c "from app.db import Base, engine; from app import models; Base.metadata.create_all(bind=engine)"
python -m uvicorn app.main:app --reload --port 8000
```

### 3. Start the Celery worker

In a separate terminal:

```bash
source .venv/bin/activate
celery -A app.celery_app:celery_app worker --loglevel=info
```

### 4. Create an API key

```bash
curl -X POST http://localhost:8000/admin/keys \
     -H "Content-Type: application/json" \
     -d '{"name": "local-test"}'
```

Save the returned `api_key`. Query `http://localhost:8000/events` with the `Authorization: Bearer <key>` header, or use the Swagger UI at `/docs`.

### 5. Test the pipeline

```bash
python test_ingest.py       # Dedup and idempotency
python test_webhook.py      # HMAC verification
python test_deadletter.py   # Retries and DLQ
python test_api.py          # Downstream API
```

## Tech stack

FastAPI · Celery · Redis · PostgreSQL · SQLAlchemy · Docker · smee.io