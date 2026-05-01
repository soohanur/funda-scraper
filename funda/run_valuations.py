"""
Valuation Pass — Back-fill bid suggestions for already-scraped Sheet rows.

Reads every tab in the Funda Google Sheet, finds rows where
"Walter Play-it-Safe (€)" is empty, queries Walter Living for each one,
runs the ValuationEngine, and back-writes the 4 valuation cells.

Run:
    cd "Data Info"
    python -m funda.run_valuations            # process all pending
    python -m funda.run_valuations --limit 5  # cap per run
"""
import sys
import time
import argparse
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from funda.src.config import config
from funda.src.modules.sheets_writer import SheetsWriter
from funda.src.modules.valuation_engine import ValuationEngine
from funda.src.modules.walter_client import WalterClient
from funda.src.utils.logger import setup_logger

log_file = Path(__file__).parent / "logs" / "valuations.log"
log_file.parent.mkdir(parents=True, exist_ok=True)
logger = setup_logger('funda.run_valuations', log_file=log_file, log_level=config.LOG_LEVEL)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run valuation pass over Funda Sheet")
    ap.add_argument('--limit', type=int, default=0,
                    help='Max rows to process this run (0 = all pending)')
    ap.add_argument('--delay', type=float, default=2.0,
                    help='Seconds to sleep between Walter queries')
    args = ap.parse_args()

    sheets = SheetsWriter()
    pending = sheets.list_pending_valuations()

    if not pending:
        logger.info("Nothing to value — all rows already have a Walter price.")
        return 0

    if args.limit > 0:
        pending = pending[:args.limit]
        logger.info(f"Limiting this run to {len(pending)} rows")

    logger.info(f"Starting Walter Living session for {len(pending)} properties")
    walter = WalterClient(
        email=config.WALTER_EMAIL,
        password=config.WALTER_PASSWORD,
        profile_path=config.WALTER_PROFILE_PATH,
        headless=config.WALTER_HEADLESS,
        port=config.WALTER_PORT,
        response_timeout=config.WALTER_RESPONSE_TIMEOUT,
    )

    written = skipped = failed = 0
    try:
        with ValuationEngine(walter=walter) as engine:
            for i, row in enumerate(pending, start=1):
                addr = row['address']
                url  = row['url']
                logger.info(f"[{i}/{len(pending)}] {row['tab']} row {row['row']}: {addr}")

                prop = {
                    'address':        addr,
                    'asking_price':   row['asking_price'],
                    'days_on_market': row['days_on_market'],
                }
                result = engine.value_property(prop)

                if result.walter_price is None:
                    logger.warning(f"  No Walter price — writing reasoning only")
                    failed += 1
                else:
                    if result.suggested_bid is None:
                        skipped += 1
                    else:
                        written += 1

                sheets.update_valuation_row(url, result.as_sheet_dict())
                if i < len(pending):
                    time.sleep(args.delay)
    finally:
        walter.close()

    logger.info(
        f"Valuation pass done — bids: {written}, skipped (low margin): {skipped}, "
        f"no-walter: {failed}, total: {len(pending)}"
    )
    return 0


if __name__ == '__main__':
    sys.exit(main())
