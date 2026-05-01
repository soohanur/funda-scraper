"""
Walter Living Client

Queries app.walterliving.com/ai for the "Play it Safe" bid recommendation
on a given Dutch property address.

Walter Living is a Phoenix LiveView app — chat answers stream into the DOM
over WebSocket. We don't try to talk WebSocket directly; we run a real
browser, send the prompt, and poll the DOM for the price string.

Public API:
    client = WalterClient()
    result = client.get_play_it_safe_bid("Dorpstraat 95, 5575 AG Luyksgestel")
    # → {"price": 727000, "raw_text": "...", "currency": "EUR"} or None

The browser session is persistent (one Chromium for the lifetime of the
client). Login cookies live in a profile dir, so re-login is rare.
"""
import os
import re
import time
from typing import Optional, Dict
from pathlib import Path

from .browser_automation import BrowserAutomation
from ..config import config
from ..utils.logger import setup_logger

logger = setup_logger('funda.walter')

LOGIN_URL = "https://app.walterliving.com/"
CHAT_URL  = "https://app.walterliving.com/ai"  # fresh-chat home; URL changes after first msg

PROMPT_MARKER = "PLAY_IT_SAFE_BID"
# Accept either:
#   PLAY_IT_SAFE_BID=€727000      (preferred, explicit)
#   Play it Safe-bod: €727.000    (legacy long-form)
EXPLICIT_RE = re.compile(
    rf"{PROMPT_MARKER}\s*[=:]\s*€?\s*([\d][\d.,]*)",
    re.IGNORECASE,
)
# Walter signals "I have no valuation" by answering literally PLAY_IT_SAFE_BID=€0
# (or any value <50k once cleaned). Detect explicitly so we don't burn the full
# response_timeout waiting for digits that will never come.
EXPLICIT_ZERO_RE = re.compile(
    rf"{PROMPT_MARKER}\s*[=:]\s*€?\s*0+\b",
    re.IGNORECASE,
)
LEGACY_RE = re.compile(
    r"Play\s*it\s*Safe[\s\u2010-\u2015\-]*(?:bod|bid|prijs|price)\s*[:\-]?\s*"
    r"€\s*([\d.,]+)",
    re.IGNORECASE,
)
NO_DATA_HINTS = (
    "geen gegevens", "kon geen", "niet gevonden", "no data",
    "couldn't find", "could not find", "not found",
)

# Markers that indicate a captcha / browser-challenge page (Cloudflare, Turnstile,
# generic "verify you are human"). Checked on page URL and HTML.
CAPTCHA_URL_MARKERS = (
    'challenges.cloudflare.com',
    'cf-chl-bypass',
    '/cdn-cgi/challenge-platform',
)
CAPTCHA_HTML_MARKERS = (
    'just a moment',
    'verify you are human',
    'verifying you are human',
    'cf-turnstile',
    'g-recaptcha',
    'security check to access',
    'challenge-platform',
)


# Reason codes returned by get_play_it_safe_bid() — see WalterClient docstring
REASON_OK            = 'ok'
REASON_NO_DATA       = 'no_data'        # Walter explicitly said it has no valuation
REASON_CAPTCHA       = 'captcha'        # Cloudflare / challenge page in the way
REASON_NO_CHAT       = 'no_chat'        # LiveView never rendered the chat input
REASON_LOGIN_FAILED  = 'login_failed'   # bounced to /login and login submit failed
REASON_TIMEOUT       = 'timeout'        # answer never arrived within response_timeout
REASON_SEND_FAILED   = 'send_failed'    # JS dispatch to send the prompt failed
REASON_PARSE_FAILED  = 'parse_failed'   # answer arrived but no parseable price
REASON_ERROR         = 'error'          # unexpected exception — see message


