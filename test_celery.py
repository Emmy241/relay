import time
from app.tasks import ping

print("Enqueueing ping(2, 3) …")
result = ping.delay(2, 3)
print(f"task id: {result.id}")

print("Waiting up to 10s for result …")
try:
    value = result.get(timeout=10)
    print(f"result: {value}")
    assert value == 5
    print("\nCELERY WORKING")
except Exception as e:
    print(f"\nFAILED: {e}")
    print("\nDid you start the worker?")
    print("  celery -A app.celery_app:celery_app worker --loglevel=info")
    raise SystemExit(1)
