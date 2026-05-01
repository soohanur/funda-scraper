"""
Property Scraper Module — Step 2

Opens individual property pages on funda.nl, extracts structured
data from the embedded Nuxt __NUXT_DATA__ JSON (devalue format),
and falls back to DOM selectors when needed.

Data extracted per property:
  - URL
  - Asking price (numeric + formatted)
  - Bidding price (calculated)
  - Description (full text)
  - Energielabel (A+++ … G)
  - Property photo URLs only (no agency logos / similar listings)
  - Agency info (name, funda URL, phone)

Filtering:
  - Price > 750K → must contain "Niet bewoningsclausule" keyword
  - Otherwise kept
"""
import json
import re
import time
import random
from datetime import date as date_type
from typing import Optional, List, Dict, Any

from ..utils.logger import setup_logger

logger = setup_logger('funda.scraper')

# ── Keyword filter (case-insensitive) ─────────────────────────
# Matches: "Niet bewonersclausule", "niet-bewoningsclausule", etc.
KEYWORD_PATTERN = re.compile(
    r'niet[\s\-]?bewon\w*clausule',
    re.IGNORECASE,
)

# Price threshold above which keyword check is required (euros)
PRICE_THRESHOLD = 750_000

# ── Kenmerken field mapping: Dutch label → internal key ───────
# NOTE: Funda renamed several labels in 2024+:
#   "Soort woning"        -> "Soort woonhuis" / "Soort appartement"
#   "Parkeergelegenheid"  -> "Soort parkeergelegenheid"
#   "Erfpacht"            -> "Eigendomssituatie"   (value: "Volle eigendom" / "...erfpacht")
# Older labels are kept here for backwards compatibility on legacy pages.
# When multiple labels map to the same key, the FIRST match in DOM order wins.
KENMERKEN_FIELDS = {
    'Woonoppervlakte':           'living_area',
    'Perceeloppervlakte':        'plot_area',
    'Perceel':                   'plot_area',
    'Inhoud':                    'volume',
    'Aantal kamers':             'rooms',
    'Aantal slaapkamers':        'bedrooms',
    'Aantal woonlagen':          'floors',
    'Bouwjaar':                  'construction_year',
    # Property type — Funda uses one of these depending on type
    'Soort woonhuis':            'property_type',
    'Soort appartement':         'property_type',
    'Soort woning':              'property_type',   # legacy
    'Soort bouw':                'build_type',
    'Soort dak':                 'roof_type',
    'Verwarming':                'heating',
    'Isolatie':                  'insulation',
    'Onderhoud binnen':          'maintenance_inside',
    'Onderhoud buiten':          'maintenance_outside',
    'Tuin':                      'garden',
    'Ligging tuin':              'garden_orientation',
    # Parking — Funda renamed this
    'Soort parkeergelegenheid':  'parking',
    'Parkeergelegenheid':        'parking',         # legacy
    'Bijdrage VvE':              'vve_contribution',
    # Erfpacht — now exposed as "Eigendomssituatie" (Volle eigendom vs ...erfpacht)
    'Eigendomssituatie':         'erfpacht',
    'Erfpacht':                  'erfpacht',        # legacy
    'Aanvaarding':               'acceptance',
    'Ligging':                   'location_type',
    'Balkon':                    'balcony',
    'Dakterras':                 'roof_terrace',
}


