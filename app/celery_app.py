from celery import Celery
from app.config import settings

celery_app = Celery(
    "relay",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,           # ack after the task succeeds, not when received
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # one task at a time per worker — safer for retries
)