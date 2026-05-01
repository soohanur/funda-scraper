"""
Retry and Error Recovery Handler

Provides intelligent retry logic with exponential backoff
and browser recovery for Funda automation.
"""
import time
import logging
from typing import Callable, Any
from functools import wraps

logger = logging.getLogger('funda.retry')


class RetryConfig:
    """Retry configuration constants."""
    MAX_RETRIES = 3
    INITIAL_DELAY = 2  # seconds
    BACKOFF_MULTIPLIER = 2
    MAX_DELAY = 15  # seconds


def retry_with_recovery(
    max_attempts: int = RetryConfig.MAX_RETRIES,
    delay: float = RetryConfig.INITIAL_DELAY,
    backoff: float = RetryConfig.BACKOFF_MULTIPLIER,
    exceptions: tuple = (Exception,),
    on_retry: Callable = None,
):
    """
    Decorator for retry logic with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for exponential backoff
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback before each retry

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        logger.info(f"✓ Success on attempt {attempt}/{max_attempts}")
                    return result

                except exceptions as e:
                    last_exception = e
                    logger.warning(
                        f"⚠ Attempt {attempt}/{max_attempts} failed: {str(e)[:150]}"
                    )

                    if attempt < max_attempts:
                        logger.info(f"  Retrying in {current_delay:.1f}s...")
                        time.sleep(current_delay)
                        current_delay = min(current_delay * backoff, RetryConfig.MAX_DELAY)

                        if on_retry:
                            try:
                                on_retry()
                            except Exception as re:
                                logger.error(f"  on_retry callback failed: {re}")

            logger.error(f"✗ All {max_attempts} attempts failed")
            raise last_exception

        return wrapper
    return decorator


def is_browser_error(exception: Exception) -> bool:
    """Check if exception is browser-related."""
    indicators = [
        'chrome', 'driver', 'session', 'timeout',
        'renderer', 'connection', 'webdriver', 'browser'
    ]
    msg = str(exception).lower()
    return any(ind in msg for ind in indicators)


def check_browser_health(driver) -> bool:
    """Quick health check on the browser session."""
    try:
        _ = driver.current_url
        driver.execute_script("return document.readyState")
        return True
    except Exception:
        return False
