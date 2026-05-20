"""
PropAI Scraper – ZVG Portal Scraper

zvg-portal.de ist eine staatliche Website ohne Anti-Bot Schutz.
Wir scrapen Zwangsversteigerungen direkt aus dem HTML.
"""

import asyncio
import re
import logging
from typing import Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import SearchParams

logger = logging.getLogger(__name__)

BASE_URL = "https://www.zvg-portal.de"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9",
}

# Bundesland → ZVG Code
BUNDESLAND_MAP = {
    "baden-württemberg": "BW", "bayern": "BY", "berlin": "BE",
    "brandenburg": "BB", "bremen": "HB", "hamburg": "HH",
    "hessen": "HE", "mecklenburg-vorpommern": "MV", "niedersachsen": "NI",
    "nordrhein-westfalen": "NW", "rheinland-pfalz": "RP", "saarland": "SL",
    "sachsen": "SN", "sachsen-anhalt": "ST", "schleswig-holstein": "SH",
    "thüringen": "TH",
}

# Stadt → Bundesland mapping (häufigste Städte)
STADT_BUNDESLAND = {
    "frankfurt": "hessen", "frankfurt am main": "hessen",
    "münchen": "bayern", "munich": "bayern",
    "berlin": "berlin", "hamburg": "hamburg",
    "köln": "nordrhein-westfalen", "düsseldorf": "nordrhein-westfalen",
    "dortmund": "nordrhein-westfalen", "essen": "nordrhein-westfalen",
    "stuttgart": "baden-württemberg", "karlsruhe": "baden-württemberg",
    "leipzig": "sachsen", "dresden": "sachsen",
    "hannover": "niedersachsen", "braunschweig": "niedersachsen",
    "wiesbaden": "hessen", "darmstadt": "hessen", "kassel": "hessen",
    "mannheim": "baden-württemberg", "freiburg": "baden-württemberg",
    "nürnberg": "bayern", "augsburg": "bayern",
}


