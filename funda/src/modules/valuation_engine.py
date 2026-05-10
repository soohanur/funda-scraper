"""
Valuation Engine — Walter-free, distribution-based bidding model.

The model is reverse-engineered from 324 historical successful deals.
Inputs: asking price, WOZ value (proxy for market value), days on market,
city, postcode/house number for WOZ lookup.

Pipeline per property:

  1. Estimate market value (MV)
       - if WOZ available: MV ≈ WOZ × WOZ_TO_MV_UPLIFT (NL avg ~+8%)
       - else fallback:    MV ≈ asking × ASK_TO_MV_DEFAULT (~+2.5%)

  2. Classify into segments
       - ask_band     : <200k | 200-300k | 300-400k | 400-600k | >600k
       - mv_spread    : (mv - asking) / asking
       - spread_band  : overpriced | fair | underpriced | badly_underpriced
       - dom_band     : fresh<=14 | normal15-30 | cooling31-60 | stale>60

  3. Lookup conditional discount distribution from DISCOUNT_TABLE:
       returns (P25, P50, P75) of historical discount % for that segment

  4. Pick a recommendation pointer using DOM:
       - DOM ≤ 14 → use P75 (aggressive — fresh listings give biggest margin)
       - DOM 15-60 → use P50 (balanced — default)
       - DOM > 60 → use P25 (conservative — seller likely already trimmed)

  5. Compute bid:  bid = round(asking × (1 - discount/100))

  6. Apply hard guardrails:
       - bid ≤ MV × MV_GUARD (never within MV_GUARD of estimated MV)
       - bid ≥ asking × MIN_RATIO_TO_ASK (never insultingly low)

  7. Lookup risk profile from RISK_TABLE → confidence label:
       - P(margin <5%) ≥ 30%        → SKIP
       - P(margin ≥20%) ≥ 50%       → HIGH
       - P(margin ≥20%) ≥ 25%       → MEDIUM
       - else                        → LOW

Returns: woz_value, suggested_bid, bid_confidence (no Walter price).
The "Bidding Price" column on the sheet stays empty — that's for the user.
"""
import re
from typing import Optional, Dict
from dataclasses import dataclass, field

from ..config import config
from ..utils.logger import setup_logger
from . import woz_client

logger = setup_logger('funda.valuation')


# ─────────────────────────────────────────────────────────────────
# MV estimation knobs
# ─────────────────────────────────────────────────────────────────
WOZ_TO_MV_UPLIFT     = 1.08   # WOZ is ~5-15% below MV in rising markets; 8% is conservative
ASK_TO_MV_DEFAULT    = 1.025  # historical median MV/Ask ratio when WOZ missing
MV_GUARD             = 0.92   # bid never within 8% of MV
MIN_RATIO_TO_ASK     = 0.55   # bid never below 55% of asking (insulting)


# ─────────────────────────────────────────────────────────────────
# DISCOUNT_TABLE — derived from 324 historical winning deals.
# Format: DISCOUNT_TABLE[ask_band][spread_band] = (P25, P50, P75)
# Discount values are PERCENTAGES below asking price.
# ─────────────────────────────────────────────────────────────────
DISCOUNT_TABLE = {
    '<200k': {
        'overpriced':        (14.01, 17.76, 23.31),
        'fair':              (11.61, 14.91, 20.53),
        'underpriced':       (12.37, 16.32, 20.44),
        'badly_underpriced': (13.81, 19.58, 25.50),
    },
    '200-300k': {
        'overpriced':        (8.78, 16.00, 25.00),
        'fair':              (10.56, 13.21, 19.68),
        'underpriced':       (7.95, 11.11, 15.56),
        'badly_underpriced': (6.22, 11.32, 16.00),
    },
    '300-400k': {
        'overpriced':        (9.80, 18.55, 20.00),
        'fair':              (6.56, 11.73, 16.35),
        'underpriced':       (6.67, 9.33, 13.33),
        'badly_underpriced': (4.17, 8.00, 12.70),
    },
    '400-600k': {
        'overpriced':        (9.79, 14.79, 17.94),
        'fair':              (6.25, 9.24, 12.50),
        'underpriced':       (6.90, 8.24, 10.59),
        'badly_underpriced': (1.65, 6.25, 7.06),
    },
    '>600k': {
        'overpriced':        (11.62, 11.73, 14.49),
        'fair':              (7.98, 13.20, 15.56),
        'underpriced':       (7.98, 13.20, 15.56),   # reuse fair (low n in this segment)
        'badly_underpriced': (7.98, 13.20, 15.56),
    },
}

