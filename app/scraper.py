"""
PropAI Scraper – ImmoScout24 Core Scraper

Strategy: ImmoScout24 embeds all listing data as hidden JSON in
a <script id="is24-react-app-initial-state"> tag.
We extract this JSON directly – no HTML parsing, no browser needed.

For detail pages: the same JSON is available in the page source.
"""

import asyncio
import json
import re
import logging
from typing import Optional
from urllib.parse import quote, urlencode

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import SearchParams

logger = logging.getLogger(__name__)

# ── Headers that mimic a real browser ─────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "no-cache",
}

BASE_URL = "https://www.immobilienscout24.de"


class ImmoScout24Scraper:

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                follow_redirects=True,
                timeout=30.0,
                http2=True,
            )
        return self._client

    # ── Build search URL ──────────────────────────────────────────────────────
    def _build_url(self, params: SearchParams, page: int = 1) -> str:
        """
        ImmoScout24 URL format:
        /Suche/{sort}/{type}/{location}/{price}/{rooms}/{sqm}/
        Example: /Suche/S-T/Wohnung-Kauf/Berlin/Berlin/EURO--500000.00/2.0-/60.00-
        """
        # Object type mapping
        type_map = {
            "wohnung-kauf": "Wohnung-Kauf",
            "haus-kauf":    "Haus-Kauf",
            "wohnung-miete":"Wohnung-Miete",
            "haus-miete":   "Haus-Miete",
        }
        obj_type = type_map.get(params.objekttyp, "Wohnung-Kauf")

        # Location: encode city name
        location = quote(params.ort, safe="")

        # Price range
        price_min = f"{params.min_price:.2f}" if params.min_price else ""
        price_max = f"{params.max_price:.2f}" if params.max_price else ""
        price_seg = f"EURO-{price_min}-{price_max}" if (price_min or price_max) else ""

        # Rooms
        room_min = f"{params.min_rooms:.1f}" if params.min_rooms else ""
        room_seg = f"{room_min}-" if room_min else ""

        # SQM
        sqm_min = f"{params.min_sqm:.2f}" if params.min_sqm else ""
        sqm_seg = f"{sqm_min}-" if sqm_min else ""

        # Build path segments
        segments = ["/Suche/S-T", obj_type, location, location]
        if price_seg:  segments.append(price_seg)
        if room_seg:   segments.append(room_seg)
        if sqm_seg:    segments.append(sqm_seg)

        url = BASE_URL + "/".join(segments)
        if page > 1:
            url += f"?pagenumber={page}"
        return url

    # ── Fetch a page and extract hidden JSON ──────────────────────────────────
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
    async def _fetch_json(self, url: str) -> Optional[dict]:
        """Fetch page and extract the hidden JSON state."""
        client = await self._get_client()
        logger.info(f"Fetching: {url}")

        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP {e.response.status_code} for {url}")
            return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None

        html = response.text

        # Strategy 1: Extract from <script id="is24-react-app-initial-state">
        pattern = r'<script[^>]*id=["\']is24-react-app-initial-state["\'][^>]*>(.*?)</script>'
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategy 2: Find __INITIAL_STATE__ in any script tag
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
            r'"searchResponseModel"\s*:\s*({.*?"resultlist".*?})',
            r'<script[^>]*>\s*var\s+IS24\s*=\s*({.*?});\s*</script>',
        ]
        for pat in patterns:
            match = re.search(pat, html, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        # Strategy 3: Try to find JSON in any script with "resultlist"
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        for script in scripts:
            if '"resultlist"' in script or '"searchResult"' in script:
                # Try to extract JSON object
                json_match = re.search(r'\{.*"resultlist".*\}', script, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        pass

        logger.warning(f"No JSON state found in page: {url}")
        return None

    # ── Parse listings from JSON state ────────────────────────────────────────
    def _parse_listings(self, state: dict) -> list:
        """Extract listing objects from the JSON state."""
        listings = []

        # Navigate the nested state structure
        # Common paths in IS24 state
        paths = [
            ["searchResponseModel", "resultlist", "resultlistEntries", 0, "resultlistEntry"],
            ["resultlist", "resultlistEntries", 0, "resultlistEntry"],
            ["searchResult", "listings"],
            ["listings"],
        ]

        raw_listings = []
        for path in paths:
            obj = state
            try:
                for key in path:
                    if isinstance(key, int):
                        obj = obj[key]
                    else:
                        obj = obj[key]
                if isinstance(obj, list) and obj:
                    raw_listings = obj
                    break
            except (KeyError, IndexError, TypeError):
                continue

        if not raw_listings:
            logger.warning("No listings found in JSON state")
            return []

        for raw in raw_listings:
            try:
                listing = self._parse_single(raw)
                if listing:
                    listings.append(listing)
            except Exception as e:
                logger.debug(f"Parse error for listing: {e}")
                continue

        return listings

    def _parse_single(self, raw: dict) -> Optional[dict]:
        """Parse a single listing from raw JSON."""
        # IS24 wraps listings in various ways
        expose = (
            raw.get("resultlistEntry") or
            raw.get("expose") or
            raw.get("listing") or
            raw
        )

        # Get the actual data object
        data = expose.get("expose", expose)

        # ID
        listing_id = str(
            data.get("@id") or
            data.get("id") or
            expose.get("@id") or
            ""
        )
        if not listing_id:
            return None

        # Title
        title = (
            data.get("title") or
            data.get("titlePicture", {}).get("title", "") or
            ""
        )

        # Address
        addr_data = data.get("address", {})
        street   = addr_data.get("street", "")
        house_nr = addr_data.get("houseNumber", "")
        city     = addr_data.get("city", "")
        plz      = addr_data.get("postcode", "")
        adresse  = f"{street} {house_nr}".strip() or city

        # Attributes
        attrs = {}
        for attr_list in [
            data.get("attributes", {}).get("attribute", []),
            data.get("features", []),
        ]:
            if isinstance(attr_list, list):
                for a in attr_list:
                    if isinstance(a, dict):
                        key = a.get("label", a.get("type", "")).lower()
                        val = a.get("value", a.get("values", [""])[0] if a.get("values") else "")
                        attrs[key] = val

        # Price
        price_raw = (
            data.get("price", {}).get("value") or
            data.get("calculatedTotalRent", {}).get("totalRent", {}).get("value") or
            attrs.get("kaufpreis") or
            attrs.get("kaltmiete") or
            0
        )
        try:
            price = float(str(price_raw).replace(".", "").replace(",", ".").replace("€", "").strip())
        except (ValueError, TypeError):
            price = 0.0

        # Area
        area_raw = (
            data.get("livingSpace") or
            attrs.get("wohnfläche") or
            attrs.get("wohnflaeche") or
            0
        )
        try:
            area = float(str(area_raw).replace(",", ".").replace("m²", "").strip())
        except (ValueError, TypeError):
            area = 0.0

        # Rooms
        rooms_raw = (
            data.get("numberOfRooms") or
            attrs.get("zimmer") or
            attrs.get("rooms") or
            0
        )
        try:
            rooms = float(str(rooms_raw).replace(",", "."))
        except (ValueError, TypeError):
            rooms = 0.0

        # Price per m²
        price_m2 = round(price / area, 2) if price and area else None

        # Year built
        year_raw = data.get("constructionYear") or attrs.get("baujahr") or 0
        try:
            year = int(str(year_raw).strip())
        except (ValueError, TypeError):
            year = None

        # Features
        features = str(data.get("features", "")).lower()
        feat_list = [str(f).lower() for f in data.get("featuresList", [])]
        all_features = features + " ".join(feat_list)

        # URL
        url = f"https://www.immobilienscout24.de/expose/{listing_id}"

        # Images
        pictures = data.get("titlePicture", {})
        images = []
        if pictures.get("@xlink:href"):
            images.append(pictures["@xlink:href"])
        for pic in data.get("pictures", {}).get("picture", []):
            if isinstance(pic, dict) and pic.get("@xlink:href"):
                images.append(pic["@xlink:href"])

        return {
            "id": listing_id,
            "titel": title or f"{city} · {rooms}Zi · {area}m²",
            "adresse": adresse,
            "ort": city or "",
            "plz": plz or "",
            "preis": price or None,
            "preis_m2": price_m2,
            "wohnflaeche": area or None,
            "zimmer": rooms or None,
            "baujahr": year,
            "objekttyp": data.get("type", {}).get("@codeValue", ""),
            "zustand": data.get("condition", {}).get("@codeValue", ""),
            "energie_klasse": data.get("energyPerformanceCertificate", {}).get("energyEfficiencyClass", ""),
            "heizungsart": attrs.get("heizungsart", ""),
            "balkon": "balkon" in all_features or bool(data.get("balcony")),
            "keller": "keller" in all_features or bool(data.get("cellar")),
            "aufzug": "aufzug" in all_features or bool(data.get("lift")),
            "kaltmiete": None,
            "url": url,
            "bilder": images[:5],
            "quelle": "immoscout24",
            "online_seit": data.get("creationDate", ""),
        }

    # ── Public search method ───────────────────────────────────────────────────
    async def search(self, params: SearchParams) -> list:
        """Search IS24 and return list of listings."""
        all_listings = []
        seen_ids = set()

        for page in range(1, params.max_pages + 1):
            url = self._build_url(params, page)
            state = await self._fetch_json(url)

            if not state:
                logger.warning(f"No data on page {page}, stopping")
                break

            page_listings = self._parse_listings(state)

            if not page_listings:
                logger.info(f"Page {page}: empty, stopping")
                break

            # Deduplicate
            new = [l for l in page_listings if l["id"] not in seen_ids]
            seen_ids.update(l["id"] for l in new)
            all_listings.extend(new)

            logger.info(f"Page {page}: {len(new)} new listings (total: {len(all_listings)})")

            # Polite delay between pages
            if page < params.max_pages:
                await asyncio.sleep(1.5)

            # Apply price filter
            if params.max_price:
                all_listings = [
                    l for l in all_listings
                    if not l["preis"] or l["preis"] <= params.max_price
                ]

        return all_listings

    # ── Fetch single listing detail ───────────────────────────────────────────
    async def get_detail(self, listing_id: str) -> Optional[dict]:
        """Fetch full detail page for a single listing."""
        url = f"{BASE_URL}/expose/{listing_id}"
        state = await self._fetch_json(url)
        if not state:
            return None

        # Detail page has a different structure
        expose = (
            state.get("expose") or
            state.get("exposePage", {}).get("expose") or
            {}
        )
        if expose:
            return self._parse_single({"expose": expose})

        return None

    async def close(self):
        if self._client:
            await self._client.aclose()