class ZVGScraper:

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=HEADERS,
                follow_redirects=True,
                timeout=30.0,
            )
        return self._client

    def _get_bundesland(self, ort: str) -> str:
        """Ermittle Bundesland aus Stadtname."""
        ort_lower = ort.lower().strip()
        return STADT_BUNDESLAND.get(ort_lower, "hessen")

    def _build_search_url(self, params: SearchParams, page: int = 1) -> str:
        """Baue ZVG-Portal Suchanfrage URL."""
        bundesland = self._get_bundesland(params.ort)
        bl_code = BUNDESLAND_MAP.get(bundesland, "HE")

        query = {
            "bundesland": bl_code,
            "suchbegriff": params.ort,
            "objekt_klasse": self._get_objekt_klasse(params.objekttyp),
            "seite": page,
        }
        return f"{BASE_URL}/index.php/ajax_request/index?" + urlencode(query)

    def _get_objekt_klasse(self, typ: str) -> str:
        """Map Objekttyp zu ZVG Klasse."""
        if "wohnung" in typ.lower():
            return "Wohnung"
        elif "haus" in typ.lower() or "efh" in typ.lower():
            return "Haus"
        elif "grundstück" in typ.lower():
            return "Grundstück"
        return ""  # Alle

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5))
    async def _fetch_page(self, url: str) -> Optional[str]:
        """Hole eine Seite vom ZVG-Portal."""
        client = await self._get_client()
        logger.info(f"Fetching ZVG: {url}")
        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"ZVG fetch error: {e}")
            return None

    def _parse_listing(self, row, bundesland: str, ort: str) -> Optional[dict]:
        """Parse eine ZVG Zeile aus der Ergebnistabelle."""
        try:
            cells = row.find_all("td")
            if len(cells) < 6:
                return None

            # Aktenzeichen als ID
            az = cells[0].get_text(strip=True)
            if not az:
                return None

            # Objektart
            obj_art = cells[1].get_text(strip=True)

            # Adresse
            adresse = cells[2].get_text(strip=True)

            # Amtsgericht
            gericht = cells[3].get_text(strip=True)

            # Termin
            termin = cells[4].get_text(strip=True)

            # Verkehrswert
            vw_text = cells[5].get_text(strip=True)
            vw_text_clean = re.sub(r'[^\d,.]', '', vw_text)
            try:
                verkehrswert = float(vw_text_clean.replace('.', '').replace(',', '.'))
            except (ValueError, TypeError):
                verkehrswert = None

            # Mindestgebot (typisch 50-70% des Verkehrswerts)
            mindestgebot = round(verkehrswert * 0.5, 0) if verkehrswert else None

            # Detail-Link
            detail_link = ""
            link_tag = row.find("a")
            if link_tag and link_tag.get("href"):
                href = link_tag["href"]
                detail_link = href if href.startswith("http") else f"{BASE_URL}{href}"

            # Wohnfläche aus Beschreibung extrahieren
            wfl = None
            desc_text = " ".join(c.get_text() for c in cells)
            wfl_match = re.search(r'(\d+[,.]?\d*)\s*m²', desc_text)
            if wfl_match:
                try:
                    wfl = float(wfl_match.group(1).replace(',', '.'))
                except ValueError:
                    pass

            # Zimmer aus Beschreibung
            zimmer = None
            zi_match = re.search(r'(\d+[,.]?\d*)\s*(?:Zimmer|Zi\.)', desc_text)
            if zi_match:
                try:
                    zimmer = float(zi_match.group(1).replace(',', '.'))
                except ValueError:
                    pass

            # ID aus Aktenzeichen
            listing_id = f"zvg_{az.replace('/', '_').replace(' ', '_')}"

            return {
                "id":            listing_id,
                "titel":         f"{obj_art} – {adresse[:50]}",
                "adresse":       adresse,
                "ort":           ort,
                "plz":           "",
                "preis":         mindestgebot,
                "preis_m2":      round(mindestgebot / wfl, 0) if mindestgebot and wfl else None,
                "wohnflaeche":   wfl,
                "zimmer":        zimmer,
                "baujahr":       None,
                "objekttyp":     obj_art,
                "zustand":       "Zwangsversteigerung",
                "energie_klasse": "k.A.",
                "heizungsart":   "",
                "balkon":        False,
                "keller":        False,
                "aufzug":        False,
                "kaltmiete":     None,
                "url":           detail_link or f"{BASE_URL}/index.php",
                "bilder":        [],
                "quelle":        "ZVG-Portal",
                "online_seit":   termin,
                # ZVG-spezifisch
                "aktenzeichen":  az,
                "amtsgericht":   gericht,
                "termin":        termin,
                "verkehrswert":  verkehrswert,
                "mindestgebot":  mindestgebot,
                "rabatt_pct":    round((1 - mindestgebot/verkehrswert) * 100, 1) if verkehrswert and mindestgebot else 50.0,
            }
        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return None

    def _parse_results(self, html: str, ort: str, bundesland: str) -> list:
        """Parse ZVG Suchergebnisse aus HTML."""
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # Suche Ergebnistabelle
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:  # Skip header
                listing = self._parse_listing(row, bundesland, ort)
                if listing:
                    listings.append(listing)

        # Fallback: Suche nach divs mit Objektdaten
        if not listings:
            obj_divs = soup.find_all("div", class_=re.compile(r"objekt|result|listing", re.I))
            for div in obj_divs:
                text = div.get_text()
                if "€" in text or "Verkehrswert" in text:
                    listing = self._parse_div(div, ort)
                    if listing:
                        listings.append(listing)

        return listings

    def _parse_div(self, div, ort: str) -> Optional[dict]:
        """Fallback: Parse Objekt aus div."""
        try:
            text = div.get_text(strip=True)
            vw_match = re.search(r'Verkehrswert[:\s]+([0-9.,]+)\s*€', text)
            if not vw_match:
                return None

            vw = float(vw_match.group(1).replace('.', '').replace(',', '.'))
            az_match = re.search(r'(\d+\s*K\s*\d+/\d+)', text)
            az = az_match.group(1) if az_match else f"zvg_{id(div)}"

            return {
                "id":           f"zvg_{az.replace('/', '_')}",
                "titel":        text[:60],
                "adresse":      ort,
                "ort":          ort,
                "plz":          "",
                "preis":        round(vw * 0.5, 0),
                "verkehrswert": vw,
                "mindestgebot": round(vw * 0.5, 0),
                "rabatt_pct":   50.0,
                "quelle":       "ZVG-Portal",
                "url":          BASE_URL,
                "bilder":       [],
            }
        except Exception:
            return None

    async def search(self, params: SearchParams) -> list:
        """Suche ZVG-Objekte."""
        all_listings = []
        seen_ids = set()
        bundesland = self._get_bundesland(params.ort)

        for page in range(1, min(params.max_pages + 1, 6)):
            url = self._build_search_url(params, page)
            html = await self._fetch_page(url)

            if not html:
                break

            listings = self._parse_results(html, params.ort, bundesland)

            if not listings:
                logger.info(f"ZVG page {page}: no results, stopping")
                break

            new = [l for l in listings if l["id"] not in seen_ids]
            seen_ids.update(l["id"] for l in new)
            all_listings.extend(new)

            logger.info(f"ZVG page {page}: {len(new)} listings (total: {len(all_listings)})")

            # Filter
            if params.max_price:
                all_listings = [
                    l for l in all_listings
                    if not l.get("preis") or l["preis"] <= params.max_price
                ]

            await asyncio.sleep(1.0)

        return all_listings

    async def get_detail(self, listing_id: str) -> Optional[dict]:
        """Hole ZVG Detail."""
        # ZVG Details sind in der Listenansicht enthalten
        return None

    async def close(self):
        if self._client:
            await self._client.aclose()


# ── Backward compatibility: keep ImmoScout24Scraper name ──────────────────────
ImmoScout24Scraper = ZVGScraper
