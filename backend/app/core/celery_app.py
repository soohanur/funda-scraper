"""
Celery configuration for background task processing
"""
from celery import Celery
from ..core.config import settings

# Create Celery app
celery_app = Celery(
    "automation_platform",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.automation_tasks"]
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.JOB_TIMEOUT,
    task_soft_time_limit=settings.JOB_TIMEOUT - 300,  # 5 minutes before hard limit
    worker_prefetch_multiplier=1,  # One task at a time
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks (memory cleanup)
    task_acks_late=False,  # Acknowledge immediately to prevent redelivery
    task_reject_on_worker_lost=True,
    result_expires=3600 * 24 * 7,  # Keep results for 7 days
)

# Task routing (for future multi-queue support)
celery_app.conf.task_routes = {
    "app.tasks.*": {"queue": "default"},
}

# Priority levels
celery_app.conf.task_default_priority = 5  # Normal priority