class PropertyScraper:
    """
    Scrapes detailed data from individual funda.nl property pages.

    Uses the embedded __NUXT_DATA__ (Nuxt 3 devalue format) for
    reliable extraction, with DOM-based fallbacks.
    """

    def __init__(self, browser):
        self.browser = browser

    # ─── Public API ───────────────────────────────────────────

    def scrape_property(self, property_info: dict) -> Optional[dict]:
        """
        Scrape a single property page.

        Args:
            property_info: dict with keys 'id', 'url', 'address'
                           (as produced by PropertyCollector)

        Returns:
            dict with all scraped data, or None if filtered out.
        """
        url = property_info['url']
        prop_id = property_info['id']

        # Ensure absolute URL
        if url.startswith('/'):
            url = f"https://www.funda.nl{url}"

        logger.info(f"  Scraping property {prop_id}: {url}")

        # Navigate to the property page
        self.browser.navigate_to(url)
        self._wait_for_load()

        # Simulate human browsing before scraping
        self.browser.simulate_browsing()

        # Handle captcha if it appears
        if self.browser.is_captcha_page():
            logger.warning("reCAPTCHA on property page!")
            if not self.browser.wait_for_captcha_solved(timeout=30):
                logger.error("Captcha not solved — signalling for browser restart")
                return 'captcha'  # Signal worker to restart browser + re-queue
            self._wait_for_load()

        # ── Extract data from __NUXT_DATA__ ───────────────────
        nuxt = self._extract_nuxt_data()
        nuxt_available = bool(nuxt)  # True if NUXT had any data

        # ── If NUXT is completely empty, verify page loaded correctly ──
        if not nuxt_available:
            # Check if the page URL still points to this property
            current_url = self.browser.get_current_url()
            if str(prop_id) not in current_url:
                logger.warning(
                    f"  No NUXT data and URL doesn't match property {prop_id} "
                    f"(current: {current_url[:80]}) — skipping"
                )
                return None  # Skip, don't trigger restart

        # ── Price ─────────────────────────────────────────────
        numeric_price = nuxt.get('numeric_price')
        selling_price = nuxt.get('selling_price', '')

        # Fallback: DOM-based price only if NUXT didn't find it
        if not numeric_price:
            numeric_price, selling_price = self._extract_price_from_dom()

        if not numeric_price:
            logger.warning(f"  Could not extract price for {prop_id} — skipping")
            return None

        logger.info(f"    Price: {selling_price} ({numeric_price})")

        # ── Description ───────────────────────────────────────
        description = nuxt.get('description', '')
        if not description:
            description = self._extract_description_from_dom()
        logger.info(f"    Description: {len(description)} chars")

        # ── Price filter ──────────────────────────────────────
        if not self._passes_price_filter(numeric_price, description):
            logger.info(
                f"    FILTERED OUT — price {numeric_price} > {PRICE_THRESHOLD} "
                f"and keyword not found"
            )
            return None

        # ── Energielabel ──────────────────────────────────────
        energy_label = nuxt.get('energy_label', '')
        if not energy_label:
            energy_label = self._extract_energielabel_from_dom()
        logger.info(f"    Energielabel: {energy_label or 'not found'}")

        # ── Images (NUXT first, then DOM fallback) ─────────────
        photo_urls = nuxt.get('photo_urls', [])
        if not photo_urls:
            photo_urls = self._extract_images_from_nuxt_script()
        if not photo_urls:
            photo_urls = self._extract_images_from_dom()
        logger.info(f"    Photos: {len(photo_urls)}")

        # ── Agency info (from DOM — contact section only) ─────
        agency_info = self._extract_agency_from_dom()
        logger.info(
            f"    Agency: {agency_info.get('name', '?')} | "
            f"Phone: {agency_info.get('phone', '?')}"
        )

        # ── Listed since date ─────────────────────────────────
        listed_since = self._extract_listed_since()
        logger.info(f"    Listed since: {listed_since or 'unknown'}")

        # ── Kenmerken (property details table) ────────────────
        # Always merge both sources: DOM fills numeric fields that NUXT
        # stores as devalue index references (not inline strings).
        kenmerken_nuxt = self._extract_kenmerken_from_nuxt_raw()
        kenmerken_dom  = self._extract_kenmerken_from_dom()
        kenmerken = {**kenmerken_dom, **kenmerken_nuxt}  # NUXT wins on conflict
        logger.info(f"    Kenmerken: {len(kenmerken)} fields (nuxt={len(kenmerken_nuxt)}, dom={len(kenmerken_dom)})")

        # Prefer NUXT featuresFastView numbers; fall back to parsed kenmerken strings
        living_area = self._to_int(nuxt.get('living_area')) or self._parse_m2(kenmerken.get('living_area', ''))
        plot_area   = self._to_int(nuxt.get('plot_area'))   or self._parse_m2(kenmerken.get('plot_area', ''))
        rooms       = self._to_int(nuxt.get('rooms'))       or self._parse_int(kenmerken.get('rooms', ''))
        bedrooms    = self._to_int(nuxt.get('bedrooms'))    or self._parse_int(kenmerken.get('bedrooms', ''))
        construction_year = self._to_int(nuxt.get('construction_year')) or self._parse_int(kenmerken.get('construction_year', ''))
        volume      = self._to_int(nuxt.get('volume'))      or self._parse_m2(kenmerken.get('volume', ''))

        # ── Full address (street + house# + postcode + city from H1) ──
        addr_parts = self._extract_full_address()
        if addr_parts.get('postcode'):
            logger.info(f"    Address: {addr_parts.get('street','')} {addr_parts.get('house_number','')}, "
                        f"{addr_parts['postcode']} {addr_parts.get('city','')}")

        # Calculated fields
        price_per_m2   = round(numeric_price / living_area) if living_area else 0
        days_on_market = self._calculate_days_on_market(listed_since)
        logger.info(f"    Living area: {living_area} m² | Price/m²: €{price_per_m2:,} | Days: {days_on_market}")

        # ── Build result ──────────────────────────────────────
        # Prefer the H1 address (street + house# + postcode + city) over the
        # URL-slug placeholder produced by the collector.
        slug_address = property_info.get('address', '')
        full_address = self._format_address(addr_parts) or slug_address

        result = {
            'id': prop_id,
            'url': url,
            'address': full_address,
            'street':       addr_parts.get('street', ''),
            'house_number': addr_parts.get('house_number', ''),
            'house_addition': addr_parts.get('house_addition', ''),
            'postcode':     addr_parts.get('postcode', ''),
            'city':         addr_parts.get('city', ''),
            'asking_price': numeric_price,
            'asking_price_formatted': selling_price,
            # Dimensions & specs
            'living_area': living_area,
            'plot_area': plot_area,
            'rooms': rooms,
            'bedrooms': bedrooms,
            'construction_year': construction_year,
            'volume': volume,
            'floors': kenmerken.get('floors', ''),
            'property_type': kenmerken.get('property_type', ''),
            'build_type': kenmerken.get('build_type', ''),
            'roof_type': kenmerken.get('roof_type', ''),
            # Condition & features
            'heating': kenmerken.get('heating', ''),
            'insulation': kenmerken.get('insulation', ''),
            'maintenance_inside': kenmerken.get('maintenance_inside', ''),
            'maintenance_outside': kenmerken.get('maintenance_outside', ''),
            'garden': kenmerken.get('garden', ''),
            'garden_orientation': kenmerken.get('garden_orientation', ''),
            'parking': kenmerken.get('parking', ''),
            # Financial / legal
            'vve_contribution': kenmerken.get('vve_contribution', ''),
            'erfpacht': kenmerken.get('erfpacht', ''),
            'acceptance': kenmerken.get('acceptance', ''),
            # Calculated
            'price_per_m2': price_per_m2,
            'days_on_market': days_on_market,
            # Other
            'energielabel': energy_label,
            'description': description,
            'listed_since': listed_since,
            'photo_urls': photo_urls,
            'agency_name': agency_info.get('name', ''),
            'agency_funda_url': agency_info.get('funda_url', ''),
            'agency_phone': agency_info.get('phone', ''),
            'agency_website': agency_info.get('website', ''),
            'agency_email': '',  # filled by AgencyScraper later
        }

        logger.info(f"  ✓ Property {prop_id} scraped successfully")
        return result

    # ─── NUXT DATA Extraction ─────────────────────────────────

    def _extract_nuxt_data(self) -> dict:
        """
        Extract structured data from the Nuxt 3 __NUXT_DATA__ script.

        Nuxt 3 serialises its server-side payload using the "devalue"
        format: a flat JSON array where object/array values are
        indices into the same array.  We iterate once and pick out
        the shapes we need.
        """
        try:
            raw = self.browser.execute_script(
                "var el = document.getElementById('__NUXT_DATA__');"
                "return el ? el.textContent : null;"
            )
            if not raw:
                logger.debug("  No __NUXT_DATA__ found")
                return {}

            data = json.loads(raw)
            result = {}

            for i, item in enumerate(data):
                if not isinstance(item, dict):
                    continue

                # ── Price object ──────────────────────────────
                if 'numericPrice' in item and 'sellingPrice' in item:
                    np_idx = item['numericPrice']
                    sp_idx = item['sellingPrice']
                    if self._valid_idx(data, np_idx):
                        result['numeric_price'] = data[np_idx]
                    if self._valid_idx(data, sp_idx):
                        result['selling_price'] = str(data[sp_idx])

                # ── Description (title == "Omschrijving") ─────
                if 'content' in item and 'title' in item:
                    t_idx = item['title']
                    if self._valid_idx(data, t_idx):
                        if data[t_idx] == 'Omschrijving':
                            c_idx = item['content']
                            if self._valid_idx(data, c_idx):
                                result['description'] = str(data[c_idx])

                # ── featuresFastView (energy label + dimensions) ──
                # Funda key names confirmed: numberOfBedrooms (not bedrooms),
                # no rooms/constructionYear/volume in this object.
                if 'energyLabel' in item or 'livingArea' in item:
                    for nuxt_key, res_key in [
                        ('energyLabel',        'energy_label'),
                        ('livingArea',         'living_area'),
                        ('plotArea',           'plot_area'),
                        ('numberOfBedrooms',   'bedrooms'),
                        ('numberOfRooms',      'rooms'),
                        ('constructionYear',   'construction_year'),
                        ('volume',             'volume'),
                    ]:
                        if nuxt_key in item:
                            idx = item[nuxt_key]
                            if self._valid_idx(data, idx) and data[idx] is not None:
                                result[res_key] = data[idx]

                # ── constructionYear / numberOfRooms (separate NUXT object) ──
                if 'constructionYear' in item and 'numberOfRooms' not in item:
                    if not result.get('construction_year'):
                        cy_idx = item['constructionYear']
                        if self._valid_idx(data, cy_idx) and data[cy_idx] is not None:
                            result['construction_year'] = data[cy_idx]

                if 'numberOfRooms' in item and 'livingArea' not in item:
                    if not result.get('rooms'):
                        nr_idx = item['numberOfRooms']
                        if self._valid_idx(data, nr_idx) and data[nr_idx] is not None:
                            result['rooms'] = data[nr_idx]

                # ── Photos ────────────────────────────────────
                if 'mediaBaseUrl' in item and 'items' in item:
                    base_idx = item['mediaBaseUrl']
                    if self._valid_idx(data, base_idx):
                        base_url = data[base_idx]
                        if isinstance(base_url, str) and 'valentina_media' in base_url:
                            items_idx = item['items']
                            if self._valid_idx(data, items_idx):
                                photo_urls = self._resolve_photo_ids(
                                    data, data[items_idx], base_url,
                                )
                                if photo_urls:
                                    result['photo_urls'] = photo_urls

            return result

        except Exception as e:
            logger.warning(f"  NUXT data extraction failed: {type(e).__name__}: {e}")
            return {}

    def _resolve_photo_ids(
        self, data: list, items_arr: list, base_url: str,
    ) -> List[str]:
        """Resolve photo IDs from the devalue items array."""
        urls = []
        if not isinstance(items_arr, list):
            return urls
        for ref in items_arr:
            if not self._valid_idx(data, ref):
                continue
            photo_obj = data[ref]
            if isinstance(photo_obj, dict) and 'id' in photo_obj:
                id_idx = photo_obj['id']
                if self._valid_idx(data, id_idx):
                    photo_id = str(data[id_idx])
                    url = base_url.replace('{id}', photo_id)
                    urls.append(url)
        return urls

    @staticmethod
    def _valid_idx(data: list, idx) -> bool:
        return isinstance(idx, int) and 0 <= idx < len(data)

    # ─── DOM Fallbacks ────────────────────────────────────────

    def _extract_price_from_dom(self) -> tuple:
        """Fallback: extract price from DT/DD kenmerken table."""
        try:
            dt = self.browser.find_element_safe(
                '@@tag()=dt@@text()=Vraagprijs', timeout=3
            )
            if dt:
                dd = dt.next()
                if dd:
                    price_text = dd.text.strip()
                    match = re.search(r'€\s*([\d.]+)', price_text)
                    if match:
                        numeric = int(match.group(1).replace('.', ''))
                        return numeric, price_text
        except Exception:
            pass

        # Fallback: header price span
        try:
            el = self.browser.find_element_safe(
                '@@tag()=span@@text():€ ', timeout=2
            )
            if el:
                price_text = el.text.strip()
                match = re.search(r'€\s*([\d.]+)', price_text)
                if match:
                    numeric = int(match.group(1).replace('.', ''))
                    return numeric, price_text
        except Exception:
            pass

        return None, ''

    def _extract_description_from_dom(self) -> str:
        """Fallback: extract description by expanding the panel."""
        try:
            # Try clicking "Lees de volledige omschrijving"
            btn = self.browser.find_element_safe(
                '@@tag()=button@@text():Lees de volledige omschrijving',
                timeout=3,
            )
            if btn:
                btn.click()
                time.sleep(0.5)

            # Now grab the section text
            section = self.browser.find_element_safe(
                '@@tag()=section@@text():Omschrijving', timeout=3
            )
            if section:
                text = section.text
                # Remove the heading and button text
                text = re.sub(
                    r'^Omschrijving\s*', '', text, flags=re.MULTILINE
                )
                text = re.sub(
                    r'Lees de volledige omschrijving\s*$', '', text,
                    flags=re.MULTILINE,
                )
                return text.strip()
        except Exception:
            pass
        return ''

    def _extract_energielabel_from_dom(self) -> str:
        """Fallback: extract energielabel from kenmerken or header."""
        # Strategy 1: DT/DD table (most reliable on funda)
        try:
            dt = self.browser.find_element_safe(
                '@@tag()=dt@@text()=Energielabel', timeout=3
            )
            if dt:
                dd = dt.next()
                if dd:
                    text = dd.text.strip()
                    match = re.match(r'([A-G]\+*)', text)
                    if match:
                        return match.group(1)
        except Exception:
            pass

        # Strategy 2: aria-label
        try:
            el = self.browser.find_element_safe(
                '@@attr(aria-label):Energielabel', timeout=2
            )
            if el:
                label = el.attr('aria-label') or ''
                # "Energielabel C" → "C"
                match = re.search(r'([A-G]\+*)', label)
                if match:
                    return match.group(1)
        except Exception:
            pass

        # Strategy 3: search page source for Energielabel pattern
        try:
            html = self.browser.get_page_source()
            # Look for "Energielabel","A" pattern in NUXT script
            match = re.search(r'"Energielabel"\s*[,}\]]\s*"([A-G]\+*)"', html)
            if match:
                return match.group(1)
        except Exception:
            pass

        return ''

    def _extract_images_from_nuxt_script(self) -> List[str]:
        """Fallback: extract property photo URLs from NUXT script text via regex.
        Only extracts URLs from the NUXT data (property photos),
        NOT from rendered HTML (which includes agency logos, similar listings, etc.)."""
        urls = []
        try:
            raw = self.browser.execute_script(
                "var el = document.getElementById('__NUXT_DATA__');"
                "return el ? el.textContent : null;"
            )
            if not raw:
                return urls
            # Find the mediaBaseUrl template (e.g. "https://cloud.funda.nl/valentina_media/{id}.jpg")
            base_match = re.search(
                r'"(https://cloud\.funda\.nl/valentina_media/\{id\}[^"]*)"',
                raw,
            )
            if not base_match:
                return urls
            base_url = base_match.group(1)
            # Parse NUXT data as JSON to resolve photo IDs
            data = json.loads(raw)
            for item in data:
                if isinstance(item, dict) and 'mediaBaseUrl' in item and 'items' in item:
                    items_idx = item['items']
                    if self._valid_idx(data, items_idx):
                        urls = self._resolve_photo_ids(data, data[items_idx], base_url)
                    break
        except Exception:
            pass
        return urls

    def _extract_images_from_dom(self) -> List[str]:
        """Fallback: extract property photo URLs from rendered HTML.
        Scans page source for valentina_media URLs and deduplicates by photo ID."""
        urls = []
        try:
            html = self.browser.get_page_source()
            # Find all valentina_media URLs in the HTML
            matches = re.findall(
                r'https://cloud\.funda\.nl/valentina_media/(\d+)/[^"\'<>\s]+',
                html,
            )
            # Deduplicate by photo ID, use first (typically largest) version
            seen_ids = set()
            full_matches = re.findall(
                r'(https://cloud\.funda\.nl/valentina_media/(\d+)/[^"\'<>\s]+)',
                html,
            )
            for full_url, photo_id in full_matches:
                if photo_id not in seen_ids:
                    seen_ids.add(photo_id)
                    urls.append(full_url)
        except Exception:
            pass
        return urls

    def _extract_agency_from_dom(self) -> dict:
        """Extract agency name, funda URL and phone from the DOM."""
        info: Dict[str, str] = {}

        # ── Agency name & URL: find /makelaar/ links ──
        try:
            els = self.browser.find_elements_safe(
                '@@tag()=a@@href:/makelaar/', timeout=3
            )
            for el in els:
                href = el.attr('href') or ''
                name = el.text.strip()
                if href and name:
                    if href.startswith('/'):
                        href = f"https://www.funda.nl{href}"
                    info['funda_url'] = href
                    info['name'] = name
                    break
        except Exception:
            pass

        # ── Phone: check for existing tel: links first ──
        try:
            tel_links = self.browser.find_elements_safe(
                '@@tag()=a@@href:tel:', timeout=2
            )
            for link in tel_links:
                href = link.attr('href') or ''
                if href.startswith('tel:'):
                    phone = href.replace('tel:', '').strip()
                    if phone and re.match(r'[\d\-+\s()]+$', phone):
                        info['phone'] = phone
                        break
        except Exception:
            pass

        # ── Phone: click "Toon telefoonnummer" if no tel: link found ──
        if 'phone' not in info:
            try:
                btn = self.browser.find_element_safe(
                    '@@tag()=button@@text():Toon telefoonnummer', timeout=2
                )
                if btn:
                    btn.click()
                    time.sleep(1.0)
                    # Re-check for tel: links after click
                    tel_links = self.browser.find_elements_safe(
                        '@@tag()=a@@href:tel:', timeout=3
                    )
                    for link in tel_links:
                        href = link.attr('href') or ''
                        if href.startswith('tel:'):
                            phone = href.replace('tel:', '').strip()
                            if phone and re.match(r'[\d\-+\s()]+$', phone):
                                info['phone'] = phone
                                break
            except Exception:
                pass

        # ── Phone: last resort — regex on page source ──
        if 'phone' not in info:
            try:
                html = self.browser.get_page_source()
                match = re.search(r'href="tel:([^"]+)"', html)
                if match:
                    phone = match.group(1).strip()
                    if re.match(r'[\d\-+\s()]+$', phone):
                        info['phone'] = phone
            except Exception:
                pass

        return info

    # ─── Listed Since Date ────────────────────────────────

    @staticmethod
    def _format_address(parts: dict) -> str:
        """Format address parts into 'Street Number, 1234 AB City'.
        Returns '' if the parts are insufficient (no street or no postcode).
        """
        if not parts:
            return ''
        street = (parts.get('street') or '').strip()
        number = (parts.get('house_number') or '').strip()
        addition = (parts.get('house_addition') or '').strip()
        postcode = (parts.get('postcode') or '').strip()
        city = (parts.get('city') or '').strip()
        if not street or not postcode:
            return ''
        line1 = f"{street} {number}".strip()
        if addition:
            line1 = f"{line1}-{addition}"
        # Funda postcodes are stored compact (e.g. 1015CJ); add a space for readability.
        if len(postcode) == 6 and postcode[:4].isdigit():
            postcode = f"{postcode[:4]} {postcode[4:]}"
        return f"{line1}, {postcode} {city}".strip(', ').strip()

    def _extract_full_address(self) -> dict:
        """Extract street/houseNumber/postcode/city from the H1 on the page.

        Funda's H1 looks like:
            Klarenberg 64
            4822 SH BredaMuizenberg

        Returns: {street, house_number, house_addition, postcode, city}.
        """
        try:
            h1 = self.browser.execute_script(
                "var h = document.querySelector('h1');"
                "return h ? h.innerText : '';"
            ) or ''
        except Exception:
            h1 = ''
        if not h1:
            return {}

        out = {}
        lines = [ln.strip() for ln in h1.splitlines() if ln.strip()]
        if not lines:
            return {}

        # Line 1: "Klarenberg 64" or "Hoofdweg 12-A" or "Marktplein 5 H"
        m = re.match(r'^(.+?)\s+(\d+)\s*([A-Za-z0-9\-]*)$', lines[0])
        if m:
            out['street']         = m.group(1).strip()
            out['house_number']   = m.group(2)
            out['house_addition'] = m.group(3).strip('-')

        # Line 2: "4822 SH Breda" (city may be glued to a neighbourhood)
        if len(lines) >= 2:
            m2 = re.match(r'^(\d{4}\s?[A-Z]{2})\s+(.+)$', lines[1])
            if m2:
                out['postcode'] = m2.group(1).replace(' ', '')
                # Take only letters of the first capitalised word as city.
                # H1 glues neighbourhood after city ("BredaMuizenberg",
                # "HuissenZilverkamp"), so we must stop at the next capital.
                # Use [a-z\-] (no uppercase) so the regex breaks at the boundary.
                city_blob = m2.group(2)
                city_match = re.match(r'^([A-Z][a-z\-]+(?:\s+[A-Z][a-z\-]+)?)', city_blob)
                out['city'] = city_match.group(1) if city_match else city_blob.split()[0]

        return out

    def _extract_listed_since(self) -> str:
        """Extract 'Aangeboden sinds' date, always returned as YYYY-MM-DD."""
        try:
            raw = self.browser.execute_script(
                "var el = document.getElementById('__NUXT_DATA__');"
                "return el ? el.textContent : null;"
            )
            if not raw:
                return ''

            data = json.loads(raw)
            raw_date = ''

            # Strategy 1: publicationDate field (ISO, always reliable)
            for item in data:
                if isinstance(item, dict) and 'publicationDate' in item:
                    pd_idx = item['publicationDate']
                    if isinstance(pd_idx, int) and 0 <= pd_idx < len(data):
                        date_val = str(data[pd_idx])
                        if date_val and date_val != 'None':
                            if 'T' in date_val:
                                date_val = date_val.split('T')[0]
                            raw_date = date_val
                            break

            # Strategy 2: "Aangeboden sinds" regex fallback
            if not raw_date:
                match = re.search(r'"Aangeboden sinds"\s*,\s*"([^"]+)"', raw)
                if match:
                    val = match.group(1).strip()
                    if re.search(r'\d{4}|\d+\s+\w+\s+\d{4}', val):
                        raw_date = val

            return self._normalize_date(raw_date)

        except Exception:
            pass

        return ''

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Convert any recognised date format to YYYY-MM-DD. Returns '' on failure."""
        if not date_str:
            return ''
        # Already YYYY-MM-DD
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        from datetime import datetime
        DUTCH_MONTHS = {
            'januari': 1, 'februari': 2, 'maart': 3, 'april': 4,
            'mei': 5, 'juni': 6, 'juli': 7, 'augustus': 8,
            'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
        }
        for fmt in ('%B %d, %Y', '%d %B %Y', '%d-%m-%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
            except ValueError:
                pass
        # Dutch: "15 april 2026"
        try:
            parts = date_str.lower().split()
            if len(parts) == 3 and parts[1] in DUTCH_MONTHS:
                from datetime import date as date_type2
                d = date_type2(int(parts[2]), DUTCH_MONTHS[parts[1]], int(parts[0]))
                return d.strftime('%Y-%m-%d')
        except Exception:
            pass
        return ''

    # ─── Kenmerken Extraction ─────────────────────────────────

    def _extract_kenmerken_from_nuxt_raw(self) -> dict:
        """
        Extract kenmerken string values from the raw NUXT JSON using regex.
        Adjacent string pattern: "Dutch Label","Value" in the devalue flat array.
        """
        result = {}
        try:
            raw = self.browser.execute_script(
                "var el = document.getElementById('__NUXT_DATA__');"
                "return el ? el.textContent : null;"
            )
            if not raw:
                return result
            for dutch_label, field_key in KENMERKEN_FIELDS.items():
                pattern = rf'"{re.escape(dutch_label)}"\s*,\s*"([^"\\]+)"'
                match = re.search(pattern, raw)
                if match:
                    result[field_key] = match.group(1).strip()
        except Exception as e:
            logger.debug(f"  Kenmerken NUXT extraction failed: {e}")
        return result

    def _extract_kenmerken_from_dom(self) -> dict:
        """Fallback: extract kenmerken from DT/DD pairs in page source.
        First-wins: when a label appears multiple times (e.g. Eigendomssituatie
        repeats per kadastraal perceel), keep the first occurrence — that is
        the main property, subsequent ones are auxiliary parcels.
        """
        result = {}
        try:
            html = self.browser.get_page_source()
            pairs = re.findall(
                r'<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>',
                html, re.DOTALL | re.IGNORECASE,
            )
            for dt_raw, dd_raw in pairs:
                key = re.sub(r'<[^>]+>', '', dt_raw).strip()
                value = re.sub(r'<[^>]+>', ' ', dd_raw)
                value = re.sub(r'\s+', ' ', value).strip()
                if key not in KENMERKEN_FIELDS or not value:
                    continue
                field_key = KENMERKEN_FIELDS[key]
                if field_key in result:
                    continue  # first-wins
                result[field_key] = value
        except Exception as e:
            logger.debug(f"  Kenmerken DOM extraction failed: {e}")
        return result

    # ─── Filtering & Calculation ──────────────────────────────

    @staticmethod
    def _passes_price_filter(
        numeric_price: int, description: str,
    ) -> bool:
        """
        Price filter logic:
          - ≤ 750K → always keep
          - > 750K → keep only if description contains
            "Niet bewoningsclausule" (or spelling variants)
        """
        if numeric_price <= PRICE_THRESHOLD:
            return True
        # Price exceeds threshold → check for keyword
        return bool(KEYWORD_PATTERN.search(description))

    # ─── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _to_int(value) -> int:
        """Safely convert a value (number, string-with-units, or None) to int."""
        if value is None:
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            # Handle strings like "115 m²" or "1.234"
            match = re.search(r'(\d+)', str(value).replace('.', '').replace(',', ''))
            return int(match.group(1)) if match else 0

    @staticmethod
    def _parse_m2(text: str) -> int:
        """Extract numeric value from strings like '95 m²' or '95'."""
        if not text:
            return 0
        match = re.search(r'([\d]+)', str(text).replace('.', '').replace(',', ''))
        return int(match.group(1)) if match else 0

    @staticmethod
    def _parse_int(text: str) -> int:
        """Extract first integer from a string."""
        if not text:
            return 0
        match = re.search(r'(\d+)', str(text))
        return int(match.group(1)) if match else 0

    @staticmethod
    def _calculate_days_on_market(listed_since: str) -> int:
        """Calculate days on market from various date formats."""
        if not listed_since:
            return 0
        from datetime import datetime
        # Dutch month name → number
        DUTCH_MONTHS = {
            'januari': 1, 'februari': 2, 'maart': 3, 'april': 4,
            'mei': 5, 'juni': 6, 'juli': 7, 'augustus': 8,
            'september': 9, 'oktober': 10, 'november': 11, 'december': 12,
        }
        formats = ['%Y-%m-%d', '%B %d, %Y', '%d %B %Y', '%d-%m-%Y']
        for fmt in formats:
            try:
                listed_date = datetime.strptime(listed_since[:10] if fmt == '%Y-%m-%d' else listed_since, fmt).date()
                return max(0, (date_type.today() - listed_date).days)
            except ValueError:
                pass
        # Try Dutch month names: "15 april 2026"
        try:
            parts = listed_since.lower().split()
            if len(parts) == 3 and parts[1] in DUTCH_MONTHS:
                listed_date = date_type(int(parts[2]), DUTCH_MONTHS[parts[1]], int(parts[0]))
                return max(0, (date_type.today() - listed_date).days)
        except Exception:
            pass
        return 0

    def _wait_for_load(self, max_wait: int = 15) -> None:
        """Wait for page to fully load."""
        try:
            for _ in range(max_wait * 2):
                state = self.browser.execute_script(
                    "return document.readyState"
                )
                if state == "complete":
                    time.sleep(0.5)
                    return
                time.sleep(0.5)
        except Exception:
            time.sleep(2)
