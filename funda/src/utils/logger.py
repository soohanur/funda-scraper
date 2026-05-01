"""
Logging Utility Module

Provides colored console logging with file output support
for comprehensive application monitoring and debugging.
"""
import logging
import sys
from pathlib import Path
from typing import Optional
from colorama import init, Fore, Style

init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """Console formatter with color coding by log level."""

    LEVEL_COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelname, '')
        record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)


def setup_logger(
    name: str = 'funda',
    log_file: Optional[Path] = None,
    log_level: str = 'INFO'
) -> logging.Logger:
    """
    Configure logger with console and optional file output.

    Args:
        name: Logger identifier
        log_file: Optional path for file logging
        log_level: Minimum level to log

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))
    logger.handlers.clear()

    logger.addHandler(_create_console_handler())

    if log_file:
        logger.addHandler(_create_file_handler(log_file))

    return logger


def _create_console_handler() -> logging.StreamHandler:
    """Create colored console handler."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = ColoredFormatter(
        '%(asctime)s - [Funda] %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    handler.setFormatter(formatter)
    return handler


def _create_file_handler(log_file: Path) -> logging.FileHandler:
    """Create file handler with detailed formatting."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    return handler


def log_step(logger: logging.Logger, step_name: str, status: str = 'START'):
    """Log a named automation step."""
    separator = '=' * 60
    if status == 'START':
        logger.info(f"\n{separator}")
        logger.info(f"  Starting: {step_name}")
        logger.info(separator)
    elif status == 'COMPLETE':
        logger.info(f"  ✓ Completed: {step_name}")
    elif status == 'FAIL':
        logger.error(f"  ✗ Failed: {step_name}")
