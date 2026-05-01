"""
Agency Scraper Module

Extracts agency (makelaar) contact information:
  1. Phone number  — from the property page tel: link or by
                     clicking "Toon telefoonnummer"
  2. Website URL   — from the agency's funda profile page
  3. Email address — by visiting the agency's own website and
                     searching for mailto: links or email patterns

Works with the BrowserAutomation wrapper (DrissionPage / CDP).
"""
import re
import time
import threading
from typing import Optional, Dict

from ..utils.logger import setup_logger

logger = setup_logger('funda.agency')

# Max time (seconds) to spend on any external agency website page
AGENCY_WEBSITE_TIMEOUT = 12

# Regex for email addresses
EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
)

# Common contact page paths to try (reduced for speed)
CONTACT_PATHS = [
    '/contact',
    '/contact/',
]

# Email addresses to skip (generic/tracking)
SKIP_EMAIL_DOMAINS = {
    'example.com', 'sentry.io', 'wix.com', 'facebook.com',
    'google.com', 'googlemail.com', 'schema.org',
    'w3.org', 'funda.nl', 'localhost',
}


# Thread-safe agency cache — same agency across all workers
_agency_cache: Dict[str, Dict[str, str]] = {}
_agency_cache_lock = threading.Lock()


class AgencyScraper:
    """
    Scrapes agency contact details from funda and the agency website.

    Designed for speed: extracts phone from the property page DOM
    (already loaded), only navigates away for website/email.
    Uses a thread-safe cache to avoid re-scraping the same agency.
    """

    def __init__(self, browser):
        self.browser = browser

    # ─── Public API ───────────────────────────────────────────

    def scrape_agency(self, property_data: dict) -> dict:
        """
        Enrich property_data with agency email and website.

        Expects property_data to already contain:
          - agency_funda_url  (e.g. https://www.funda.nl/makelaar/63661)
          - agency_phone      (may be empty)

        Uses cache to avoid re-scraping same agency.
        Updates in-place and returns the same dict.
        """
        agency_funda_url = property_data.get('agency_funda_url', '')
        agency_name = property_data.get('agency_name', '')

        if not agency_funda_url:
            logger.warning("  No agency funda URL — skipping agency scrape")
            return property_data

        # Check cache first
        with _agency_cache_lock:
            cached = _agency_cache.get(agency_funda_url)
            if cached is not None:
                property_data['agency_website'] = cached.get('website', '')
                property_data['agency_email'] = cached.get('email', '')
                logger.info(f"  Agency {agency_name}: cached (website={cached.get('website', '?')}, email={cached.get('email', '?')})")
                return property_data

        logger.info(f"  Scraping agency: {agency_name}")

        # ── Step 1: Visit agency funda page for website URL ───
        website_url = self._get_agency_website(agency_funda_url)
        property_data['agency_website'] = website_url or ''

        if not website_url:
            logger.info("    No agency website found on funda profile")
            # Cache the negative result too
            with _agency_cache_lock:
                _agency_cache[agency_funda_url] = {'website': '', 'email': ''}
            return property_data

        logger.info(f"    Agency website: {website_url}")

        # ── Step 2: Visit agency website for email ────────────
        email = self._find_email_on_website(website_url)
        property_data['agency_email'] = email or ''

        if email:
            logger.info(f"    Agency email: {email}")
        else:
            logger.info("    No email found on agency website")

        # Cache the result
        with _agency_cache_lock:
            _agency_cache[agency_funda_url] = {
                'website': website_url or '',
                'email': email or '',
            }

        return property_data

    # ─── Agency Funda Profile ─────────────────────────────────

    def _get_agency_website(self, funda_url: str) -> Optional[str]:
        """
        Visit the makelaar profile on funda and extract website URL.
        Opens in a new tab to avoid interfering with the main property page.
        """
        agency_tab = None
        try:
            logger.debug(f"    Visiting agency profile: {funda_url}")

            # Open agency profile in a new tab to preserve property page state
            try:
                agency_tab = self.browser.page.new_tab(funda_url)
                self._smart_wait_page(agency_tab, max_wait=8)
            except Exception as e:
                logger.debug(f"    Failed to open agency tab: {e}")
                # Fallback: navigate main tab
                self.browser.navigate_to(funda_url)
                self._smart_wait()
                agency_tab = None

            page = agency_tab if agency_tab else self.browser.page

            # Verify we're on the agency page (not redirected)
            try:
                current_url = page.url if agency_tab else self.browser.get_current_url()
                if current_url and '/makelaar/' not in current_url:
                    logger.warning(f"    Agency page redirect: expected /makelaar/ but got: {current_url[:80]}")
                    return None
            except Exception:
                pass

            # Accept cookies if needed
            try:
                cookie_btn = page.ele('@@tag()=button@@text():accepteer', timeout=2)
                if cookie_btn:
                    cookie_btn.click()
                    time.sleep(0.5)
            except Exception:
                pass

            # Look for external website link
            # Strategy 1: link with "Bezoek website" or similar text
            for text in [
                'Bezoek website', 'Website', 'website',
                'Ga naar website', 'Naar website',
            ]:
                try:
                    el = page.ele(f'@@tag()=a@@text():{text}', timeout=1)
                    if el:
                        href = el.attr('href') or ''
                        if href and not href.startswith('/') and 'funda.nl' not in href:
                            return self._clean_url(href)
                except Exception:
                    continue

            # Strategy 2: look for external links (not funda.nl)
            try:
                all_links = page.eles('tag:a', timeout=2)
                for link in all_links:
                    try:
                        href = link.attr('href') or ''
                        if (
                            href.startswith('http')
                            and 'funda.nl' not in href
                            and 'google' not in href
                            and 'facebook' not in href
                            and 'instagram' not in href
                            and 'linkedin' not in href
                            and 'twitter' not in href
                            and 'youtube' not in href
                            and 'mailto:' not in href
                            and 'tel:' not in href
                        ):
                            return self._clean_url(href)
                    except Exception:
                        continue
            except Exception:
                pass

            # Strategy 3: search __NUXT_DATA__ for website URL
            try:
                nuxt_raw = page.run_js(
                    "var el = document.getElementById('__NUXT_DATA__');"
                    "return el ? el.textContent : null;"
                )
                if nuxt_raw:
                    urls = re.findall(
                        r'https?://(?!.*funda\.nl)[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}[^"]*',
                        nuxt_raw,
                    )
                    for url in urls:
                        if any(skip in url for skip in [
                            'google', 'facebook', 'sentry', 'schema.org',
                            'w3.org', 'cloudflare', 'optimizely', 'qualtrics',
                            'hotjar', 'gtm', 'googleapis',
                        ]):
                            continue
                        return self._clean_url(url)
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"    Error visiting agency profile: {e}")
        finally:
            if agency_tab:
                try:
                    agency_tab.close()
                except Exception:
                    pass

        return None

    # ─── Email Extraction ─────────────────────────────────────

    def _find_email_on_website(self, website_url: str) -> Optional[str]:
        """
        Visit the agency website and search for email addresses.
        
        Strategy:
          1. Check the landing page (especially footer) for email
          2. Only if not found, try /contact page
        
        Capped at AGENCY_WEBSITE_TIMEOUT seconds total.
        """
        deadline = time.time() + AGENCY_WEBSITE_TIMEOUT
        
        try:
            logger.debug(f"    Visiting agency website: {website_url}")

            # Open in new tab to preserve current page state
            new_tab = None
            try:
                new_tab = self.browser.page.new_tab(website_url)
                self._smart_wait_page(new_tab, max_wait=10)
            except Exception as e:
                logger.debug(f"    Failed to open new tab: {e}")
                self.browser.navigate_to(website_url)
                self._smart_wait(max_wait=10)

            page = new_tab if new_tab else self.browser.page

            # ── Step 1: Check landing page (footer has email most of the time)
            email = self._search_page_for_email(page)

            if not email and time.time() < deadline:
                # ── Step 2: Try /contact page only if landing page had no email
                base_url = self._get_base_url(website_url)
                for path in CONTACT_PATHS:
                    if time.time() >= deadline:
                        logger.debug("    Agency website timeout — stopping contact page search")
                        break
                    contact_url = base_url.rstrip('/') + path
                    try:
                        page.get(contact_url)
                        self._smart_wait_page(page, max_wait=8)
                        email = self._search_page_for_email(page)
                        if email:
                            break
                    except Exception:
                        continue

            # Close the tab
            if new_tab:
                try:
                    new_tab.close()
                except Exception:
                    pass

            return email

        except Exception as e:
            logger.warning(f"    Error searching agency website: {e}")
            return None

    def _search_page_for_email(self, page) -> Optional[str]:
        """Search a single page for email addresses - checks mailto links, footer, and full page."""
        try:
            # Strategy 1: mailto: links (most reliable)
            try:
                mailto_links = page.eles('@@tag()=a@@href:mailto:', timeout=3)
                for link in mailto_links:
                    href = link.attr('href') or ''
                    if href.startswith('mailto:'):
                        # Strip mailto: scheme + querystring, URL-decode (some
                        # sites prefix a space as %20 inside the mailto link).
                        from urllib.parse import unquote
                        email = unquote(href.replace('mailto:', '').split('?')[0]).strip()
                        if self._is_valid_email(email):
                            return email
            except Exception:
                pass

            # Strategy 2: look specifically in footer area
            try:
                for selector in ['tag:footer', '@@class:footer', '@@id:footer', '@@class:contact']:
                    footer = page.ele(selector, timeout=1)
                    if footer:
                        footer_text = footer.html
                        emails = EMAIL_PATTERN.findall(footer_text)
                        for email in emails:
                            if self._is_valid_email(email):
                                return email
            except Exception:
                pass

            # Strategy 3: regex on full page HTML
            try:
                html = page.html
                emails = EMAIL_PATTERN.findall(html)
                for email in emails:
                    if self._is_valid_email(email):
                        return email
            except Exception:
                pass

        except Exception:
            pass

        return None

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Check if email is valid and not a generic/tracking address."""
        if not email or '@' not in email:
            return False
        domain = email.split('@')[1].lower()
        if domain in SKIP_EMAIL_DOMAINS:
            return False
        if email.endswith(('.png', '.jpg', '.gif', '.svg', '.css', '.js')):
            return False
        return True

    @staticmethod
    def _clean_url(url: str) -> str:
        url = url.strip().rstrip('/')
        if not url.startswith('http'):
            url = 'https://' + url
        return url

    @staticmethod
    def _get_base_url(url: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _smart_wait(self, max_wait: int = 15) -> None:
        """Wait for page to fully load using document.readyState."""
        try:
            for _ in range(max_wait * 2):
                state = self.browser.execute_script("return document.readyState")
                if state == "complete":
                    time.sleep(0.3)
                    return
                time.sleep(0.5)
        except Exception:
            time.sleep(1)

    def _smart_wait_page(self, page, max_wait: int = 15) -> None:
        """Wait for a specific page/tab to load using document.readyState."""
        try:
            for _ in range(max_wait * 2):
                state = page.run_js("return document.readyState")
                if state == "complete":
                    time.sleep(0.3)
                    return
                time.sleep(0.5)
        except Exception:
            time.sleep(1)
