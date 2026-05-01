"""
Funda - Property Scraper Automation Tool Configuration
Dedicated configuration for Funda tool with isolated resources
"""

import os
from pathlib import Path
from typing import Optional

# Base directory - Funda tool folder
BASE_DIR = Path(__file__).resolve().parent  # funda/ folder
PROJECT_ROOT = BASE_DIR.parent  # project root

# Funda-specific directories (isolated from other tools)
CSV_DIR = BASE_DIR / "csv_files"
INPUT_DIR = CSV_DIR / "input"
OUTPUT_DIR = CSV_DIR / "output"

# Chrome profiles - SHARED at project root (optimized for memory)
PROFILES_DIR = PROJECT_ROOT / "chrome_profiles"  # Shared across all tools

# Logs directory (funda-specific)
LOGS_DIR = BASE_DIR / "logs"

# Create directories if they don't exist
for directory in [CSV_DIR, INPUT_DIR, OUTPUT_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Chrome profiles are shared at project root - ensure they exist
PROFILES_DIR.mkdir(parents=True, exist_ok=True)


class Config:
    TOOL_NAME = "Funda"
    TOOL_VERSION = "1.0.0"
    TOOL_DESCRIPTION = "Funda.nl Property Data Scraper"

    BASE_DIR = BASE_DIR
    PROJECT_ROOT = PROJECT_ROOT
    CSV_DIR = CSV_DIR
    INPUT_DIR = INPUT_DIR
    OUTPUT_DIR = OUTPUT_DIR
    PROFILES_DIR = PROFILES_DIR
    LOGS_DIR = LOGS_DIR

    CHROME_PROFILE_PATH = PROFILES_DIR / "default"
    CHROME_DATA_PROFILE_PATH = PROFILES_DIR / "data_profile"

    # Head mode by default for local development (set True for production)
    HEADLESS_MODE = False
    WINDOW_SIZE = "1920,1080"

    # Single worker only (no parallel processing)
    PROCESSING_MODE = "sequential"
    MAX_WORKERS = 1
    MAX_RETRIES = 3
    RETRY_DELAY = 2
    PAGE_LOAD_TIMEOUT = 30
    ELEMENT_WAIT_TIMEOUT = 10

    OUTPUT_PREFIX = "DONE_"
    CSV_DELIMITER = ","
    EXCEL_SHEET_NAME = "Sheet1"

    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - [Funda] %(name)s - %(levelname)s - %(message)s"
    LOG_FILE_NAME = "funda.log"

    # Funda-specific settings
    FUNDA_BASE_URL = "https://www.funda.nl"
    FUNDA_SEARCH_URL = (
        'https://www.funda.nl/zoeken/koop?selected_area=["nl"]'
        '&publication_date=5&availability=["available"]'
    )
    FUNDA_PROPERTY_URL_TEMPLATE = "https://www.funda.nl/{kvk_number}/"

    # How many property KVK numbers to collect per run
    PROPERTIES_TO_COLLECT = 90

    # Results per page on funda.nl (typically 15)
    RESULTS_PER_PAGE = 15

    @classmethod
    def get_log_file_path(cls) -> Path:
        return cls.LOGS_DIR / cls.LOG_FILE_NAME

    @classmethod
    def get_input_file_path(cls, filename: str) -> Path:
        return cls.INPUT_DIR / filename

    @classmethod
    def get_output_file_path(cls, filename: str) -> Path:
        if not filename.startswith(cls.OUTPUT_PREFIX):
            name_parts = filename.rsplit(".", 1)
            if len(name_parts) == 2:
                filename = f"{cls.OUTPUT_PREFIX}{name_parts[0]}.{name_parts[1]}"
            else:
                filename = f"{cls.OUTPUT_PREFIX}{filename}"
        return cls.OUTPUT_DIR / filename

    @classmethod
    def ensure_directories_exist(cls):
        for directory in [cls.INPUT_DIR, cls.OUTPUT_DIR, cls.PROFILES_DIR, cls.LOGS_DIR]:
            directory.mkdir(parents=True, exist_ok=True)


class DevelopmentConfig(Config):
    HEADLESS_MODE = False
    LOG_LEVEL = "DEBUG"


class ProductionConfig(Config):
    HEADLESS_MODE = True
    LOG_LEVEL = "INFO"
    PROCESSING_MODE = "sequential"  # Single worker for now
    MAX_WORKERS = 1


config = Config()


def get_config(env: Optional[str] = None) -> Config:
    if env == "development":
        return DevelopmentConfig()
    elif env == "production":
        return ProductionConfig()
    else:
        return Config()