# RISK_TABLE[ask_band][spread_band] = (P_loss, P_thin, P_good)
# P_loss = % of historical deals with margin < 5%
# P_thin = % of historical deals with margin < 10%
# P_good = % of historical deals with margin >= 20%
RISK_TABLE = {
    '<200k': {
        'overpriced':        (25.0, 50.0, 25.0),
        'fair':              (8.7, 21.7, 39.1),
        'underpriced':       (0.0, 0.0, 70.0),
        'badly_underpriced': (0.0, 0.0, 83.3),
    },
    '200-300k': {
        'overpriced':        (42.9, 42.9, 28.6),
        'fair':              (9.1, 27.3, 33.3),
        'underpriced':       (2.8, 16.7, 44.4),
        'badly_underpriced': (3.0, 3.0, 81.8),
    },
    '300-400k': {
        'overpriced':        (40.0, 60.0, 20.0),
        'fair':              (23.5, 38.2, 26.5),
        'underpriced':       (11.9, 21.4, 35.7),
        'badly_underpriced': (0.0, 0.0, 76.5),
    },
    '400-600k': {
        'overpriced':        (50.0, 50.0, 0.0),
        'fair':              (20.7, 55.2, 13.8),
        'underpriced':       (0.0, 9.5, 14.3),
        'badly_underpriced': (0.0, 0.0, 20.0),
    },
    '>600k': {
        'overpriced':        (0.0, 66.7, 0.0),
        'fair':              (12.5, 37.5, 25.0),
        'underpriced':       (12.5, 37.5, 25.0),
        'badly_underpriced': (12.5, 37.5, 25.0),
    },
}

# Confidence-decision thresholds (apply on RISK_TABLE values)
SKIP_IF_LOSS_PROB_GE  = 30.0   # P(margin <5%) >= 30% → SKIP
HIGH_IF_GOOD_PROB_GE  = 50.0   # P(margin >=20%) >= 50% → HIGH
MED_IF_GOOD_PROB_GE   = 25.0


# ─────────────────────────────────────────────────────────────────
# Helpers — input parsing + segment classification
# ─────────────────────────────────────────────────────────────────

def _parse_int(v) -> Optional[int]:
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v)
    digits = re.sub(r'[^\d]', '', s.split(',')[0])
    return int(digits) if digits else None


def _ask_band(asking: int) -> str:
    if asking < 200_000: return '<200k'
    if asking < 300_000: return '200-300k'
    if asking < 400_000: return '300-400k'
    if asking < 600_000: return '400-600k'
    return '>600k'


def _spread_band(spread_pct: float) -> str:
    if spread_pct < -5:  return 'overpriced'
    if spread_pct <  2:  return 'fair'
    if spread_pct < 10:  return 'underpriced'
    return 'badly_underpriced'


def _dom_pointer(dom: Optional[int]) -> str:
    """Pick which percentile to use based on days on market."""
    if dom is None:        return 'balanced'   # P50 default
    if dom <= 14:          return 'aggressive' # P75
    if dom > 60:           return 'conservative' # P25
    return 'balanced'


# ─────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────

@dataclass
class ValuationResult:
    woz_value: Optional[int] = None
    suggested_bid: Optional[int] = None
    confidence: str = 'NONE'           # HIGH | MEDIUM | LOW | SKIP | NONE
    reasoning: str = ''                # log-only
    components: Dict = field(default_factory=dict)

    def as_sheet_dict(self) -> Dict:
        """Flatten for sheets_writer back-write.
        Returns the 2 cells we write (G + H). Bidding Price (col I) stays
        empty for the user. Confidence stays on the dataclass for logging
        but is not written to the sheet anymore.
        """
        return {
            'woz_value':       self.woz_value or '',
            'suggested_bid':   self.suggested_bid or '',
        }


# ─────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────

