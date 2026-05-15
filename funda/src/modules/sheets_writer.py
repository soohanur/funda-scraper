"""
Google Sheets Writer Module

Writes scraped Funda property data directly to Google Sheets,
one row per property, instantly after scraping.

Sheet tabs correspond to the publication_date filter:
  3-7 Days Ago | 8-12 Days Ago | 13-17 Days Ago | 25-30 Days Ago | 30+ Days Ago

Uses gspread + google-auth with a service account.
"""
import gspread
from datetime import date
from google.oauth2.service_account import Credentials
from typing import Optional, List, Set

from ..config import config
from ..utils.logger import setup_logger

logger = setup_logger('funda.sheets')

# Google Sheets API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

# Column definitions: (header, pixel_width)
# Valuation columns (Walter / Suggested Bid / Confidence / Reasoning) sit
# directly after Asking Price so the bid decision is readable next to asking.
COLUMNS = [
    ('Scrape Date',                   95),
    ('Property URL',                 180),
    ('Address',                      220),
    ('Listed Since',                  95),
    ('Days on Market',                95),
    ('Asking Price (\u20ac)',        120),
    ('WOZ Value (\u20ac)',           120),
    ('Suggested Bid (\u20ac)',       130),
    ('Bidding Price',                 130),
    ('Price / m\u00b2 (\u20ac)',    100),
    ('Living Area (m\u00b2)',        110),
    ('Plot Area (m\u00b2)',          100),
    ('Rooms',                         65),
    ('Bedrooms',                      75),
    ('Construction Year',            130),
    ('Property Type',                150),
    ('Energy Label',                  90),
    ('Heating',                      160),
    ('Insulation',                   200),
    ('Maintenance Inside',           130),
    ('Maintenance Outside',          130),
    ('Garden',                       100),
    ('Garden Orientation',           130),
    ('Parking',                      150),
    ('VVE (\u20ac/month)',          100),
    ('Erfpacht',                      80),
    ('Acceptance',                   110),
    ('Description',                  280),
    ('Images',                       200),
    ('Agency Name',                  150),
    ('Agency Phone',                 120),
    ('Agency Email',                 160),
    ('Agency Website',               160),
]

HEADERS = [col[0] for col in COLUMNS]

# Header theme: dark navy blue
_HEADER_BG   = {'red': 0.145, 'green': 0.247, 'blue': 0.455}
_HEADER_TEXT = {'red': 1.0,   'green': 1.0,   'blue': 1.0}
# Alternating row colours: white / very light blue
_ROW_ODD     = {'red': 1.0,   'green': 1.0,   'blue': 1.0}
_ROW_EVEN    = {'red': 0.929, 'green': 0.941, 'blue': 0.969}


