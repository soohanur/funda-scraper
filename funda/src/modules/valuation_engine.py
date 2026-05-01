"""
Valuation Engine — Walter-only ceiling, fixed discount X ∈ [0%, 3%]

Bid model:
    suggested_bid = round(walter_price × (1 − X))

X is a discount in [0, 3%], composed of three independent parts:

    X = DOM_part + region_part + spread_part           (clamped to [0, 0.03])

  DOM_part           — how stale the listing is (max 1.5%)
    ≤ 7 days   → 0.0%
    8–14 days  → 0.5%
    15–30 days → 1.0%
    31–60 days → 1.3%
    > 60 days  → 1.5%

  region_part        — postcode prefix heat (max 1.0%)
    10/11/12/20/30/31/35  → 0.0%   (Amsterdam / Rotterdam / Utrecht — hot)
    21/25/26              → 0.5%   (Haarlem / Den Haag — warm)
    anything else         → 1.0%

  spread_part        — Walter-vs-asking headroom (max 0.5%)
    spread ≤ 5%   → 0.0%
    5–15%         → 0.25%
    > 15%         → 0.5%
    asking missing OR walter ≤ asking → 0%

Fallback path (only when Walter genuinely returns reason='no_data'):
    The same X formula is applied to `asking` instead of Walter:
        suggested_bid = round(asking × (1 − X))
        spread_part = 0 (Walter is unavailable)
    Walter Play-it-Safe stays empty in the sheet.
    Bid Confidence = 'FALLBACK' (clearly distinct from HIGH/MEDIUM/LOW).

Walter retry policy (handled here, not in the controller):
    captcha / no_chat / login_failed / send_failed / parse_failed
                 → close Walter, sleep 60s, restart, retry the same address
                   once. If the retry also fails: behave per reason as below.
    captcha (2nd time)        → fall back via asking-based formula
                                (so the queue keeps moving even if Walter is
                                 blocked — flagged with 'FALLBACK' confidence)
    timeout / error           → skip property (NONE confidence)
    no_data                   → asking-based fallback formula immediately
"""
import re
import time
from typing import Optional, Dict
from dataclasses import dataclass, field

from ..config import config
from ..utils.logger import setup_logger
from .walter_client import (
    WalterClient,
    REASON_OK, REASON_NO_DATA, REASON_CAPTCHA, REASON_NO_CHAT,
    REASON_LOGIN_FAILED, REASON_TIMEOUT, REASON_SEND_FAILED,
    REASON_PARSE_FAILED, REASON_ERROR,
)
from . import woz_client

logger = setup_logger('funda.valuation')


# ─────────────────────────────────────────────────────────────────
# Tunables
# ─────────────────────────────────────────────────────────────────
MAX_DISCOUNT = 0.03         # cap X at 3%

# DOM bands — (upper bound days inclusive, discount fraction)
_DOM_TIERS = [
    (7,    0.0000),
    (14,   0.0050),
    (30,   0.0100),
    (60,   0.0130),
    (10**9, 0.0150),
]

# Postcode-prefix region tiers
_HOT_REGIONS  = {'10', '11', '12', '20', '30', '31', '35'}
_WARM_REGIONS = {'21', '25', '26'}

# Walter-vs-asking spread bands — (upper bound spread fraction, discount fraction)
_SPREAD_TIERS = [
    (0.05,   0.0000),
    (0.15,   0.0025),
    (10.0,   0.0050),
]

# Walter retry behaviour. REASON_ERROR is included because most "errors" we
# see in practice are PageDisconnectedError / ChromeDriver crashes, which a
# fresh browser session (close + restart) reliably resolves. REASON_TIMEOUT
# is included because hung sessions are usually freed by a browser restart.
_WALTER_RECOVERABLE = {
    REASON_CAPTCHA, REASON_NO_CHAT, REASON_LOGIN_FAILED,
    REASON_SEND_FAILED, REASON_PARSE_FAILED, REASON_ERROR,
    REASON_TIMEOUT,
}
_WALTER_RETRY_SLEEP_SEC = 60   # cooldown before retrying after captcha/etc

