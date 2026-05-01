"""
Celery background tasks for automation tools
"""
import asyncio
import logging
import signal
import time
from datetime import datetime
from typing import Dict, Any

from celery import Task
from sqlalchemy import select

from app.core.celery_app import celery_app
from app.db.models import Job, JobStatus, JobLog
from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Global flag for termination
_termination_requested = False

def _signal_handler(signum, frame):
    """Handle termination signals."""
    global _termination_requested
    _termination_requested = True
    logger.warning(f"Received signal {signum}, requesting graceful termination")

# Register signal handlers
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def run_async(coro):
    """Helper to run async code in celery tasks."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


class JobTask(Task):
    """Base task class with error handling and progress tracking."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_uuid = kwargs.get('job_uuid')
        if job_uuid:
            run_async(self._update_job_status(
                job_uuid,
                JobStatus.FAILED,
                error_message=str(exc)
            ))

    async def _update_job_status(self, job_uuid: str, status: JobStatus, force: bool = False, **kwargs):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Job).where(Job.job_uuid == job_uuid))
            job = result.scalar_one_or_none()
            if job:
                if not force and job.status in [JobStatus.CANCELLED, JobStatus.PAUSED] and status not in [JobStatus.CANCELLED, JobStatus.PAUSED]:
                    return
                job.status = status
                for key, value in kwargs.items():
                    if hasattr(job, key):
                        setattr(job, key, value)
                await session.commit()

    async def _add_job_log(self, job_uuid: str, level: str, message: str, metadata: Dict[str, Any] = None):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Job).where(Job.job_uuid == job_uuid))
            job = result.scalar_one_or_none()
            if job:
                log = JobLog(job_id=job.id, level=level, message=message, metadata=metadata or {})
                session.add(log)
                await session.commit()
