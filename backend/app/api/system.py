"""
System health and monitoring routes
"""
import psutil
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from ..db.database import get_db
from ..db.models import Job, JobStatus
from ..schemas.schemas import HealthCheck, SystemStats
from ..core.config import settings
from ..core.celery_app import celery_app
from ..core.security import get_current_user

router = APIRouter(prefix="/system", tags=["System"])


class WorkerConfigUpdate(BaseModel):
    """Worker configuration update request"""
    max_workers: int = Field(ge=1, le=10, description="Maximum concurrent workers (1-10)")


@router.post("/config/workers")
async def update_worker_config(
    config: WorkerConfigUpdate,
    user_id: str = Depends(get_current_user)
):
    """
    Update worker configuration dynamically.
    Updates .env file and restarts Celery service.
    
    Args:
        config: New worker configuration
        user_id: Current user ID
        
    Returns:
        Updated configuration
    """
    try:
        # Update the settings object
        settings.MAX_WORKERS = config.max_workers
        
        # Update .env file
        env_file = settings.BASE_DIR / ".env"
        if env_file.exists():
            with open(env_file, 'r') as f:
                lines = f.readlines()
            
            # Update or add MAX_WORKERS
            updated = False
            for i, line in enumerate(lines):
                if line.startswith('MAX_WORKERS='):
                    lines[i] = f'MAX_WORKERS={config.max_workers}\n'
                    updated = True
                    break
            
            if not updated:
                lines.append(f'MAX_WORKERS={config.max_workers}\n')
            
            with open(env_file, 'w') as f:
                f.writelines(lines)
        
        # Restart Celery service to apply new worker count
        try:
            # Check if running in production (systemd service exists)
            result = subprocess.run(
                ['systemctl', 'is-active', 'datainfo-celery'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 or 'active' in result.stdout:
                # Production: restart systemd service
                subprocess.run(
                    ['sudo', 'systemctl', 'restart', 'datainfo-celery'],
                    check=True,
                    timeout=10
                )
                message = f"Worker configuration updated to {config.max_workers} workers. Celery service restarted."
            else:
                message = f"Worker configuration updated to {config.max_workers} workers. Restart Celery manually to apply changes."
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            # Development or systemctl not available
            message = f"Worker configuration updated to {config.max_workers} workers. Restart Celery manually to apply changes."
        
        return {
            "success": True,
            "max_workers": config.max_workers,
            "message": message
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}"
        )


@router.get("/config/workers")
async def get_worker_config(user_id: str = Depends(get_current_user)):
    """
    Get current worker configuration.
    
    Args:
        user_id: Current user ID
        
    Returns:
        Current worker configuration
    """
    return {
        "max_workers": settings.MAX_WORKERS,
        "max_concurrent_jobs": settings.MAX_CONCURRENT_JOBS
    }


@router.get("/health", response_model=HealthCheck)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Check system health status.
    
    Returns status of all critical components:
    - API server
    - PostgreSQL database
    - Redis cache/queue
    - Celery workers
    
    Args:
        db: Database session
        
    Returns:
        Health status of all components
    """
    # Check database
    try:
        await db.execute(select(1))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    # Check Redis
    try:
        from redis import Redis
        redis_client = Redis.from_url(settings.REDIS_URL)
        redis_client.ping()
        redis_status = "healthy"
    except Exception as e:
        redis_status = f"unhealthy: {str(e)}"
    
    # Check Celery
    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        if stats:
            celery_status = f"healthy ({len(stats)} workers)"
        else:
            celery_status = "no workers"
    except Exception as e:
        celery_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "healthy" if all([
            db_status == "healthy",
            redis_status == "healthy",
            "healthy" in celery_status
        ]) else "degraded",
        "version": settings.APP_VERSION,
        "timestamp": datetime.utcnow(),
        "database": db_status,
        "redis": redis_status,
        "celery": celery_status
    }


@router.get("/stats", response_model=SystemStats)
async def get_system_stats(db: AsyncSession = Depends(get_db)):
    """
    Get system performance statistics.
    
    Returns:
        System resource usage and job statistics
    """
    # CPU and Memory
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(settings.BASE_DIR))
    
    # Job statistics for today
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Active jobs
    active_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.status.in_([JobStatus.RUNNING, JobStatus.QUEUED])
        )
    )
    active_jobs = active_result.scalar() or 0
    
    # Queued jobs
    queued_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.status == JobStatus.QUEUED
        )
    )
    queued_jobs = queued_result.scalar() or 0
    
    # Completed today
    completed_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.status == JobStatus.COMPLETED,
            Job.completed_at >= today
        )
    )
    completed_jobs_today = completed_result.scalar() or 0
    
    # Failed today
    failed_result = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.status == JobStatus.FAILED,
            Job.completed_at >= today
        )
    )
    failed_jobs_today = failed_result.scalar() or 0
    
    # Success rate
    total_today = completed_jobs_today + failed_jobs_today
    success_rate = (completed_jobs_today / total_today * 100) if total_today > 0 else 100.0
    
    return {
        "cpu_percent": cpu_percent,
        "memory_percent": memory.percent,
        "disk_percent": disk.percent,
        "active_jobs": active_jobs,
        "queued_jobs": queued_jobs,
        "completed_jobs_today": completed_jobs_today,
        "failed_jobs_today": failed_jobs_today,
        "success_rate": round(success_rate, 2)
    }


@router.get("/workers")
async def get_worker_status():
    """
    Get Celery worker status and statistics.
    
    Returns:
        Dictionary of worker information
    """
    try:
        inspect = celery_app.control.inspect()
        
        stats = inspect.stats() or {}
        active = inspect.active() or {}
        registered = inspect.registered() or {}
        
        workers = []
        for worker_name, worker_stats in stats.items():
            workers.append({
                "name": worker_name,
                "status": "online",
                "pool": worker_stats.get("pool", {}).get("implementation", "unknown"),
                "max_concurrency": worker_stats.get("pool", {}).get("max-concurrency", 0),
                "active_tasks": len(active.get(worker_name, [])),
                "registered_tasks": len(registered.get(worker_name, []))
            })
        
        return {
            "workers": workers,
            "total_workers": len(workers)
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "workers": [],
            "total_workers": 0
        }


@router.get("/debug/jobs")
async def debug_jobs(db: AsyncSession = Depends(get_db)):
    """Debug endpoint to check jobs without auth."""
    from sqlalchemy import desc
    query = select(Job).order_by(desc(Job.created_at)).limit(10)
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return {
        "jobs": [
            {
                "uuid": j.job_uuid[:8],
                "status": j.status.value,
                "filename": j.display_filename,
                "total": j.total_rows,
                "processed": j.processed_rows,
                "created": j.created_at.isoformat() if j.created_at else None,
                "completed": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]
    }