class WalterClient:
    """Persistent browser client for Walter Living chat."""

    DEFAULT_PROFILE = str(
        Path(config.PROJECT_ROOT) / "funda" / "chrome_profile_walter"
    )

    def __init__(
        self,
        email: Optional[str] = None,
        password: Optional[str] = None,
        profile_path: Optional[str] = None,
        headless: Optional[bool] = None,
        port: int = 9444,
        response_timeout: int = 240,
    ):
        self.email    = email    or os.getenv("WALTER_EMAIL", "")
        self.password = password or os.getenv("WALTER_PASSWORD", "")
        if not (self.email and self.password):
            raise ValueError(
                "Walter credentials missing. Set WALTER_EMAIL + WALTER_PASSWORD "
                "in .env or pass to WalterClient(email=..., password=...)."
            )

        self.profile_path     = profile_path or self.DEFAULT_PROFILE
        self.headless         = config.HEADLESS if headless is None else headless
        self.port             = port
        self.response_timeout = response_timeout

        self._browser: Optional[BrowserAutomation] = None
        self._logged_in = False

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    def _ensure_browser(self) -> None:
        if self._browser is not None:
            return
        Path(self.profile_path).mkdir(parents=True, exist_ok=True)
        self._browser = BrowserAutomation(
            profile_path=self.profile_path,
            headless=self.headless,
            port=self.port,
        )
        self._browser.start_browser()
        logger.info(f"Walter browser started (headless={self.headless})")

    def _is_login_page(self) -> bool:
        url = self._browser.get_current_url() or ""
        return "/login" in url.lower()

    def _is_captcha_page(self) -> bool:
        """True when the current page looks like a Cloudflare/Turnstile
        challenge or generic anti-bot wall."""
        try:
            url = (self._browser.get_current_url() or '').lower()
            if any(m in url for m in CAPTCHA_URL_MARKERS):
                return True
            html = self._browser.get_page_source() or ''
            html_lc = html.lower()
            return any(m in html_lc for m in CAPTCHA_HTML_MARKERS)
        except Exception:
            return False

    def restart_browser(self) -> None:
        """Close the browser and forget login state. Next call will re-init.
        Called from the controller's Walter worker after captcha/login_failed
        to start a clean session.
        """
        try:
            self.close()
        except Exception:
            pass
        # _browser=None forces _ensure_browser to spin a fresh process

    def deep_recovery_restart(self) -> None:
        """Funda-style deep recovery: kill any chrome lingering on our port,
        wipe the entire profile directory + lock files, and re-init the
        profile path with a NEW timestamp so any per-path fingerprint Walter
        might track gets reset.

        Called when the basic restart_browser hasn't fixed repeated failures.
        Next get_play_it_safe_bid() call will spin a brand-new browser with
        a fresh profile dir, fresh user-agent (random pool in BrowserAutomation),
        fresh window size, and re-attempt login from scratch.
        """
        import subprocess
        import shutil
        import time as _t

        # 1) Close DrissionPage handle if any
        try:
            self.close()
        except Exception:
            pass

        # 2) Kill any chrome process bound to OUR debugging port (only ours
        #    — don't touch the funda collector or worker chromes)
        try:
            subprocess.run(
                ['pkill', '-9', '-f', f'remote-debugging-port={self.port}'],
                capture_output=True, timeout=10,
            )
            _t.sleep(1)
        except Exception as e:
            logger.warning(f"Walter deep-recovery: pkill failed: {e}")

        # 3) Wipe the existing profile dir + parent lock dirs entirely
        try:
            old_profile = Path(self.profile_path)
            if old_profile.exists():
                shutil.rmtree(old_profile, ignore_errors=True)
                logger.info(f"Walter deep-recovery: wiped profile {old_profile}")
        except Exception as e:
            logger.warning(f"Walter deep-recovery: wipe failed: {e}")

        # 4) Rotate to a fresh profile path so Walter can't tie us to the old
        #    directory's stored cookies/fingerprint metadata. Keep the old
        #    *base* path so config doesn't need to know the rotation.
        try:
            base = Path(self.profile_path).parent
            new_name = f"chrome_profile_walter_fresh_{int(_t.time())}"
            self.profile_path = str(base / new_name)
            Path(self.profile_path).mkdir(parents=True, exist_ok=True)
            logger.info(f"Walter deep-recovery: rotated profile path to {self.profile_path}")
        except Exception as e:
            logger.warning(f"Walter deep-recovery: profile rotation failed: {e}")

        # 5) Force fresh login state
        self._logged_in = False
        # _browser=None already set by close(); next ensure spins fresh

    def _login(self) -> bool:
        """Submit login form. Returns True on success."""
        b = self._browser
        page = b.page
        logger.info("Walter: submitting login")
        try:
            email_el = page.ele("#user_registration_email", timeout=10)
            email_el.input(self.email)
            time.sleep(0.4)
            pw_el = page.ele("#user_registration_password", timeout=5)
            pw_el.input(self.password)
            time.sleep(0.4)
            btn = page.ele(
                "css:form[action='/login'] button[type='submit']",
                timeout=5,
            )
            btn.click()
            # Wait for redirect away from /login
            for _ in range(20):
                time.sleep(0.5)
                if not self._is_login_page():
                    self._logged_in = True
                    logger.info("Walter: login successful")
                    return True
            logger.error("Walter: login did not redirect")
            return False
        except Exception as e:
            logger.error(f"Walter: login error: {e}")
            return False

    def _ensure_logged_in(self) -> bool:
        self._ensure_browser()
        if self._logged_in and not self._is_login_page():
            return True
        # Hit the app root; if we get bounced to /login, fill the form
        self._browser.navigate_to(LOGIN_URL)
        time.sleep(2)
        if self._is_login_page():
            return self._login()
        self._logged_in = True
        return True

    def close(self) -> None:
        if self._browser is not None:
            try:
                self._browser.page.quit()
            except Exception:
                pass
            self._browser = None
            self._logged_in = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ─────────────────────────────────────────────────────────────
    # Chat interaction
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_price(text: str) -> Optional[int]:
        """
        Try explicit marker first, then legacy. Collect ALL matches and
        return the largest value within the sane Dutch home-price range.
        """
        candidates = []
        for rx in (EXPLICIT_RE, LEGACY_RE):
            for m in rx.finditer(text or ""):
                raw = m.group(1)
                cleaned = raw.replace(".", "").split(",")[0]
                try:
                    val = int(cleaned)
                    candidates.append(val)
                except ValueError:
                    continue
        if not candidates:
            return None
        in_range = [v for v in candidates if 50_000 <= v <= 10_000_000]
        if in_range:
            return max(in_range)
        # Often happens mid-stream (e.g. "€727" before "000" lands).
        # Don't log as warning — the wait loop will retry.
        logger.debug(
            f"Walter: parse found {candidates} but none in 50k-10M range (mid-stream?)"
        )
        return None

    def _open_new_chat(self) -> bool:
        """
        Navigate to /ai and wait until the LiveView WebSocket renders the
        chat input (#chat_message) AND the submit button. Both must exist
        in the DOM before we attempt to send.

        Sometimes the first cold navigation to /ai doesn't render the input
        (LiveView WS handshake hiccup). Retry once with a refresh.
        """
        check_js = """
            const inp = document.getElementById('chat_message');
            const btn = document.querySelector('button[aria-label="Stuur je vraag"]');
            return JSON.stringify({ready: !!(inp && btn), url: location.pathname});
        """
        b = self._browser
        for attempt in (1, 2):
            if attempt == 1:
                b.navigate_to(CHAT_URL)
            else:
                logger.info("Walter: chat input absent on first try, refreshing")
                try:
                    b.page.refresh()
                except Exception:
                    b.navigate_to(CHAT_URL)
            deadline = time.time() + 30
            last_state = None
            while time.time() < deadline:
                time.sleep(1.0)
                if self._is_login_page():
                    logger.warning("Walter: bounced to /login during chat open")
                    return False
                try:
                    state = b.page.run_js(check_js)
                    last_state = state
                    import json as _json
                    d = _json.loads(state) if isinstance(state, str) else state
                    if d.get('ready'):
                        time.sleep(1.5)
                        return True
                except Exception as e:
                    logger.debug(f"Walter: ready-check transient: {e}")
            logger.warning(f"Walter: attempt {attempt} chat-not-ready last={last_state}")
        return False

    def _send_prompt(self, prompt: str) -> bool:
        """
        Atomic JS: set contenteditable + hidden input + dispatch events +
        click submit button — all in one call to avoid stale-element races
        from Phoenix LiveView re-renders.
        """
        import json as _json
        b = self._browser
        text = _json.dumps(prompt)
        js = f"""
            const el = document.getElementById('chat_message');
            if (!el) return 'NO_INPUT';
            el.focus();
            el.innerHTML = '';
            const p = document.createElement('p');
            p.textContent = {text};
            el.appendChild(p);
            const form = el.closest('form');
            if (!form) return 'NO_FORM';
            const hidden = form.querySelector('input[name="message"]');
            if (hidden) hidden.value = {text};
            ['input', 'change', 'keyup'].forEach(ev =>
                el.dispatchEvent(new Event(ev, {{bubbles: true}}))
            );
            // Place caret at end (some Phoenix hooks need a real selection)
            const range = document.createRange();
            range.selectNodeContents(el);
            range.collapse(false);
            const sel = window.getSelection();
            sel.removeAllRanges();
            sel.addRange(range);
            // Brief async wait for LiveView to register the change, then click
            return new Promise(resolve => {{
                setTimeout(() => {{
                    const btn = document.querySelector('button[aria-label="Stuur je vraag"]')
                              || form.querySelector('button[type="submit"]');
                    if (!btn) {{ resolve('NO_BUTTON'); return; }}
                    btn.click();
                    resolve('SENT');
                }}, 600);
            }});
        """
        try:
            result = b.page.run_js(js)
            if result != 'SENT':
                logger.error(f"Walter: send failed: {result!r}")
                return False
            return True
        except Exception as e:
            logger.error(f"Walter: send exception: {e}")
            return False

    # JS that returns just the visible chat text — much cheaper than full HTML.
    # innerText is already script/style-free and reflects what the user sees.
    _BODY_TEXT_JS = "return document.body && document.body.innerText || '';"

    def _wait_for_answer(self, prompt_text: str) -> Optional[str]:
        """
        Adaptive poll: pull `document.body.innerText` (cheap) and exit the
        moment a *sane and stable* Play-it-Safe price appears past our
        own echoed prompt.

        Stability matters because Phoenix LiveView streams the answer
        character-by-character — naïvely matching the first hit can grab
        ``€727`` half a second before ``000`` lands. We keep polling
        until either (a) the parsed price is in 50k-10M range AND hasn't
        changed for ~1.2s, or (b) Walter explicitly says no data, or
        (c) timeouts trip.

        - Fast cadence: 0.4s before any reply, 0.6s while streaming.
        - Hard early-fail if no reply signal at all after 45s.
        """
        b = self._browser
        start          = time.time()
        deadline       = start + self.response_timeout
        no_signal_by   = start + 45    # bail fast if reply never starts
        baseline_len   = None
        streaming      = False
        last_price     = None          # most recent sane parse
        last_price_at  = None          # when we first saw `last_price`
        STABLE_WINDOW  = 1.2           # seconds the value must hold

        while time.time() < deadline:
            try:
                text = b.page.run_js(self._BODY_TEXT_JS) or ""
            except Exception as e:
                logger.debug(f"Walter: innerText transient: {e}")
                time.sleep(0.5)
                continue

            if baseline_len is None:
                baseline_len = len(text)

            if not streaming and len(text) > baseline_len + 40:
                streaming = True
                logger.info(f"Walter: reply streaming after {time.time()-start:.1f}s")

            # Slice past our echoed prompt so the placeholder can't match.
            search_text = text
            idx = text.rfind(prompt_text[:60]) if prompt_text else -1
            if idx > 0:
                search_text = text[idx + len(prompt_text):]

            # "No data" early exits
            tail = search_text[-2000:].lower()
            if any(h in tail for h in NO_DATA_HINTS) and "play it safe" not in tail:
                logger.info("Walter: assistant says no data for property")
                return None
            # Explicit "PLAY_IT_SAFE_BID=€0" — Walter has no valuation
            # (typical for non-residential / historic / land-only addresses).
            # Need stability: zero must persist for STABLE_WINDOW so we don't
            # confuse it with a streamed leading digit (e.g. "€0" before "12000").
            if EXPLICIT_ZERO_RE.search(search_text):
                if last_price == 0:
                    if time.time() - last_price_at >= STABLE_WINDOW:
                        logger.info(
                            f"Walter: explicit no-valuation signal "
                            f"(€0) after {time.time()-start:.1f}s"
                        )
                        return None
                else:
                    last_price = 0
                    last_price_at = time.time()

            # Try to parse a sane price *right now*
            current = self._parse_price(search_text)

            if current is not None:
                if current == last_price:
                    if time.time() - last_price_at >= STABLE_WINDOW:
                        logger.debug(
                            f"Walter: price €{current:,} stable for "
                            f"{STABLE_WINDOW}s, returning ({time.time()-start:.1f}s total)"
                        )
                        return search_text
                else:
                    last_price    = current
                    last_price_at = time.time()
                    logger.debug(f"Walter: candidate €{current:,} at {time.time()-start:.1f}s")

            # No-signal early abort
            if not streaming and time.time() > no_signal_by:
                logger.warning("Walter: no reply signal after 45s — aborting")
                return None

            time.sleep(0.6 if streaming else 0.4)

        # Timeout — if we have ANY sane parse, return it; else give up.
        if last_price is not None:
            logger.warning(
                f"Walter: timeout but returning last sane price €{last_price:,}"
            )
            try:
                return b.page.run_js(self._BODY_TEXT_JS) or ""
            except Exception:
                return ""
        logger.warning(f"Walter: response timeout after {self.response_timeout}s")
        return None

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def get_play_it_safe_bid(self, address: str) -> Dict:
        """
        Query Walter Living. Always returns a dict (never None) with keys:
            price    : int | None       — parsed bid value when reason='ok'
            reason   : str               — one of REASON_* codes
            message  : str               — human-readable detail for logs
            raw_text : str               — answer snippet when reason='ok'
            currency : 'EUR'             — when reason='ok'

        See REASON_* constants at module top for what each reason means.
        Only `no_data` should trigger the controller's fallback formula —
        all other failure reasons are recoverable via retry/restart.
        """
        result = {'price': None, 'reason': REASON_ERROR, 'message': '',
                  'raw_text': '', 'currency': 'EUR'}

        if not address:
            result['reason'] = REASON_ERROR
            result['message'] = 'empty address'
            return result

        try:
            if not self._ensure_logged_in():
                if self._browser is not None and self._is_captcha_page():
                    result['reason'] = REASON_CAPTCHA
                    result['message'] = 'captcha on login page'
                else:
                    result['reason'] = REASON_LOGIN_FAILED
                    result['message'] = 'login submission did not redirect'
                logger.error(f"Walter: {result['message']}")
                return result

            if self._is_captcha_page():
                result['reason'] = REASON_CAPTCHA
                result['message'] = 'captcha after login'
                logger.warning(f"Walter: {result['message']}")
                return result

            if not self._open_new_chat():
                if self._is_captcha_page():
                    result['reason'] = REASON_CAPTCHA
                    result['message'] = 'captcha while opening chat'
                else:
                    result['reason'] = REASON_NO_CHAT
                    result['message'] = 'chat input never rendered'
                logger.error(f"Walter: {result['message']}")
                return result

            prompt = (
                f"Wat is de exacte Play it Safe-prijs voor {address}? "
                f"Antwoord uitsluitend op één regel, zonder uitleg, in dit exacte "
                f"formaat: {PROMPT_MARKER}=\u20ac<exacte bedrag in hele euro's, "
                "geen punten, geen comma's>."
            )
            logger.info(f"Walter: querying — {address}")
            if not self._send_prompt(prompt):
                result['reason'] = REASON_SEND_FAILED
                result['message'] = 'JS dispatch to send prompt failed'
                return result

            text = self._wait_for_answer(prompt)
            if not text:
                # Disambiguate: captcha mid-stream vs no_data vs real timeout
                if self._is_captcha_page():
                    result['reason'] = REASON_CAPTCHA
                    result['message'] = 'captcha during answer wait'
                    logger.warning(f"Walter: {result['message']} for {address}")
                    return result
                try:
                    final_text = (self._browser.page.run_js(self._BODY_TEXT_JS) or '').lower()
                except Exception:
                    final_text = ''
                if any(h in final_text for h in NO_DATA_HINTS):
                    result['reason'] = REASON_NO_DATA
                    result['message'] = 'Walter has no valuation for address'
                    logger.info(f"Walter: no_data — {address}")
                elif EXPLICIT_ZERO_RE.search(final_text):
                    result['reason'] = REASON_NO_DATA
                    result['message'] = 'Walter answered €0 (no valuation)'
                    logger.info(f"Walter: no_data (€0) — {address}")
                else:
                    result['reason'] = REASON_TIMEOUT
                    result['message'] = f'no answer within {self.response_timeout}s'
                    logger.warning(f"Walter: timeout for {address}")
                return result

            price = self._parse_price(text)
            if price is None:
                result['reason'] = REASON_PARSE_FAILED
                result['message'] = 'answer received but no parseable price'
                logger.warning(f"Walter: parse_failed for {address}")
                return result

            m = EXPLICIT_RE.search(text) or LEGACY_RE.search(text)
            snippet = text[max(0, m.start() - 80): m.end() + 120].strip() if m else ""
            logger.info(f"Walter: ✓ {address} → €{price:,}")
            result.update({
                'price':    price,
                'reason':   REASON_OK,
                'message':  '',
                'raw_text': snippet,
            })
            return result

        except Exception as e:
            result['reason'] = REASON_ERROR
            result['message'] = f'{type(e).__name__}: {e}'
            logger.error(f"Walter: unexpected error for {address}: {e}", exc_info=True)
            return result
