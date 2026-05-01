"""One-shot migration: bring every sheet tab to the latest column layout.

The schema has evolved through 3 versions:
  V1 (35 cols): ... Asking, Bidding (calc), Price/m², ..., Walter, Suggested, Conf, Reason
  V2 (34 cols): ... Asking, Walter, Suggested, Conf, Reason, Price/m², ...
  V3 (36 cols): ... Asking, Walter, WOZ, Suggested, BiddingPrice (human), Conf, Reason, Price/m², ...

This script auto-detects the current layout and remaps to V3.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from funda.src.modules.sheets_writer import SheetsWriter, HEADERS

# Position-keyed maps for each historical layout
V1_KEYS = [
    'scrape_date', 'url', 'address', 'listed_since', 'days_on_market',
    'asking_price', 'bidding_calc', 'price_per_m2', 'living_area', 'plot_area',
    'rooms', 'bedrooms', 'construction_year', 'property_type', 'energielabel',
    'heating', 'insulation', 'maintenance_inside', 'maintenance_outside',
    'garden', 'garden_orientation', 'parking', 'vve', 'erfpacht', 'acceptance',
    'description', 'images', 'agency_name', 'agency_phone', 'agency_email',
    'agency_website', 'walter', 'suggested_bid', 'confidence', 'reasoning',
]
V2_KEYS = [
    'scrape_date', 'url', 'address', 'listed_since', 'days_on_market',
    'asking_price',
    'walter', 'suggested_bid', 'confidence', 'reasoning',
    'price_per_m2', 'living_area', 'plot_area',
    'rooms', 'bedrooms', 'construction_year', 'property_type', 'energielabel',
    'heating', 'insulation', 'maintenance_inside', 'maintenance_outside',
    'garden', 'garden_orientation', 'parking', 'vve', 'erfpacht', 'acceptance',
    'description', 'images', 'agency_name', 'agency_phone', 'agency_email',
    'agency_website',
]
V3_KEYS = [   # current target — must align with sheets_writer.COLUMNS
    'scrape_date', 'url', 'address', 'listed_since', 'days_on_market',
    'asking_price',
    'walter', 'woz', 'suggested_bid', 'bidding_price_human', 'confidence', 'reasoning',
    'price_per_m2', 'living_area', 'plot_area',
    'rooms', 'bedrooms', 'construction_year', 'property_type', 'energielabel',
    'heating', 'insulation', 'maintenance_inside', 'maintenance_outside',
    'garden', 'garden_orientation', 'parking', 'vve', 'erfpacht', 'acceptance',
    'description', 'images', 'agency_name', 'agency_phone', 'agency_email',
    'agency_website',
]

assert len(V3_KEYS) == len(HEADERS), (len(V3_KEYS), len(HEADERS))


def detect_version(header):
    n = len(header)
    if n == 36 and 'WOZ Value' in ' '.join(header):
        return 'V3'
    if n == 34:
        return 'V2'
    if n == 35:
        return 'V1'
    if n == 0:
        return 'EMPTY'
    return f'UNKNOWN({n})'


def remap(old_row, src_keys):
    padded = old_row + [''] * (len(src_keys) - len(old_row))
    rec = {src_keys[i]: padded[i] for i in range(len(src_keys))}
    return [rec.get(k, '') for k in V3_KEYS]


sw = SheetsWriter()
sw._connect()

for ws in sw._spreadsheet.worksheets():
    values = ws.get_all_values()
    header = values[0] if values else []
    data   = values[1:] if values else []
    n_data = len([r for r in data if any(c.strip() for c in r)])
    ver = detect_version(header)
    print(f"\n  [{ws.title}] schema={ver}  data rows={n_data}")

    if ver == 'V3':
        print('    already V3 — skip')
        continue

    src = {'V1': V1_KEYS, 'V2': V2_KEYS, 'EMPTY': V3_KEYS}.get(ver)
    if src is None:
        print(f'    unknown layout — manual review needed')
        continue

    new_rows = [remap(r, src) for r in data if any(c.strip() for c in r)] if data else []

    ws.clear()
    ws.update(values=[HEADERS] + new_rows, range_name='A1',
              value_input_option='USER_ENTERED')
    try:
        ws.resize(rows=max(2000, len(new_rows) + 10), cols=len(HEADERS))
    except Exception:
        pass
    sw._formatted_sheets.discard(ws.title)
    sw._apply_sheet_formatting(ws)
    print(f"    migrated {ver} → V3 ({len(new_rows)} rows, {len(HEADERS)} cols)")

print('\nDONE.')
