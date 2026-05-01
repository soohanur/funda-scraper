"""Recompute valuation cells (Walter / WOZ / Suggested Bid / Confidence /
Reasoning) for every sheet row that already has a Walter price.

  - Walter price is reused from the sheet (no Walter re-query)
  - WOZ is fetched live from the public Kadaster API
  - Bidding Price (col J) is HUMAN-controlled and is never touched

Usage:  python3 scripts/recompute_bids.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from funda.src.modules.sheets_writer import SheetsWriter, HEADERS
from funda.src.modules.valuation_engine import (
    _parse_int, _dom_premium, _regional_factor, _postcode_prefix,
)
from funda.src.modules import woz_client
from funda.src.config import config


def recompute(asking, walter, dom, address):
    dom_mult = _dom_premium(dom)
    reg_mult = _regional_factor(address)
    pfx      = _postcode_prefix(address)

    # WOZ from PDOK + Kadaster (slug → postcode → WOZ)
    woz_val = None
    try:
        resolved = woz_client.find_address_from_slug(address)
        if resolved and resolved.get('postcode') and resolved.get('house_number'):
            woz = woz_client.get_woz_value(
                resolved['postcode'], resolved['house_number'],
            )
            if woz and woz.get('value'):
                woz_val = int(woz['value'])
    except Exception:
        pass

    if asking:
        competitive = int(round(asking * dom_mult * reg_mult))
        floor       = int(round(asking * config.BID_FLOOR_VS_ASKING))
    else:
        competitive = int(round(walter * (1 - config.BID_MIN_MARGIN)))
        floor       = 0

    ceiling = int(round(walter * (1 - config.BID_MIN_MARGIN)))
    final   = min(competitive, ceiling)

    cap_tag = ''
    if competitive > ceiling:
        cap_tag = ' \u26a0 capped by Walter (profit guard)'
    if asking and final < floor:
        cap_tag = ' \u26a0 walter \u2248 asking — bid is profitable but tight'

    woz_warning = ''
    if woz_val and final < woz_val:
        woz_warning = f' \u26a0 below WOZ (\u20ac{woz_val:,})'

    if asking:
        wm = (walter - asking) / asking
        if competitive <= ceiling and wm >= config.BID_MIN_MARGIN:
            confidence = 'HIGH'
        elif ceiling >= floor:
            confidence = 'MEDIUM'
        else:
            confidence = 'LOW'
    else:
        confidence = 'MEDIUM'

    parts = []
    if asking:
        parts.append(f"asking \u20ac{asking:,}")
    if dom is not None:
        parts.append(f"DOM={dom}d \u00d7{dom_mult}")
    parts.append(f"region {pfx} \u00d7{reg_mult}")
    parts.append(f"competitive \u20ac{competitive:,}")
    parts.append(f"Walter \u20ac{walter:,} \u2192 ceiling \u20ac{ceiling:,}")
    if woz_val:
        parts.append(f"WOZ \u20ac{woz_val:,}{woz_warning}")
    parts.append(f"\u2192 bid \u20ac{final:,}{cap_tag}")
    return woz_val, final, confidence, ' | '.join(parts)


sw = SheetsWriter()
sw._connect()

print(f"\n{'='*100}")
print(f"  RECOMPUTE BIDS — new schema (Walter | WOZ | Suggested | [Bidding] | Conf | Reasoning)")
print(f"  competitive = asking \u00d7 DOM \u00d7 region   |   ceiling = walter \u00d7 (1 - {config.BID_MIN_MARGIN})")
print(f"  final = min(competitive, ceiling)   |   floor = asking \u00d7 {config.BID_FLOOR_VS_ASKING}")
print(f"{'='*100}\n")

updated = 0
for ws in sw._spreadsheet.worksheets():
    values = ws.get_all_values()
    if len(values) < 2:
        continue
    for row_idx, row in enumerate(values[1:], start=2):
        row = row + [''] * (len(HEADERS) - len(row))
        url     = row[1]
        address = row[2]
        asking  = _parse_int(row[5])
        dom     = _parse_int(row[4])
        walter  = _parse_int(row[6])   # col G
        if not url or not walter:
            continue

        woz_val, bid, conf, reasoning = recompute(asking, walter, dom, address)

        # Two writes — leave col J (Bidding Price) alone
        ws.batch_update([
            {'range': f'H{row_idx}:I{row_idx}',
             'values': [[woz_val or '', bid]]},
            {'range': f'K{row_idx}:L{row_idx}',
             'values': [[conf, reasoning]]},
        ], value_input_option='USER_ENTERED')

        updated += 1
        old_bid = row[8]   # old col I (was Suggested Bid post-prev-migration; now it's still I)
        print(f"  [{ws.title} row {row_idx}] {address[:40]:40s}")
        print(f"    asking={asking}  walter={walter}  WOZ={woz_val}  DOM={dom}")
        print(f"    bid: \u20ac{bid:,}   ({conf})")
        print(f"    {reasoning}\n")

print(f"\nUpdated {updated} row(s).\n")
