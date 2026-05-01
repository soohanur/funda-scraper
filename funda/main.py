"""
Funda Property Scraper — Main Entry Point

Step 1:  Collect property IDs from funda.nl search results.
Step 2:  Open each property, scrape data, filter by price,
         calculate bidding price, scrape agency info, write Excel.

Remembers last search page number so collection can continue
where it left off on the next run.

Run:
    cd "Data Info"
    python -m funda.main
"""
import sys
import json
import time
import random
import logging
from pathlib import Path

# Ensure project root is on the path so relative imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from funda.src.config import config
from funda.src.modules import (
    create_browser,
    PropertyCollector,
    PropertyScraper,
    AgencyScraper,
    ExcelWriter,
)
from funda.src.utils.logger import setup_logger, log_step

# ── Configure logging ────────────────────────────────────────
log_file = Path(__file__).parent / "logs" / "funda.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - [Funda] %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding='utf-8'),
    ],
)
logger = setup_logger('funda.main', log_file=log_file, log_level=config.LOG_LEVEL)


class FundaAutomation:
    """
    Main automation orchestrator for Funda property scraping.

    Step 1: Collect property IDs from search results.
    Step 2: Scrape each property page → filter → agency → Excel.
    """

    def __init__(self):
        self.config = config
        self.browser = None
        self.collector = None
        self.scraper = None
        self.agency_scraper = None
        self.state_file = Path(config.STATE_FILE)

    # ─── State persistence ────────────────────────────────────

    def _load_state(self) -> dict:
        """Load saved state (last page number, processed IDs)."""
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    state = json.load(f)
                logger.info(f"  Loaded state: last_page={state.get('last_page', 0)}, "
                            f"processed={len(state.get('processed_ids', []))}")
                return state
            except Exception as e:
                logger.warning(f"  Could not load state: {e}")
        return {'last_page': 0, 'processed_ids': []}

    def _save_state(self, state: dict) -> None:
        """Save state to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.debug(f"  State saved: last_page={state.get('last_page')}")
        except Exception as e:
            logger.warning(f"  Could not save state: {e}")

    # ─── Main pipeline ────────────────────────────────────────

    def run(self) -> bool:
        """Execute the full automation pipeline (Step 1 + Step 2)."""
        logger.info("=" * 60)
        logger.info("  FUNDA PROPERTY SCRAPER — STARTED")
        logger.info("=" * 60)
        logger.info(f"  Search URL  : {self.config.FUNDA_SEARCH_URL}")
        logger.info(f"  Collect     : {self.config.PROPERTIES_TO_COLLECT} properties")
        logger.info(f"  Process     : {self.config.PROPERTIES_TO_PROCESS} properties")
        logger.info(f"  Headless    : {self.config.HEADLESS}")
        logger.info("")

        start_time = time.time()
        state = self._load_state()

        try:
            # ── Start browser ─────────────────────────────────
            log_step(logger, "Starting Chrome browser")
            self.browser = create_browser(
                headless=self.config.HEADLESS,
                implicit_wait=self.config.IMPLICIT_WAIT,
            )
            log_step(logger, "Starting Chrome browser", "COMPLETE")

            # ── STEP 1: Collect property IDs ──────────────────
            log_step(logger, "Step 1 — Collect property IDs")

            self.collector = PropertyCollector(
                browser=self.browser,
                search_url=self.config.FUNDA_SEARCH_URL,
                target_count=self.config.PROPERTIES_TO_COLLECT,
                min_page_delay=self.config.MIN_DELAY_BETWEEN_PAGES,
                max_page_delay=self.config.MAX_DELAY_BETWEEN_PAGES,
            )

            kvk_numbers = self.collector.collect_kvk_numbers()

            if not kvk_numbers:
                logger.error("No property IDs collected — aborting.")
                log_step(logger, "Step 1", "FAIL")
                return False

            # Remember last page number for continuation
            pages_used = (len(kvk_numbers) + self.config.RESULTS_PER_PAGE - 1) // self.config.RESULTS_PER_PAGE
            state['last_page'] = state.get('last_page', 0) + pages_used
            self._save_state(state)

            logger.info(f"  Collected {len(kvk_numbers)} property IDs")
            log_step(logger, "Step 1", "COMPLETE")

            # ── STEP 2: Scrape individual properties ──────────
            log_step(logger, "Step 2 — Scrape property details")

            self.scraper = PropertyScraper(browser=self.browser)
            self.agency_scraper = AgencyScraper(browser=self.browser)

            # Determine how many to process
            to_process = self.config.PROPERTIES_TO_PROCESS
            if to_process <= 0:
                to_process = len(self.collector.collected)

            properties_to_scrape = self.collector.collected[:to_process]
            logger.info(
                f"  Processing {len(properties_to_scrape)} of "
                f"{len(self.collector.collected)} collected properties"
            )

            scraped_properties = []
            skipped = 0

            for idx, prop_info in enumerate(properties_to_scrape, 1):
                logger.info(f"\n{'─' * 50}")
                logger.info(
                    f"  Property {idx}/{len(properties_to_scrape)}: "
                    f"{prop_info['id']} — {prop_info['address']}"
                )

                # Skip already processed
                if prop_info['id'] in state.get('processed_ids', []):
                    logger.info("    Already processed — skipping")
                    skipped += 1
                    continue

                # Scrape property page
                result = self.scraper.scrape_property(prop_info)

                if result is None:
                    logger.info("    Property filtered out or failed")
                    skipped += 1
                    # Mark as processed even if filtered
                    state.setdefault('processed_ids', []).append(prop_info['id'])
                    self._save_state(state)
                    continue

                # Scrape agency info (phone + email)
                result = self.agency_scraper.scrape_agency(result)

                scraped_properties.append(result)

                # Mark as processed
                state.setdefault('processed_ids', []).append(prop_info['id'])
                self._save_state(state)

                # Human-like delay between properties
                if idx < len(properties_to_scrape):
                    delay = random.uniform(
                        self.config.MIN_DELAY_BETWEEN_PROPERTIES,
                        self.config.MAX_DELAY_BETWEEN_PROPERTIES,
                    )
                    time.sleep(delay)

            logger.info(f"\n{'─' * 50}")
            logger.info(
                f"  Step 2 results: {len(scraped_properties)} scraped, "
                f"{skipped} skipped/filtered"
            )
            log_step(logger, "Step 2", "COMPLETE")

            # ── STEP 3: Write Excel ───────────────────────────
            if scraped_properties:
                log_step(logger, "Step 3 — Write Excel output")

                writer = ExcelWriter(output_dir=config.OUTPUT_DIR)
                excel_path = writer.write(scraped_properties)

                logger.info(f"  ✓ Excel file: {excel_path}")
                log_step(logger, "Step 3", "COMPLETE")
            else:
                logger.info("  No properties to write — skipping Excel output")

            # ── Summary ───────────────────────────────────────
            elapsed = time.time() - start_time
            logger.info("")
            logger.info("=" * 60)
            logger.info("  PIPELINE COMPLETE — SUMMARY")
            logger.info("=" * 60)
            logger.info(f"  Properties collected : {len(kvk_numbers)}")
            logger.info(f"  Properties processed : {len(properties_to_scrape)}")
            logger.info(f"  Properties scraped   : {len(scraped_properties)}")
            logger.info(f"  Properties skipped   : {skipped}")
            logger.info(f"  Last search page     : {state.get('last_page', '?')}")
            logger.info(f"  Total time           : {elapsed:.1f}s")
            logger.info("=" * 60)

            # Print scraped data summary
            for prop in scraped_properties:
                logger.info(f"\n  📍 {prop['address']}")
                logger.info(f"     URL: {prop['url']}")
                logger.info(f"     Asking: {prop['asking_price_formatted']}")
                logger.info(f"     Energy: {prop['energielabel']}")
                logger.info(f"     Photos: {len(prop['photo_urls'])}")
                logger.info(f"     Agency: {prop['agency_name']}")
                logger.info(f"     Phone: {prop['agency_phone']}")
                logger.info(f"     Email: {prop['agency_email']}")

            return True

        except KeyboardInterrupt:
            logger.warning("Interrupted by user")
            return False
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            return False
        finally:
            if self.browser:
                self.browser.close_browser()


def main():
    automation = FundaAutomation()
    success = automation.run()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