class _BatchBuffer:
    """Per-tab thread-safe row buffer for batched Google Sheets appends.

    Three scraper workers share one SheetsWriter and may all call
    write_property() at the same time. Each tab gets its own buffer +
    lock so concurrent writes to different publication-date buckets do
    not block each other. The actual gspread append_rows() call runs
    OUTSIDE the buffer lock so workers can keep enqueuing while the
    flush is in flight against Google.

    Flush triggers (whichever fires first):
      • size:  buffer reaches max_size (default 10) — flush in
        whatever thread queued the row that pushed it over the line.
      • timer: SheetsWriter._batch_timer_thread wakes once per second
        and calls maybe_flush_on_timer() — flushes any tab whose
        oldest row is more than _BATCH_FLUSH_INTERVAL_SEC seconds old.
      • shutdown: SheetsWriter.flush_all() (atexit) drains every tab.

    Retry policy on the gspread call mirrors the per-row policy used
    elsewhere in this module: up to 4 attempts with 0/5/15/45s backoff,
    quota-aware, force_reconnect on a half-connected client.
    """

    def __init__(self, writer: "SheetsWriter", worksheet, tab_name: str, max_size: int = 10):
        import threading
        self.writer = writer
        self.worksheet = worksheet
        self.tab_name = tab_name
        self.max_size = max_size
        self.lock = threading.Lock()
        self.flush_lock = threading.Lock()  # serialise flushes per tab
        self.rows: list = []
        self.labels: list = []  # human-readable tags for log lines
        self.first_added_at: Optional[float] = None  # epoch seconds

    def add(self, row: list, label: str) -> None:
        """Enqueue a row. If buffer hits max_size, flush in this thread."""
        import time as _t
        with self.lock:
            self.rows.append(row)
            self.labels.append(label)
            if self.first_added_at is None:
                self.first_added_at = _t.time()
            should_flush = len(self.rows) >= self.max_size
        if should_flush:
            self.flush()

    def maybe_flush_on_timer(self, max_age_sec: float) -> None:
        """Called by the writer's daemon timer thread. Flush if the
        oldest row in the buffer is older than max_age_sec."""
        import time as _t
        with self.lock:
            if not self.rows or self.first_added_at is None:
                return
            age = _t.time() - self.first_added_at
            if age < max_age_sec:
                return
        # Drop lock before flush; flush() takes its own snapshot.
        self.flush()

    def flush(self) -> bool:
        """Drain buffer to the sheet. Safe to call concurrently with
        add() — we snapshot under the buffer lock, then run the slow
        Google API call serialised by flush_lock so two timers don't
        both POST the same payload."""
        # Drain under the buffer lock so callers see an empty buffer
        # immediately and any new rows start a fresh window.
        with self.lock:
            if not self.rows:
                return True
            rows = self.rows
            labels = self.labels
            self.rows = []
            self.labels = []
            self.first_added_at = None

        # Serialise the actual API call per tab so timer + size-trigger
        # flushes never race each other.
        with self.flush_lock:
            return self._send(rows, labels)

    def _send(self, rows: list, labels: list) -> bool:
        import time as _t
        backoff = [0, 5, 15, 45]
        for attempt in range(1, len(backoff) + 1):
            if backoff[attempt - 1] > 0:
                _t.sleep(backoff[attempt - 1])
            try:
                self.worksheet.append_rows(rows, value_input_option='USER_ENTERED')
                logger.info(
                    f"  ✓ Sheets [{self.tab_name}] batch flushed: {len(rows)} rows"
                )
                if labels:
                    # One-line digest so individual properties are still
                    # traceable in the journal.
                    sample = ', '.join(str(l) for l in labels[:3])
                    extra = '' if len(labels) <= 3 else f' (+{len(labels) - 3} more)'
                    logger.info(f"    → {sample}{extra}")
                return True
            except Exception as e:
                msg = str(e).lower()
                is_quota = (
                    '429' in msg
                    or 'quota' in msg
                    or 'rate' in msg
                    or 'resource_exhausted' in msg
                )
                if is_quota and attempt < len(backoff):
                    logger.warning(
                        f"  Sheets batch [{self.tab_name}] quota hit "
                        f"(attempt {attempt}/{len(backoff)}) — backing off "
                        f"{backoff[attempt]}s"
                    )
                    continue
                if attempt < len(backoff):
                    logger.warning(
                        f"  Sheets batch [{self.tab_name}] transient error "
                        f"(attempt {attempt}/{len(backoff)}) — forcing reconnect: {e}"
                    )
                    self.writer._force_reconnect()
                    # Re-fetch worksheet after reconnect — handle on the SAME
                    # thread so subsequent retries see a fresh handle.
                    try:
                        self.worksheet = self.writer._get_or_create_worksheet(self.tab_name)
                    except Exception as we:
                        logger.warning(
                            f"  Sheets batch [{self.tab_name}] worksheet refetch failed: {we}"
                        )
                    continue
                logger.error(
                    f"  ✗ Sheets batch [{self.tab_name}] FAILED after {attempt} attempts — "
                    f"{len(rows)} rows lost: {e}"
                )
                return False
        return False


