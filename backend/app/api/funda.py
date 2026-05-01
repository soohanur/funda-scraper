"""
Funda Property Scraper API Router

REST API endpoints for controlling the Funda scraper.
"""
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import logging

# Add funda package to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/funda", tags=["Funda"])


# ── Pydantic Models ────────────────────────────────────────────

class StartRequest(BaseModel):
    """Request body for starting the scraper."""
    publication_date: int = Field(
        default=5,
        ge=5,
        le=31,
        description="Date range option: 5=3-7d ago, 10=8-12d ago, 15=13-17d ago, 30=25-30d ago, 31=30+d ago"
    )


class StatusResponse(BaseModel):
    """Response for scraper status."""
    status: str
    total_kvk_stored: int
    kvk_collected_this_session: int
    total_search_results: int = 0
    current_batch: int
    properties_scraped: int
    properties_filtered: int
    properties_failed: int
    current_page: int
    total_pages_scraped: int
    batch_progress: int
    active_workers: int = 0
    excel_files_created: int
    sheets_written: int = 0
    valuations_written: int = 0
    valuations_failed: int = 0
    valuations_pending: int = 0
    valuations_fallback: int = 0
    elapsed_seconds: float
    last_error: str
    browser_restarts: int = 0
    collection_status: str = ""
    collection_page: int = 0
    ids_collected: int = 0
    ids_queued: int = 0
    duplicate_in_storage: int = 0
    duplicate_in_retry_queue: int = 0
    consecutive_failures: int = 0


class ActionResponse(BaseModel):
    """Response for scraper actions."""
    success: bool
    message: str
    status: str


class KvkStatsResponse(BaseModel):
    """Response for KVK storage stats."""
    total_stored: int
    sample: list = []


class ClearKvkStorageResponse(BaseModel):
    """Response for clearing KVK storage."""
    success: bool
    message: str
    cleared_count: int
    total_kvk_stored: int


# ── Global scraper state ───────────────────────────────────────
# We lazily import the funda controller to avoid import errors at startup
_controller = None
_import_error: Optional[str] = None


def _get_controller():
    """Lazily import and get the funda controller."""
    global _controller, _import_error
    
    if _import_error:
        raise HTTPException(
            status_code=500,
            detail=f"Funda module import error: {_import_error}"
        )
    
    try:
        from funda.src.modules import get_controller
        return get_controller()
    except ImportError as e:
        _import_error = str(e)
        logger.error(f"Failed to import funda modules: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Funda module not available: {e}"
        )


def _start_scraper(publication_date: int):
    """Import and start the scraper."""
    try:
        from funda.src.modules import start_scraper
        return start_scraper(publication_date=publication_date)
    except ImportError as e:
        logger.error(f"Failed to import funda modules: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Funda module not available: {e}"
        )


def _stop_scraper():
    """Import and stop the scraper."""
    try:
        from funda.src.modules import stop_scraper
        return stop_scraper()
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))


def _pause_scraper():
    """Import and pause the scraper."""
    try:
        from funda.src.modules import pause_scraper
        return pause_scraper()
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))


def _resume_scraper():
    """Import and resume the scraper."""
    try:
        from funda.src.modules import resume_scraper
        return resume_scraper()
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_stats():
    """Import and get scraper stats."""
    try:
        from funda.src.modules import get_scraper_stats
        return get_scraper_stats()
    except ImportError as e:
        return {
            'status': 'IDLE',
            'total_kvk_stored': 0,
            'kvk_collected_this_session': 0,
            'total_search_results': 0,
            'current_batch': 0,
            'properties_scraped': 0,
            'properties_filtered': 0,
            'properties_failed': 0,
            'current_page': 0,
            'total_pages_scraped': 0,
            'batch_progress': 0,
            'active_workers': 0,
            'excel_files_created': 0,
            'sheets_written': 0,
            'valuations_written': 0,
            'valuations_failed': 0,
            'valuations_pending': 0,
            'valuations_fallback': 0,
            'elapsed_seconds': 0,
            'last_error': str(e),
            'browser_restarts': 0,
            'collection_status': '',
            'collection_page': 0,
            'ids_collected': 0,
            'ids_queued': 0,
            'duplicate_in_storage': 0,
            'duplicate_in_retry_queue': 0,
            'consecutive_failures': 0,
        }


def _get_kvk_storage():
    """Import and get KVK storage."""
    try:
        from funda.src.modules import get_kvk_storage
        return get_kvk_storage()
    except ImportError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── API Endpoints ──────────────────────────────────────────────

@router.get("/status", response_model=StatusResponse)
async def get_status():
    """
    Get current scraper status and stats.
    
    Returns real-time information about the scraping process:
    - Status (IDLE, RUNNING, PAUSED, STOPPING, COMPLETED, FAILED)
    - Collection progress
    - Scraping progress
    - Error information
    """
    stats = _get_stats()

    # Always return the real persistent-storage count so UI cannot show stale values.
    try:
        stats['total_kvk_stored'] = _get_kvk_storage().count()
    except Exception:
        # If storage is temporarily unavailable, keep existing stats value.
        pass

    return StatusResponse(**stats)