class ValuationEngine:
    """Stateless, fast valuation. No external service calls except WOZ.
    Each property's valuation finishes in <100ms (just lookups + math).
    Walter Living dependency removed entirely.
    """

    def __init__(self, walter=None):
        # `walter` accepted for backward-compat with controller signature; ignored.
        pass

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── Main API ──────────────────────────────────────────────

    def value_property(self, prop: Dict) -> ValuationResult:
        """Compute suggested bid using the distribution-based model.
        Never raises — returns a ValuationResult with confidence='NONE' on
        unrecoverable input errors.
        """
        result = ValuationResult()
        address = prop.get('address') or ''
        asking  = _parse_int(prop.get('asking_price'))
        dom     = _parse_int(prop.get('days_on_market'))

        if not address or not asking:
            result.reasoning = 'Missing address or asking price — cannot value'
            return result

        # ── 1. WOZ lookup ───────────────────────────────────
        woz_val: Optional[int] = None
        pc = (prop.get('postcode') or '').strip()
        hn = str(prop.get('house_number') or '').strip()
        ha = str(prop.get('house_addition') or '').strip()
        if not (pc and hn):
            try:
                resolved = woz_client.find_address_from_slug(address)
                if resolved:
                    pc = pc or resolved.get('postcode', '')
                    hn = hn or resolved.get('house_number', '')
            except Exception as e:
                logger.debug(f"slug→postcode lookup failed for {address!r}: {e}")
        if pc and hn:
            try:
                woz = woz_client.get_woz_value(pc, hn, ha)
                if woz and woz.get('value'):
                    woz_val = int(woz['value'])
                    result.woz_value = woz_val
                    logger.info(f"  WOZ €{woz_val:,} ({woz.get('peildatum','')})")
            except Exception as e:
                logger.debug(f"WOZ lookup failed for {pc} {hn}: {e}")

        # ── 2. Estimate market value ─────────────────────────
        if woz_val:
            mv_estimate = int(woz_val * WOZ_TO_MV_UPLIFT)
            mv_source = 'WOZ'
        else:
            mv_estimate = int(asking * ASK_TO_MV_DEFAULT)
            mv_source = 'asking'

        # ── 3. Classify segment ──────────────────────────────
        ab = _ask_band(asking)
        spread_pct = (mv_estimate - asking) / asking * 100
        sb = _spread_band(spread_pct)

        # ── 4. Lookup discount distribution ──────────────────
        p25, p50, p75 = DISCOUNT_TABLE[ab][sb]
        pointer = _dom_pointer(dom)
        if   pointer == 'aggressive':   discount = p75
        elif pointer == 'conservative': discount = p25
        else:                           discount = p50

        # ── 5. Compute bid ───────────────────────────────────
        bid = int(round(asking * (1 - discount / 100)))

        # ── 6. Hard guardrails ───────────────────────────────
        bid_before_guards = bid
        guard_notes = []
        ceiling = int(mv_estimate * MV_GUARD)
        floor = int(asking * MIN_RATIO_TO_ASK)
        if bid > ceiling:
            bid = ceiling
            guard_notes.append(f'capped by MV-guard (≤ MV×{MV_GUARD})')
        if bid < floor:
            bid = floor
            guard_notes.append(f'floored at asking×{MIN_RATIO_TO_ASK}')

        # ── 7. Risk-based confidence ─────────────────────────
        p_loss, p_thin, p_good = RISK_TABLE[ab][sb]
        if p_loss >= SKIP_IF_LOSS_PROB_GE:
            confidence = 'SKIP'
        elif p_good >= HIGH_IF_GOOD_PROB_GE:
            confidence = 'HIGH'
        elif p_good >= MED_IF_GOOD_PROB_GE:
            confidence = 'MEDIUM'
        else:
            confidence = 'LOW'

        result.suggested_bid = bid
        result.confidence = confidence

        result.components = {
            'asking':         asking,
            'mv_estimate':    mv_estimate,
            'mv_source':      mv_source,
            'ask_band':       ab,
            'spread_pct':     round(spread_pct, 2),
            'spread_band':    sb,
            'dom':            dom,
            'pointer':        pointer,
            'discount_p25':   p25,
            'discount_p50':   p50,
            'discount_p75':   p75,
            'discount_used':  discount,
            'risk_loss':      p_loss,
            'risk_good':      p_good,
            'bid_pre_guard':  bid_before_guards,
            'guard_notes':    guard_notes,
        }

        parts = [
            f'asking €{asking:,}',
            f'MV(est)=€{mv_estimate:,}({mv_source})',
            f'band={ab}/{sb}',
            f'DOM={dom}d→{pointer}',
            f'disc={discount:.2f}%',
            f'bid €{bid:,}',
            f'risk_loss={p_loss:.0f}% risk_good={p_good:.0f}%',
            f'conf={confidence}',
        ]
        if guard_notes:
            parts.append('|'.join(guard_notes))
        result.reasoning = ' | '.join(parts)
        logger.info(f"  Valuation [{address}]: {result.reasoning}")
        return result
