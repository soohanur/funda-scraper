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
    ('Walter Play-it-Safe (\u20ac)', 150),
    ('WOZ Value (\u20ac)',           120),
    ('Suggested Bid (\u20ac)',       130),
    ('Bid Confidence',                110),
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


class SheetsWriter:
    """Writes property data to Google Sheets in real-time."""

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        spreadsheet_id: Optional[str] = None,
    ):
        self.credentials_path = credentials_path or config.GOOGLE_SHEETS_CREDENTIALS
        self.spreadsheet_id   = spreadsheet_id   or config.GOOGLE_SHEETS_SPREADSHEET_ID
        self._client: Optional[gspread.Client]       = None
        self._spreadsheet: Optional[gspread.Spreadsheet] = None
        self._formatted_sheets: Set[str] = set()   # track formatted tabs this session

    # ── Connection ────────────────────────────────────────────

    def _connect(self) -> None:
        if self._client is not None:
            return
        creds = Credentials.from_service_account_file(
            self.credentials_path, scopes=SCOPES,
        )
        self._client       = gspread.authorize(creds)
        self._spreadsheet  = self._client.open_by_key(self.spreadsheet_id)
        logger.info(f"Connected to Google Sheets: {self._spreadsheet.title}")

    # ── Worksheet setup ───────────────────────────────────────

    def _get_or_create_worksheet(self, tab_name: str) -> gspread.Worksheet:
        """Get existing worksheet or create it, then ensure headers + formatting."""
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
        """Write a single property row to the correct sheet tab."""
        tab_name = self._get_tab_name(publication_date)
        try:
            ws = self._get_or_create_worksheet(tab_name)

            images_joined = ', '.join(prop.get('photo_urls', []))

            row = [
                date.today().isoformat(),
                prop.get('url', ''),
                prop.get('address', ''),
                prop.get('listed_since', ''),
                prop.get('days_on_market', '') or '',
                prop.get('asking_price', '') or '',
                # Valuation cells — filled by Walter worker thread in parallel
                prop.get('walter_play_it_safe', ''),
                prop.get('woz_value', ''),
                prop.get('suggested_bid', ''),
                prop.get('bid_confidence', ''),
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

            ws.append_row(row, value_input_option='USER_ENTERED')
            logger.info(
                f"  ✓ Sheets [{tab_name}]: {prop.get('address', prop.get('id', '?'))}"
            )
            return True

        except Exception as e:
            logger.error(f"  ✗ Sheets write failed: {e}")
            return False

    def write_properties(self, properties: list, publication_date: int) -> int:
        written = 0
        for prop in properties:
            if self.write_property(prop, publication_date):
                written += 1
        return written

    # ── Valuation back-write ──────────────────────────────────

    # Column letters for the 4 machine-written valuation cells.
    # New 34-col layout: no Bidding Price column, no Reasoning column.
    _VAL_COL_WALTER     = 'G'   # 7  — Walter Play-it-Safe
    _VAL_COL_WOZ        = 'H'   # 8  — WOZ Value
    _VAL_COL_SUGGESTED  = 'I'   # 9  — Suggested Bid
    _VAL_COL_CONFIDENCE = 'J'   # 10 — Bid Confidence
    _IDX_WALTER         = 6     # 0-based index in a row list

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

        Writes a single contiguous G:J range:
            G → Walter Play-it-Safe
            H → WOZ Value
            I → Suggested Bid
            J → Bid Confidence
        `valuation` keys: walter_play_it_safe, woz_value, suggested_bid,
                          bid_confidence.

        Retries find_row_by_url up to `find_retries` times with 3s backoff —
        the sheet API has eventual consistency and a freshly-written row may
        not show up in `col_values()` for a few seconds.
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
        try:
            ws.batch_update([{
                'range':  f'{self._VAL_COL_WALTER}{row_num}:{self._VAL_COL_CONFIDENCE}{row_num}',
                'values': [[
                    valuation.get('walter_play_it_safe', '') or '',
                    valuation.get('woz_value', '')           or '',
                    valuation.get('suggested_bid', '')       or '',
                    valuation.get('bid_confidence', '')      or '',
                ]],
            }], value_input_option='USER_ENTERED')
            logger.info(f"  ✓ Valuation written [{ws.title} row {row_num}]: {url}")
            return True
        except Exception as e:
            logger.error(f"  ✗ Valuation update failed [{ws.title} row {row_num}]: {e}")
            return False

    def reformat_all_tabs(self) -> None:
        """Force re-apply formatting to every existing sheet tab."""
        self._connect()
        self._formatted_sheets.clear()
        for ws in self._spreadsheet.worksheets():
            self._apply_sheet_formatting(ws)
            logger.info(f"  Reformatted tab: {ws.title}")

    def get_sheet_url(self) -> str:
        return config.GOOGLE_SHEETS_URL