class SheetsWriter:
    """Writes property data to Google Sheets in real-time."""

    # ── Batch-write tunables ──────────────────────────────────
    # Three scraper workers append rows concurrently. We coalesce them into
    # one Google Sheets API call per N rows (or every flush-interval
    # seconds, whichever comes first) so we don't blow the 60-write/min
    # quota and cause cascading 429 backoffs.
    _BATCH_SIZE = 10                # flush when buffer reaches this
    _BATCH_FLUSH_INTERVAL_SEC = 3.0 # flush sooner if any row sits this long

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        spreadsheet_id: Optional[str] = None,
    ):
        self.credentials_path = credentials_path or config.GOOGLE_SHEETS_CREDENTIALS
        self.spreadsheet_id   = spreadsheet_id   or config.GOOGLE_SHEETS_SPREADSHEET_ID
        self._client: Optional[gspread.Client]       = None
        self._spreadsheet: Optional[gspread.Spreadsheet] = None
        # Guards _connect against concurrent reconnect attempts (writer thread,
        # valuation thread, bidding-mirror BackgroundTask, dashboard sync).
        import threading
        self._connect_lock = threading.Lock()
        self._formatted_sheets: Set[str] = set()   # track formatted tabs this session
        # In-memory URL set per tab, seeded from the sheet on first use and
        # updated after every append. Prevents writing a property twice — both
        # within a session AND across sessions (e.g. when a prior run's write
        # reported failure due to Google API eventual consistency but actually
        # landed, so the property never got added to KVK and gets re-scraped).
        self._tab_urls: dict = {}   # tab_name -> set(url)

        # Batch-write state. One queue per sheet tab so concurrent workers
        # writing to different publication_date buckets never block each
        # other and we always flush homogeneous rows with one API call.
        self._batches: dict = {}                # tab_name -> _BatchBuffer
        self._batches_lock = threading.Lock()   # guards _batches dict
        self._batch_timer_stop = threading.Event()
        self._batch_timer_thread: Optional[threading.Thread] = None
        self._start_batch_timer()
        # Best-effort flush on interpreter shutdown so the last partial
        # batch isn't silently lost.
        import atexit
        atexit.register(self.flush_all)

    # ── Connection ────────────────────────────────────────────

    def _connect(self) -> None:
        # Both must be live — earlier code only checked _client, which broke
        # if a prior open_by_key failure left _spreadsheet=None or a thread
        # raced past the guard before the spreadsheet handle was assigned.
        if self._client is not None and self._spreadsheet is not None:
            return
        with self._connect_lock:
            if self._client is not None and self._spreadsheet is not None:
                return
            try:
                creds = Credentials.from_service_account_file(
                    self.credentials_path, scopes=SCOPES,
                )
                client = gspread.authorize(creds)
                spreadsheet = client.open_by_key(self.spreadsheet_id)
            except Exception:
                # Reset both so the next call retries cleanly instead of
                # entering the half-connected state that caused
                # 'NoneType has no attribute worksheet'.
                self._client = None
                self._spreadsheet = None
                raise
            self._client = client
            self._spreadsheet = spreadsheet
            logger.info(f"Connected to Google Sheets: {self._spreadsheet.title}")

    def _force_reconnect(self) -> None:
        """Drop cached client + spreadsheet so the next op rebuilds them."""
        with self._connect_lock:
            self._client = None
            self._spreadsheet = None
            self._formatted_sheets.clear()
            self._tab_urls.clear()

    # ── Worksheet setup ───────────────────────────────────────

    def _get_or_create_worksheet(self, tab_name: str) -> gspread.Worksheet:
        """Get existing worksheet or create it, then ensure headers + formatting."""
        self._connect()
        # Belt-and-braces: if a prior op left _spreadsheet None despite _client
        # being set, force a clean reconnect now instead of crashing with
        # 'NoneType has no attribute worksheet'.
        if self._spreadsheet is None:
            self._force_reconnect()
            self._connect()

        try:
            ws = self._spreadsheet.worksheet(tab_name)
        except gspread.WorksheetNotFound:
            ws = self._spreadsheet.add_worksheet(
                title=tab_name, rows=2000, cols=len(HEADERS),
            )
            logger.info(f"Created new sheet tab: {tab_name}")

        # Update headers if missing or outdated
        existing = ws.row_values(1)
        if not existing or existing != HEADERS:
            ws.update(values=[HEADERS], range_name='A1')
            logger.info(f"Headers updated on tab: {tab_name}")

        # Apply formatting once per session per tab
        if tab_name not in self._formatted_sheets:
            self._apply_sheet_formatting(ws)
            self._formatted_sheets.add(tab_name)

        # Seed the in-memory URL set from the sheet's Property URL column (B)
        # the first time we touch this tab. Used for append-time dedup.
        if tab_name not in self._tab_urls:
            try:
                col_b = ws.col_values(2)   # includes header
                self._tab_urls[tab_name] = {v.strip() for v in col_b[1:] if v and v.strip()}
                logger.info(f"  Seeded {len(self._tab_urls[tab_name])} known URLs for tab: {tab_name}")
            except Exception as e:
                logger.warning(f"  Could not seed URL set for {tab_name}: {e}")
                self._tab_urls[tab_name] = set()

        return ws

    # ── Formatting ────────────────────────────────────────────

    def _apply_sheet_formatting(self, ws: gspread.Worksheet) -> None:
        """
        Apply professional formatting to a worksheet:
        - Dark navy header with white bold text, 40 px tall, frozen
        - Data rows: 21 px fixed height, text CLIPPED (never expands row)
        - Alternating row banding (white / light blue)
        - Per-column pixel widths
        """
        try:
            sid      = ws.id
            num_cols = len(HEADERS)
            max_rows = 2000

            # Expand sheet to fit all columns before setting widths
            ws.resize(rows=max_rows, cols=num_cols)

            requests = [
                # ── 1. Header row style ───────────────────────
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sid,
                            "startRowIndex": 0, "endRowIndex": 1,
                            "startColumnIndex": 0, "endColumnIndex": num_cols,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": _HEADER_BG,
                                "textFormat": {
                                    "foregroundColor": _HEADER_TEXT,
                                    "bold": True,
                                    "fontSize": 9,
                                    "fontFamily": "Arial",
                                },
                                "wrapStrategy": "WRAP",
                                "verticalAlignment": "MIDDLE",
                                "horizontalAlignment": "CENTER",
                            }
                        },
                        "fields": "userEnteredFormat(backgroundColor,textFormat,"
                                  "wrapStrategy,verticalAlignment,horizontalAlignment)",
                    }
                },
                # ── 2. Header row height: 40 px ───────────────
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sid,
                            "dimension": "ROWS",
                            "startIndex": 0, "endIndex": 1,
                        },
                        "properties": {"pixelSize": 40},
                        "fields": "pixelSize",
                    }
                },
                # ── 3. Data rows fixed height: 21 px ─────────
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sid,
                            "dimension": "ROWS",
                            "startIndex": 1, "endIndex": max_rows,
                        },
                        "properties": {"pixelSize": 21},
                        "fields": "pixelSize",
                    }
                },
                # ── 4. All data cells: CLIP wrap ──────────────
                #    This is the key fix — text never expands row height
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sid,
                            "startRowIndex": 1, "endRowIndex": max_rows,
                            "startColumnIndex": 0, "endColumnIndex": num_cols,
                        },
                        "cell": {
                            "userEnteredFormat": {
                                "wrapStrategy": "CLIP",
                                "verticalAlignment": "MIDDLE",
                                "textFormat": {
                                    "fontSize": 9,
                                    "fontFamily": "Arial",
                                },
                            }
                        },
                        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment,textFormat)",
                    }
                },
                # ── 5. Freeze header row ──────────────────────
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sid,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
            ]

            # ── 6. Alternating row banding ────────────────────
            # Remove existing banding first to avoid duplicates
            try:
                sheet_info = self._spreadsheet.fetch_sheet_metadata()
                for s in sheet_info.get('sheets', []):
                    if s['properties']['sheetId'] == sid:
                        for br in s.get('bandedRanges', []):
                            requests.insert(0, {
                                "deleteBanding": {"bandedRangeId": br['bandedRangeId']}
                            })
            except Exception:
                pass

            requests.append({
                "addBanding": {
                    "bandedRange": {
                        "range": {
                            "sheetId": sid,
                            "startRowIndex": 1,
                            "endRowIndex": max_rows,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols,
                        },
                        "rowProperties": {
                            "firstBandColor":  _ROW_ODD,
                            "secondBandColor": _ROW_EVEN,
                        },
                    }
                }
            })

            # ── 7. Column widths ──────────────────────────────
            for col_idx, (_, px_width) in enumerate(COLUMNS):
                requests.append({
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": sid,
                            "dimension": "COLUMNS",
                            "startIndex": col_idx,
                            "endIndex": col_idx + 1,
                        },
                        "properties": {"pixelSize": px_width},
                        "fields": "pixelSize",
                    }
                })

            self._spreadsheet.batch_update({"requests": requests})
            logger.info(f"  Formatting applied to tab: {ws.title}")

        except Exception as e:
            logger.warning(f"  Sheet formatting failed (non-critical): {e}")

    # ── Public API ────────────────────────────────────────────

    def _get_tab_name(self, publication_date: int) -> str:
        return config.PUBLICATION_DATE_TABS.get(publication_date, f'{publication_date} Days')

    def write_property(self, prop: dict, publication_date: int) -> bool:
        """Queue a property row for the next batch flush to its tab.

        Returns True after the row is buffered (or skipped as a duplicate)
        — same external contract as the old per-row implementation, so the
        scraper module sees no change. The actual Google Sheets API call
        happens later, either when the buffer for this tab fills to
        _BATCH_SIZE rows or when the background timer thread observes the
        buffer is older than _BATCH_FLUSH_INTERVAL_SEC.

        Three scraper workers can call this concurrently; per-tab locks +
        the connect lock guarantee no two threads ever fight over the same
        gspread session or batch buffer.
        """
        tab_name = self._get_tab_name(publication_date)
        url = (prop.get('url', '') or '').strip()

        # Cross-session dedup. Has to happen before the row enters the
        # batch buffer so a re-scrape of a property already in the sheet
        # does not produce a duplicate row.
        if url:
            existing = self._tab_urls.get(tab_name)
            if existing is None:
                # First touch on this tab — seed the URL set from the sheet
                # so dedup survives a backend restart mid-run.
                try:
                    self._seed_tab_urls(tab_name)
                    existing = self._tab_urls.get(tab_name, set())
                except Exception as e:
                    logger.debug(f"  Sheets [{tab_name}]: dedup seed failed: {e}")
                    existing = self._tab_urls.setdefault(tab_name, set())
            if url in existing:
                logger.info(f"  Sheets [{tab_name}]: URL already present — skipping duplicate: {url}")
                return True

        images_joined = ', '.join(prop.get('photo_urls', []))
        row = [
            date.today().isoformat(),
            prop.get('url', ''),
            prop.get('address', ''),
            prop.get('listed_since', ''),
            prop.get('days_on_market', '') or '',
            prop.get('asking_price', '') or '',
            # Valuation cells — filled by valuation worker (Walter-free)
            prop.get('woz_value', ''),
            prop.get('suggested_bid', ''),
            '',                                # Bidding Price — EMPTY for user
            prop.get('price_per_m2', '') or '',
            prop.get('living_area', '') or '',
            prop.get('plot_area', '') or '',
            prop.get('rooms', '') or '',
            prop.get('bedrooms', '') or '',
            prop.get('construction_year', '') or '',
            prop.get('property_type', ''),
            prop.get('energielabel', ''),
            prop.get('heating', ''),
            prop.get('insulation', ''),
            prop.get('maintenance_inside', ''),
            prop.get('maintenance_outside', ''),
            prop.get('garden', ''),
            prop.get('garden_orientation', ''),
            prop.get('parking', ''),
            prop.get('vve_contribution', ''),
            prop.get('erfpacht', ''),
            prop.get('acceptance', ''),
            prop.get('description', ''),
            images_joined,
            prop.get('agency_name', ''),
            prop.get('agency_phone', ''),
            prop.get('agency_email', ''),
            prop.get('agency_website', ''),
        ]
        # Reserve the URL immediately so a second worker that scrapes the
        # same property in parallel skips it as a duplicate. If the batch
        # flush ultimately fails we DON'T un-reserve — the property is
        # already in KVK in that case (controller marked it written), and
        # the safer behavior is to surface the loss in logs than to risk a
        # double row on the next scrape.
        if url:
            self._tab_urls.setdefault(tab_name, set()).add(url)

        batch = self._get_batch(tab_name)
        batch.add(row, prop.get('address', prop.get('id', '?')))
        return True

    # ── Batch-write internals ─────────────────────────────────

    def _seed_tab_urls(self, tab_name: str) -> None:
        """Populate _tab_urls[tab_name] from column B of the sheet tab.
        Called on first write to a tab so URLs already in the sheet count
        as duplicates even if this session never wrote them itself."""
        ws = self._get_or_create_worksheet(tab_name)
        col_b = ws.col_values(2)  # Property URL column
        # First row is the header.
        urls = {v.strip() for v in col_b[1:] if v and v.strip()}
        self._tab_urls[tab_name] = urls
        logger.info(f"  Sheets [{tab_name}]: dedup seeded with {len(urls)} URLs")

    def _get_batch(self, tab_name: str) -> "_BatchBuffer":
        """Return (creating if needed) the per-tab batch buffer."""
        with self._batches_lock:
            buf = self._batches.get(tab_name)
            if buf is None:
                ws = self._get_or_create_worksheet(tab_name)
                buf = _BatchBuffer(
                    writer=self,
                    worksheet=ws,
                    tab_name=tab_name,
                    max_size=self._BATCH_SIZE,
                )
                self._batches[tab_name] = buf
            return buf

    def _start_batch_timer(self) -> None:
        """Start the daemon thread that flushes any tab whose buffer is
        older than _BATCH_FLUSH_INTERVAL_SEC. Thread is restartable —
        if a prior call left a thread running, it keeps running."""
        import threading
        if self._batch_timer_thread is not None and self._batch_timer_thread.is_alive():
            return

        def loop():
            while not self._batch_timer_stop.wait(1.0):
                try:
                    with self._batches_lock:
                        items = list(self._batches.values())
                    for b in items:
                        b.maybe_flush_on_timer(self._BATCH_FLUSH_INTERVAL_SEC)
                except Exception as e:
                    logger.warning(f"Sheets batch timer iteration failed: {e}")

        self._batch_timer_thread = threading.Thread(
            target=loop,
            name="sheets-batch-flush",
            daemon=True,
        )
        self._batch_timer_thread.start()

    def flush_all(self) -> None:
        """Drain every per-tab buffer immediately. Called on graceful
        shutdown (atexit) so the last partial batch lands in the sheet."""
        try:
            with self._batches_lock:
                items = list(self._batches.values())
            for b in items:
                try:
                    b.flush()
                except Exception as e:
                    logger.warning(f"Sheets flush_all: tab {b.tab_name} failed: {e}")
        except Exception:
            # Atexit must never raise.
            pass

    def write_properties(self, properties: list, publication_date: int) -> int:
        written = 0
        for prop in properties:
            if self.write_property(prop, publication_date):
                written += 1
        return written

    # ── Valuation back-write ──────────────────────────────────

    # Column letters for the post-Walter, post-Confidence layout (33 cols).
    # G=WOZ, H=Suggested Bid, I=Bidding Price (HUMAN, never written).
    # No Bid Confidence column — confidence still computed for logging only.
    _VAL_COL_WOZ        = 'G'   # 7 — WOZ Value
    _VAL_COL_SUGGESTED  = 'H'   # 8 — Suggested Bid
    _VAL_COL_BIDDING    = 'I'   # 9 — Bidding Price (HUMAN, empty)
    _IDX_WOZ            = 6     # 0-based index for "is this row valued yet?" check
    _IDX_WALTER         = 6     # back-compat alias

    def find_row_by_url(self, url: str) -> Optional[tuple]:
        """Locate a property row across all tabs by its Funda URL (col B).
        Returns (worksheet, row_number) or None.
        """
        self._connect()
        for ws in self._spreadsheet.worksheets():
            try:
                col_b = ws.col_values(2)   # Property URL column
            except Exception:
                continue
            for idx, val in enumerate(col_b, start=1):
                if val and val.strip() == url.strip():
                    return ws, idx
        return None

    def list_pending_valuations(self) -> List[dict]:
        """Return rows where Walter Play-it-Safe (col AF) is empty.
        Each item: {tab, row, url, address, asking_price, days_on_market}.
        """
        self._connect()
        pending: List[dict] = []
        for ws in self._spreadsheet.worksheets():
            try:
                values = ws.get_all_values()
            except Exception as e:
                logger.warning(f"  Could not read {ws.title}: {e}")
                continue
            if len(values) < 2:
                continue
            for row_idx, row in enumerate(values[1:], start=2):
                # Pad row to expected width
                row = row + [''] * (len(HEADERS) - len(row))
                url = row[1]
                if not url:
                    continue
                walter_cell = row[self._IDX_WALTER] if len(row) > self._IDX_WALTER else ''
                if walter_cell.strip():
                    continue   # already valued
                pending.append({
                    'tab':             ws.title,
                    'row':             row_idx,
                    'url':             url,
                    'address':         row[2],
                    'listed_since':    row[3],
                    'days_on_market':  row[4],
                    'asking_price':    row[5],
                    # postcode/house_number not stored in the sheet — the
                    # valuation pass re-derives them from the property page
                    # via Walter (which already needs the full address).
                })
        logger.info(f"Found {len(pending)} pending valuations across all tabs")
        return pending

    def update_valuation_row(self, url: str, valuation: dict, find_retries: int = 3) -> bool:
        """Back-write valuation cells for the row matching `url`.

        Writes only G:H so the human-controlled Bidding Price column (I) is
        NEVER touched:
            G:H → WOZ Value, Suggested Bid
        `valuation` keys: woz_value, suggested_bid.
        (bid_confidence is no longer written to the sheet — kept in logs only.)
        """
        import time
        loc = None
        for attempt in range(1, find_retries + 1):
            loc = self.find_row_by_url(url)
            if loc is not None:
                break
            if attempt < find_retries:
                logger.debug(
                    f"  Valuation back-write: URL not yet visible in sheet "
                    f"(try {attempt}/{find_retries}) — waiting 3s..."
                )
                time.sleep(3)
        if loc is None:
            logger.warning(
                f"  ✗ Valuation back-write: URL still not found in any tab "
                f"after {find_retries} retries: {url}"
            )
            return False
        ws, row_num = loc
        ok = self._batch_update_with_backoff(
            ws,
            [{
                'range':  f'{self._VAL_COL_WOZ}{row_num}:{self._VAL_COL_SUGGESTED}{row_num}',
                'values': [[
                    valuation.get('woz_value', '')      or '',
                    valuation.get('suggested_bid', '')  or '',
                ]],
            }],
            label=f"Valuation [{ws.title} row {row_num}]",
        )
        if ok:
            logger.info(f"  ✓ Valuation written [{ws.title} row {row_num}]: {url}")
        return ok

    def update_bidding_price(self, url: str, bidding_price: str) -> bool:
        """Write the human-entered Bidding Price (col I) for the row matching `url`.

        Isolated from the scraper's valuation flow — this is only ever called
        from the CRM dashboard when a user edits a property's bidding price.
        Returns True on success, False if the URL is not present yet.
        """
        loc = self.find_row_by_url(url)
        if loc is None:
            logger.warning(f"  ✗ Bidding back-write: URL not found in any tab: {url}")
            return False
        ws, row_num = loc
        ok = self._batch_update_with_backoff(
            ws,
            [{
                'range': f'{self._VAL_COL_BIDDING}{row_num}',
                'values': [[bidding_price or '']],
            }],
            label=f"Bidding [{ws.title} row {row_num}]",
        )
        if ok:
            logger.info(f"  ✓ Bidding price written [{ws.title} row {row_num}]: {bidding_price}")
        return ok

    def _batch_update_with_backoff(self, ws, requests: list, label: str) -> bool:
        """Run ws.batch_update with the same retry / backoff policy as
        write_property: 4 attempts with 0/5/15/45s sleeps; on quota errors
        we wait, on other transient errors we force-reconnect and retry.
        """
        import time as _time
        backoff = [0, 5, 15, 45]
        for attempt in range(1, len(backoff) + 1):
            if backoff[attempt - 1] > 0:
                _time.sleep(backoff[attempt - 1])
            try:
                ws.batch_update(requests, value_input_option='USER_ENTERED')
                return True
            except Exception as e:
                msg = str(e).lower()
                is_quota = (
                    '429' in msg
                    or 'quota' in msg
                    or 'rate' in msg
                    or 'resource_exhausted' in msg
                )
                if is_quota and attempt < len(backoff):
                    logger.warning(
                        f"  {label}: quota hit (attempt {attempt}) — backing off {backoff[attempt]}s"
                    )
                    continue
                if attempt < len(backoff):
                    logger.warning(
                        f"  {label}: transient error (attempt {attempt}) — forcing reconnect: {e}"
                    )
                    self._force_reconnect()
                    continue
                logger.error(f"  ✗ {label} failed after {attempt} attempts: {e}")
                return False
        return False

    def clear_all_data_rows(self) -> None:
        """Wipe every data row (row 2 onwards) on every tab — keeps headers.
        Called at the start of a fresh run so each run produces a clean sheet
        with no carry-over from previous runs."""
        self._connect()
        for ws in self._spreadsheet.worksheets():
            try:
                rows = ws.row_count
                cols = ws.col_count
                if rows < 2:
                    continue
                last_col = gspread.utils.rowcol_to_a1(1, cols).rstrip('1')
                ws.batch_clear([f"A2:{last_col}{rows}"])
                logger.info(f"  Cleared data rows on tab: {ws.title}")
            except Exception as e:
                logger.warning(f"  Could not clear tab {ws.title}: {e}")
        # In-memory URL sets are now stale — drop them so fresh writes work.
        self._tab_urls.clear()

    def reformat_all_tabs(self) -> None:
        """Force re-apply formatting to every existing sheet tab."""
        self._connect()
        self._formatted_sheets.clear()
        for ws in self._spreadsheet.worksheets():
            self._apply_sheet_formatting(ws)
            logger.info(f"  Reformatted tab: {ws.title}")

    def get_sheet_url(self) -> str:
        return config.GOOGLE_SHEETS_URL
