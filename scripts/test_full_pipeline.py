"""
End-to-end pipeline test:
  1. Clear KVK memory + all Google Sheet data (keep headers)
  2. Start scraper for publication_date=5 (3-7 Days Ago)
  3. Stop as soon as N properties are written to the sheet
  4. Run valuation pass
  5. Print final sheet state

Usage:  python3 scripts/test_full_pipeline.py [N]   (default N=5)
"""
import sys
import time
import json
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from funda.src.config import config
from funda.src.modules import kvk_storage as kvk_mod
from funda.src.modules.kvk_storage import get_kvk_storage
from funda.src.modules.sheets_writer import SheetsWriter, HEADERS
from funda.src.modules import start_scraper, stop_scraper, get_scraper_stats

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 5
PUB_DATE = 5   # 3-7 Days Ago


def step(msg):
    print(f"\n{'='*70}\n  {msg}\n{'='*70}")


# ─── Step 1: Clear KVK memory ───────────────────────────────────
step(f"1/5  Clear KVK memory ({config.STATE_FILE.parent}/permanent_kvk.json)")
kvk = get_kvk_storage()
before = kvk.count()
try:
    Path(kvk.storage_file).unlink(missing_ok=True)
except Exception:
    pass
# Also clear the scraper state file (last_page cursor)
try:
    Path(config.STATE_FILE).unlink(missing_ok=True)
    print(f"  Removed state file: {config.STATE_FILE}")
except Exception as e:
    print(f"  state file: {e}")
print(f"  KVK before: {before} → cleared")

# Reset singleton so anyone calling get_kvk_storage() reloads fresh from disk
kvk_mod._storage_instance = None
kvk = get_kvk_storage()
print(f"  KVK after reset: {kvk.count()}")


# ─── Step 2: Clear all Sheet tabs ───────────────────────────────
step("2/5  Clear all Google Sheet tabs (keep headers)")
sw = SheetsWriter()
sw._connect()
for ws in sw._spreadsheet.worksheets():
    rows = len(ws.col_values(1))
    if rows > 1:
        ws.delete_rows(2, rows)  # delete all data rows
        print(f"  [{ws.title}]: removed {rows - 1} data rows")
    else:
        print(f"  [{ws.title}]: empty, skipped")


# ─── Step 3: Start scraper, stop after TARGET properties ────────
step(f"3/5  Start scraper (publication_date={PUB_DATE}, target={TARGET} scraped)")
start_t = time.time()
ctrl = start_scraper(publication_date=PUB_DATE)

last_print = 0
while True:
    time.sleep(5)
    stats = get_scraper_stats()
    scraped = stats.get('properties_scraped', 0)
    filtered = stats.get('properties_filtered', 0)
    written = stats.get('sheets_written', 0)
    collected = stats.get('ids_collected', 0)
    status = stats.get('status', '?')
    elapsed = time.time() - start_t

    # Print only on change to keep log clean
    snap = (scraped, filtered, written, collected, status)
    if snap != last_print:
        last_print = snap
        print(f"  t={elapsed:5.0f}s | {status:8s} | "
              f"collected={collected:3d} scraped={scraped:3d} "
              f"filtered={filtered:3d} sheets={written:3d}")

    # Exit criteria
    if written >= TARGET:
        print(f"\n  ✓ Target reached: {written} rows written to Sheets.")
        break
    if status in ('FAILED',):
        print(f"\n  ✗ Scraper failed.")
        break
    if status == 'COMPLETED':
        print(f"\n  Scraper completed (written={written}).")
        break
    if elapsed > 900:   # 15 min hard cap
        print(f"\n  Aborting — 15 min elapsed without reaching target.")
        break

print("\n  Stopping scraper...")
stop_scraper()
# Wait for it to actually stop
for _ in range(30):
    time.sleep(1)
    s = get_scraper_stats().get('status')
    if s in ('COMPLETED', 'IDLE', 'FAILED'):
        print(f"  Scraper {s} after {int(time.time()-start_t)}s")
        break
else:
    print("  Scraper didn't cleanly stop in 30s (continuing anyway)")


# ─── Step 4: Run valuation pass ─────────────────────────────────
step("4/5  Run valuation pass (Walter → sheet back-write)")
rc = subprocess.call([sys.executable, '-m', 'funda.run_valuations'])
print(f"  run_valuations rc={rc}")


# ─── Step 5: Dump final state ───────────────────────────────────
step("5/5  Final Sheet state")
sw2 = SheetsWriter()
sw2._connect()
for ws in sw2._spreadsheet.worksheets():
    vals = ws.get_all_values()
    data = [r for r in vals[1:] if r and r[1]]   # rows with URL
    if not data:
        continue
    print(f"\n  [{ws.title}]: {len(data)} rows")
    for r in data:
        r = r + [''] * (len(HEADERS) - len(r))
        addr   = (r[2] or '')[:40]
        ask    = r[5]
        walter = r[6]    # col G
        woz    = r[7]    # col H
        bid    = r[8]    # col I
        bidding= r[9]    # col J — human controlled
        conf   = r[10]   # col K
        why    = (r[11] or '')[:90]  # col L
        print(f"    {addr:40s} | ask={ask:>9} | W={walter:>9} | WOZ={woz:>9} | "
              f"bid={bid:>9} | human={bidding:>9} | {conf:6s} | {why}")

print("\nDONE.")
