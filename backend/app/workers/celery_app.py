from celery import Celery
from celery.schedules import crontab

from backend.app.core.config import settings

celery_app = Celery("cloudteck", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.timezone = "UTC"

celery_app.conf.beat_schedule = {
    "flush-usage-counters-every-5m": {
        "task": "backend.app.workers.tasks.flush_usage_counters",
        "schedule": crontab(minute="*/5"),
    },
    "close-billing-cycles-daily": {
        "task": "backend.app.workers.tasks.close_billing_cycles",
        "schedule": crontab(hour=0, minute=15),
    },
}