@router.post("/start", response_model=ActionResponse)
async def start_scraper(request: StartRequest):
    """
    Start the Funda property scraper.
    
    The scraper will:
    1. Collect property IDs from search results (90 per batch)
    2. Scrape each property's details, filter by price
    3. Extract agency contact information
    4. Write results to Excel
    5. Repeat until no new properties found
    
    **Publication Date Filter:**
    - 1 = Today
    - 3 = Last 3 Days
    - 5 = Last 5 Days (default)
    - 10 = Last 10 Days
    - 30 = Last 30 Days
    """
    current = _get_stats()
    if current['status'] in ['RUNNING', 'PAUSED']:
        raise HTTPException(
            status_code=400,
            detail=f"Scraper is already {current['status'].lower()}. Stop it first."
        )
    
    try:
        _start_scraper(publication_date=request.publication_date)
        return ActionResponse(
            success=True,
            message=f"Scraper started with publication_date={request.publication_date}",
            status="RUNNING"
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/stop", response_model=ActionResponse)
async def stop_scraper_endpoint():
    """
    Stop the running scraper.
    
    The scraper will finish the current operation and then stop.
    Progress is saved automatically.
    """
    current = _get_stats()
    if current['status'] not in ['RUNNING', 'PAUSED']:
        raise HTTPException(
            status_code=400,
            detail=f"Scraper is not running (current status: {current['status']})"
        )
    
    success = _stop_scraper()
    if success:
        return ActionResponse(
            success=True,
            message="Stop signal sent. Scraper will stop after current operation.",
            status="STOPPING"
        )
    else:
        raise HTTPException(status_code=400, detail="Failed to stop scraper")


@router.post("/pause", response_model=ActionResponse)
async def pause_scraper_endpoint():
    """
    Pause the running scraper.
    
    The scraper will pause after the current property is processed.
    Use /resume to continue.
    """
    current = _get_stats()
    if current['status'] != 'RUNNING':
        raise HTTPException(
            status_code=400,
            detail=f"Can only pause a running scraper (current status: {current['status']})"
        )
    
    success = _pause_scraper()
    if success:
        return ActionResponse(
            success=True,
            message="Scraper paused",
            status="PAUSED"
        )
    else:
        raise HTTPException(status_code=400, detail="Failed to pause scraper")


@router.post("/resume", response_model=ActionResponse)
async def resume_scraper_endpoint():
    """
    Resume a paused scraper.
    """
    current = _get_stats()
    if current['status'] != 'PAUSED':
        raise HTTPException(
            status_code=400,
            detail=f"Can only resume a paused scraper (current status: {current['status']})"
        )
    
    success = _resume_scraper()
    if success:
        return ActionResponse(
            success=True,
            message="Scraper resumed",
            status="RUNNING"
        )
    else:
        raise HTTPException(status_code=400, detail="Failed to resume scraper")


@router.get("/kvk-storage", response_model=KvkStatsResponse)
async def get_kvk_storage_stats():
    """
    Get permanent KVK storage statistics.
    
    Shows how many property IDs are stored permanently.
    These IDs will be skipped in future scraping sessions.
    """
    try:
        storage = _get_kvk_storage()
        all_kvks = list(storage.get_all())
        return KvkStatsResponse(
            total_stored=len(all_kvks),
            sample=all_kvks[:10]  # First 10 as sample
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/kvk-storage", response_model=ClearKvkStorageResponse)
async def clear_kvk_storage():
    """
    Clear the permanent KVK storage.
    
    ⚠️ WARNING: This will delete ALL stored property IDs.
    The scraper will start collecting from scratch.
    """
    try:
        current = _get_stats()
        if current['status'] in ['RUNNING', 'PAUSED', 'STOPPING']:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot clear storage while scraper is {current['status'].lower()}. Stop it first."
            )

        storage = _get_kvk_storage()
        count = storage.count()
        storage.clear()

        # If a controller instance exists, sync in-memory counters to fresh-start state.
        controller = None
        try:
            controller = _get_controller()
        except Exception:
            controller = None

        if controller is not None:
            try:
                controller._update_stats(
                    total_kvk_stored=0,
                    kvk_collected_this_session=0,
                    ids_collected=0,
                    ids_queued=0,
                    duplicate_in_storage=0,
                    duplicate_in_retry_queue=0,
                    collection_page=0,
                    collection_status="",
                    current_batch=0,
                    batch_progress=0,
                )
            except Exception:
                # Non-fatal: /status endpoint still returns authoritative storage count.
                pass

        return {
            "success": True,
            "message": f"Cleared {count} KVK numbers from storage",
            "cleared_count": count,
            "total_kvk_stored": 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/publication-date-options")
async def get_publication_date_options():
    """
    Get available publication date filter options.
    
    Returns the list of valid values for the publication_date parameter.
    """
    return {
        "options": [
            {"value": 5, "label": "3-7 Days Ago"},
            {"value": 10, "label": "8-12 Days Ago"},
            {"value": 15, "label": "13-17 Days Ago"},
            {"value": 30, "label": "25-30 Days Ago"},
            {"value": 31, "label": "30+ Days Ago"},
        ],
        "default": 5
    }


@router.get("/sheets-url")
async def get_sheets_url():
    """
    Get the Google Sheets URL for viewing collected data.
    """
    try:
        from funda.src.config import config
        return {
            "url": config.GOOGLE_SHEETS_URL,
            "spreadsheet_id": config.GOOGLE_SHEETS_SPREADSHEET_ID,
        }
    except Exception as e:
        return {
            "url": "https://docs.google.com/spreadsheets/d/1-96C6xdg-gL2kSdWHivE9e-PQucPxS3suB9AO8xDldo/edit",
            "spreadsheet_id": "1-96C6xdg-gL2kSdWHivE9e-PQucPxS3suB9AO8xDldo",
        }