# Politeness delay between consecutive Walter queries. Walter Living's chat is
# LLM-backed and rate-limits aggressive use. We use a JITTERED range so we
# don't look like a periodic bot.
_WALTER_DELAY_MIN_SEC = 8
_WALTER_DELAY_MAX_SEC = 25
_WALTER_PRESEND_MIN_SEC = 1.0     # extra random pause right before sending prompt
_WALTER_PRESEND_MAX_SEC = 3.0

# 4-tier escalation when Walter keeps failing.
# Tier 1: per-call retry (close+restart browser, 60s sleep, retry once)
_WALTER_TIER1_RETRY_SLEEP = 60

# Tier 2: 3 consecutive fails → DEEP RECOVERY
#   kill Walter chrome, wipe profile, rotate profile dir, fresh fingerprint,
#   sleep 5 min, fresh login.
_WALTER_TIER2_FAILS = 3
_WALTER_TIER2_SLEEP = 300         # 5 minutes

# Tier 3: 6 consecutive fails → LONG RECOVERY (deep + 30 min cooldown)
_WALTER_TIER3_FAILS = 6
_WALTER_TIER3_SLEEP = 1800        # 30 minutes

# Tier 4: 10 consecutive fails → FLAG WALTER DEAD for the rest of session.
#   Every subsequent property goes straight to fallback formula — no more
#   wasted timeouts. The flag is reset only when a new ValuationEngine is
#   created (next session).
_WALTER_TIER4_FAILS = 10


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _parse_int(v) -> Optional[int]:
    """Parse an int from messy values: '€450.000', '450000', '€ 1.250.000', etc."""
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v)
    digits = re.sub(r'[^\d]', '', s.split(',')[0])
    return int(digits) if digits else None


def _postcode_prefix(prop: Dict) -> str:
    """Extract first 2 digits of NL postcode from property dict."""
    pc = (prop.get('postcode') or '').strip().upper()
    if pc:
        m = re.match(r'^(\d{4})', pc)
        if m:
            return m.group(1)[:2]
    addr = prop.get('address') or ''
    m = re.search(r'\b(\d{4})\s*[A-Z]{2}\b', addr.upper())
    return m.group(1)[:2] if m else 'default'


def _dom_discount(days_on_market: Optional[int]) -> float:
    if days_on_market is None or days_on_market < 0:
        return 0.0
    for upper, disc in _DOM_TIERS:
        if days_on_market <= upper:
            return disc
    return 0.0


def _region_discount(prefix: str) -> float:
    if prefix in _HOT_REGIONS:
        return 0.0
    if prefix in _WARM_REGIONS:
        return 0.0050
    return 0.0100


def _spread_discount(walter: Optional[int], asking: Optional[int]) -> tuple:
    """Return (discount, spread_fraction). Spread = (walter-asking)/asking.
    When walter is None (fallback path), returns (0.0, 0.0)."""
    if not walter or not asking or walter <= asking:
        return 0.0, 0.0
    spread = (walter - asking) / asking
    for upper, disc in _SPREAD_TIERS:
        if spread <= upper:
            return disc, spread
    return 0.0, spread


def _compute_x(walter: Optional[int], asking: Optional[int],
               dom: Optional[int], prefix: str) -> tuple:
    """Compute total discount X and the three component values."""
    dd = _dom_discount(dom)
    rd = _region_discount(prefix)
    sd, spread = _spread_discount(walter, asking)
    x = max(0.0, min(MAX_DISCOUNT, dd + rd + sd))
    return x, dd, rd, sd, spread


# ─────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────

@dataclass
class ValuationResult:
    walter_price: Optional[int] = None
    woz_value: Optional[int] = None
    suggested_bid: Optional[int] = None
    confidence: str = 'NONE'           # HIGH | MEDIUM | LOW | FALLBACK | NONE
    reasoning: str = ''                # log-only, NOT written to sheet
    walter_reason: str = REASON_ERROR  # REASON_OK | REASON_NO_DATA | ...
    components: Dict = field(default_factory=dict)

    def as_sheet_dict(self) -> Dict:
        """Flatten for sheets_writer back-write (4 cells: G:J)."""
        return {
            'walter_play_it_safe': self.walter_price or '',
            'woz_value':           self.woz_value    or '',
            'suggested_bid':       self.suggested_bid or '',
            'bid_confidence':      self.confidence,
        }


# ─────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────

class ValuationEngine:
    """Stateful engine — holds one WalterClient across many properties.
    Handles Walter retries and falls back to asking-based formula when
    Walter genuinely has no price (no_data) or remains blocked after retry.
    """

    def __init__(self, walter: Optional[WalterClient] = None):
        self._walter = walter
        self._owns_walter = walter is None
        # Throttle bookkeeping
        self._last_walter_call_ts: float = 0.0       # when last query started
        self._consecutive_walter_fails: int = 0      # since last success OR last tier
        # Monotonic tier level: 0 = no recovery yet, 1 = tier-2 fired,
        # 2 = tier-3 fired, 3 = DEAD (tier-4). Only ascends, never resets
        # except on a real Walter success.
        self._walter_tier_level: int = 0
        self._walter_dead: bool = False              # Tier-4: skip Walter entirely

    def _get_walter(self) -> WalterClient:
        if self._walter is None:
            self._walter = WalterClient(
                email=config.WALTER_EMAIL,
                password=config.WALTER_PASSWORD,
                profile_path=config.WALTER_PROFILE_PATH,
                headless=config.WALTER_HEADLESS,
                port=config.WALTER_PORT,
                response_timeout=config.WALTER_RESPONSE_TIMEOUT,
            )
        return self._walter

    def _restart_walter(self) -> None:
        """Close the Walter session and let next call re-init it. Called on
        captcha/login failure to start a clean session."""
        if self._walter is None:
            return
        try:
            self._walter.restart_browser()
        except Exception:
            pass
        # Force re-init on next access
        if self._owns_walter:
            self._walter = None
        # If we don't own Walter, the caller is responsible for the restart;
        # we still rely on its lazy-init behaviour to reopen.

    def close(self) -> None:
        if self._owns_walter and self._walter is not None:
            self._walter.close()
            self._walter = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── Walter call with retry ─────────────────────────────────

    def _query_walter_with_retry(self, address: str) -> Dict:
        """Query Walter with 4-tier escalation + jittered politeness.

        Tiers (each fires when consecutive_walter_fails crosses the threshold,
        BEFORE the next per-call retry to avoid burning quick retries that
        will also fail):

          - Tier 1 (always)  : per-call restart + 60s sleep + retry once
          - Tier 2 (3 fails) : DEEP recovery — kill chrome, wipe profile,
                                rotate profile path, fresh fingerprint, sleep
                                5 min, fresh login.
          - Tier 3 (6 fails) : repeat deep recovery + sleep 30 min.
          - Tier 4 (10 fails): flag Walter DEAD for rest of session — every
                                subsequent property gets fallback formula
                                immediately, no Walter call at all.

        Returns the WalterClient dict either from the successful call or the
        last attempt's failure dict.
        """
        import random as _r

        # Tier 4 hard skip — Walter is permanently broken for this session
        if self._walter_dead:
            return {
                'price': None,
                'reason': REASON_ERROR,
                'message': 'Walter flagged dead for this session (tier 4)',
                'raw_text': '',
                'currency': 'EUR',
            }

        # ── Politeness delay (jittered) ──────────────────────────
        now = time.time()
        elapsed = now - self._last_walter_call_ts
        target_delay = _r.uniform(_WALTER_DELAY_MIN_SEC, _WALTER_DELAY_MAX_SEC)
        if self._last_walter_call_ts and elapsed < target_delay:
            wait = target_delay - elapsed
            logger.debug(f"  Walter politeness wait: {wait:.1f}s")
            time.sleep(wait)
        # Tiny pre-send randomness on top
        time.sleep(_r.uniform(_WALTER_PRESEND_MIN_SEC, _WALTER_PRESEND_MAX_SEC))
        self._last_walter_call_ts = time.time()

        first = self._get_walter().get_play_it_safe_bid(address)
        if first.get('reason') == REASON_OK:
            # Real success → reset both counters, drop tier level back to 0
            self._consecutive_walter_fails = 0
            self._walter_tier_level = 0
            return first

        # ── Tier escalation BEFORE per-call retry ───────────────
        # Monotonic: tier_level only ascends. Each tier fires when
        # consec_fails reaches the threshold for the NEXT tier from current level.
        #
        #   level 0 (no recovery yet)  →  3 fails  →  tier-2 (5 min)
        #   level 1 (tier-2 done)      →  3 fails  →  tier-3 (30 min)
        #   level 2 (tier-3 done)      →  1 fail   →  tier-4 DEAD
        if self._walter_tier_level == 2 and self._consecutive_walter_fails >= 1:
            logger.error(
                f"Walter Tier-4 reached: tier-3 deep recovery + 30min cooldown "
                f"didn't restore Walter (still failing). Flagging Walter DEAD "
                f"for rest of session — all remaining properties will use "
                f"fallback formula."
            )
            self._walter_dead = True
            self._walter_tier_level = 3
            return first   # caller writes fallback bid

        if self._walter_tier_level == 1 and self._consecutive_walter_fails >= _WALTER_TIER2_FAILS:
            logger.warning(
                f"Walter Tier-3: tier-2 didn't recover Walter ({self._consecutive_walter_fails} "
                f"more failures since tier-2 cooldown). Escalating: DEEP RECOVERY "
                f"+ sleeping {_WALTER_TIER3_SLEEP}s ({_WALTER_TIER3_SLEEP//60} min)"
            )
            self._get_walter().deep_recovery_restart()
            time.sleep(_WALTER_TIER3_SLEEP)
            self._consecutive_walter_fails = 0
            self._walter_tier_level = 2
        elif self._walter_tier_level == 0 and self._consecutive_walter_fails >= _WALTER_TIER2_FAILS:
            logger.warning(
                f"Walter Tier-2 ({self._consecutive_walter_fails} consecutive "
                f"failures) — DEEP RECOVERY + sleeping {_WALTER_TIER2_SLEEP}s "
                f"({_WALTER_TIER2_SLEEP//60} min)"
            )
            self._get_walter().deep_recovery_restart()
            time.sleep(_WALTER_TIER2_SLEEP)
            self._consecutive_walter_fails = 0
            self._walter_tier_level = 1

        # ── Tier 1 per-call retry ──────────────────────────────
        if first.get('reason') in _WALTER_RECOVERABLE:
            logger.warning(
                f"Walter recoverable failure ({first.get('reason')}: "
                f"{first.get('message', '')}) — restarting session and retrying"
            )
            self._restart_walter()
            time.sleep(_WALTER_TIER1_RETRY_SLEEP)
            second = self._get_walter().get_play_it_safe_bid(address)
            self._last_walter_call_ts = time.time()
            if second.get('reason') == REASON_OK:
                self._consecutive_walter_fails = 0
            else:
                self._consecutive_walter_fails += 1
            return second

        # no_data / non-recoverable — only count as failure if NOT no_data
        if first.get('reason') != REASON_NO_DATA:
            self._consecutive_walter_fails += 1
        else:
            self._consecutive_walter_fails = 0
        return first

    # ── Main API ──────────────────────────────────────────────

    def value_property(self, prop: Dict) -> ValuationResult:
        """Never raises — returns a ValuationResult with confidence=NONE on
        unrecoverable errors."""
        result = ValuationResult()
        address = prop.get('address') or ''
        asking  = _parse_int(prop.get('asking_price'))
        dom     = _parse_int(prop.get('days_on_market'))

        if not address:
            result.reasoning = 'No address — cannot value'
            return result

        # ── 1. Query Walter (with retry on recoverable failures) ──
        walter = self._query_walter_with_retry(address)
        reason = walter.get('reason', REASON_ERROR)
        result.walter_reason = reason
        wp = walter.get('price')

        # ── 2. WOZ lookup (informational only, never blocks the bid) ──
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

        prefix = _postcode_prefix(prop)

        # ── 3. Decide path: Walter price OK / no_data fallback / hard failure ──
        if reason == REASON_OK and wp:
            wp = int(wp)
            result.walter_price = wp
            x, dd, rd, sd, spread = _compute_x(wp, asking, dom, prefix)
            bid = int(round(wp * (1.0 - x)))
            result.suggested_bid = bid
            # HIGH whenever Walter ≥ asking, LOW when Walter < asking, MEDIUM if no asking
            if asking is None:
                result.confidence = 'MEDIUM'
            elif wp >= asking:
                result.confidence = 'HIGH'
            else:
                result.confidence = 'LOW'
            parts = [f"Walter €{wp:,}"]
            if asking:
                parts.append(f"asking €{asking:,}")
            if dom is not None:
                parts.append(f"DOM={dom}d (+{dd*100:.2f}%)")
            parts.append(f"region {prefix} (+{rd*100:.2f}%)")
            if asking:
                parts.append(f"spread {spread*100:.1f}% (+{sd*100:.2f}%)")
            parts.append(f"X={x*100:.2f}% → bid €{bid:,}")
            if woz_val:
                parts.append(f"WOZ €{woz_val:,}")
            result.reasoning = ' | '.join(parts)
            return result

        # Walter unavailable. Two sub-paths:
        #   (a) reason == no_data            → expected, immediate fallback
        #   (b) reason still recoverable     → after retry exhausted, still
        #                                       use fallback so the queue
        #                                       doesn't stall on Walter outage
        #   (c) reason in {timeout, error}   → no fallback; mark NONE so the
        #                                       row stays empty for retry later
        fallback_eligible = reason in (REASON_NO_DATA,) or reason in _WALTER_RECOVERABLE

        if not fallback_eligible:
            result.confidence = 'NONE'
            result.reasoning = (
                f"Walter unavailable (reason={reason}, "
                f"msg={walter.get('message','')}) — no bid"
            )
            logger.warning(f"  Valuation: {address} — {result.reasoning}")
            return result

        # Asking-based fallback. Need asking to compute anything.
        if not asking:
            result.confidence = 'NONE'
            result.reasoning = (
                f"Walter no_data and no asking price — cannot compute fallback bid"
            )
            return result

        # Fallback X: same DOM + region terms; spread part is 0 (no Walter).
        x, dd, rd, sd, spread = _compute_x(None, asking, dom, prefix)
        bid = int(round(asking * (1.0 - x)))
        result.suggested_bid = bid
        result.confidence = 'FALLBACK'
        parts = [f"FALLBACK (Walter reason={reason})", f"asking €{asking:,}"]
        if dom is not None:
            parts.append(f"DOM={dom}d (+{dd*100:.2f}%)")
        parts.append(f"region {prefix} (+{rd*100:.2f}%)")
        parts.append(f"X={x*100:.2f}% → bid €{bid:,}")
        if woz_val:
            parts.append(f"WOZ €{woz_val:,}")
        result.reasoning = ' | '.join(parts)
        logger.info(f"  Valuation FALLBACK for {address}: {result.reasoning}")
        return result
