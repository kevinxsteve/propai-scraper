"""
PropAI Scraper – ZVG Portal
Korrekte Formularfelder: land_abk + ger_id
"""

import asyncio
import re
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import SearchParams

logger = logging.getLogger(__name__)

BASE_URL   = "https://www.zvg-portal.de"
HOME_URL   = f"{BASE_URL}/index.php"
SEARCH_URL = f"{BASE_URL}/index.php?button=Termine+suchen"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9",
    "Connection":      "keep-alive",
}

# Stadt → (land_abk, ger_id) – direkt aus dem ZVG-Portal HTML
STADT_GERICHT = {
    # Hessen
    "frankfurt am main":     ("he", "M1201"),
    "frankfurt":             ("he", "M1201"),
    "wiesbaden":             ("he", "M1906"),
    "darmstadt":             ("he", "M1103"),
    "kassel":                ("he", "M1607"),
    "offenbach am main":     ("he", "M1114"),
    "offenbach":             ("he", "M1114"),
    "hanau":                 ("he", "M1502"),
    "gießen":                ("he", "M1406"),
    "marburg":               ("he", "M1809"),
    "fulda":                 ("he", "M1301"),
    "bad homburg":           ("he", "M1202"),
    "rüsselsheim":           ("he", "M1107"),
    "dillenburg":            ("he", "M1702"),
    "limburg":               ("he", "M1706"),
    "bensheim":              ("he", "M1102"),
    "groß-gerau":            ("he", "M1106"),
    "wetzlar":               ("he", "M1710"),
    # Bayern
    "münchen":               ("by", "D2601"),
    "munich":                ("by", "D2601"),
    "nürnberg":              ("by", "D3310"),
    "augsburg":              ("by", "D2102"),
    "regensburg":            ("by", "D3410"),
    "würzburg":              ("by", "D4708"),
    "ingolstadt":            ("by", "D5701"),
    "fürth":                 ("by", "D3304"),
    "erlangen":              ("by", "D3310"),
    "rosenheim":             ("by", "D2909"),
    "landshut":              ("by", "D2404"),
    "bamberg":               ("by", "D4201"),
    "bayreuth":              ("by", "D4301"),
    "kempten":               ("by", "D2304"),
    "traunstein":            ("by", "D2910"),
    "passau":                ("by", "D2803"),
    # Berlin
    "berlin":                ("be", "F1112"),
    "berlin mitte":          ("be", "F1112"),
    "berlin charlottenburg": ("be", "F1103"),
    "berlin schöneberg":     ("be", "F1106"),
    "berlin pankow":         ("be", "F1105"),
    "berlin spandau":        ("be", "F1104"),
    "berlin neukölln":       ("be", "F1109"),
    # Hamburg
    "hamburg":               ("hh", "0"),
    # NRW
    "köln":                  ("nw", "R3306"),
    "düsseldorf":            ("nw", "R1101"),
    "dortmund":              ("nw", "R2402"),
    "essen":                 ("nw", "R2503"),
    "duisburg":              ("nw", "R1202"),
    "bochum":                ("nw", "R2201"),
    "wuppertal":             ("nw", "R1608"),
    "bonn":                  ("nw", "R3201"),
    "münster":               ("nw", "R2713"),
    "bielefeld":             ("nw", "R2101"),
    "aachen":                ("nw", "R3101"),
    "gelsenkirchen":         ("nw", "R2507"),
    "krefeld":               ("nw", "R1402"),
    "oberhausen":            ("nw", "R1206"),
    "hagen":                 ("nw", "R2602"),
    "hamm":                  ("nw", "R2404"),
    "mülheim":               ("nw", "R1205"),
    "leverkusen":            ("nw", "R3311"),
    "solingen":              ("nw", "R1605"),
    "neuss":                 ("nw", "R1102"),
    "paderborn":             ("nw", "R2809"),
    "siegen":                ("nw", "R2909"),
    "remscheid":             ("nw", "R1603"),
    "recklinghausen":        ("nw", "R2204"),
    # Baden-Württemberg
    "mannheim":              ("bw", "B1601"),
    "karlsruhe":             ("bw", "B1405"),
    "reutlingen":            ("bw", "B2705"),
    "ravensburg":            ("bw", "B2404"),
    "offenburg":             ("bw", "B1805"),
    "freiburg":              ("bw", "0"),
    "stuttgart":             ("bw", "0"),
    "heidelberg":            ("bw", "B1601"),
    # Niedersachsen
    "hannover":              ("ni", "P2305"),
    "braunschweig":          ("ni", "P1103"),
    "osnabrück":             ("ni", "P3313"),
    "oldenburg":             ("ni", "P3210"),
    "wolfsburg":             ("ni", "P2413"),
    "göttingen":             ("ni", "P1204"),
    "hildesheim":            ("ni", "P2408"),
    "lüneburg":              ("ni", "P2507"),
    "salzgitter":            ("ni", "P1108"),
    # Sachsen
    "leipzig":               ("sn", "U1308"),
    "dresden":               ("sn", "U1104"),
    "chemnitz":              ("sn", "U1206"),
    "zwickau":               ("sn", "U1222"),
    "bautzen":               ("sn", "U1101"),
    "görlitz":               ("sn", "U1107"),
    # Brandenburg
    "potsdam":               ("br", "G1312"),
    "cottbus":               ("br", "G1103"),
    "frankfurt oder":        ("br", "G1207"),
    # Sachsen-Anhalt
    "halle":                 ("st", "W1109"),
    "magdeburg":             ("st", "W1209"),
    "dessau":                ("st", "W1104"),
    # Thüringen
    "erfurt":                ("th", "Y1106"),
    "jena":                  ("th", "Y1206"),
    "gera":                  ("th", "Y1203"),
    "weimar":                ("th", "Y1114"),
    "eisenach":              ("th", "Y1105"),
    # Bremen
    "bremen":                ("hb", "H1101"),
    "bremerhaven":           ("hb", "H1102"),
    # Saarland
    "saarbrücken":           ("sl", "V1109"),
    "saarlouis":             ("sl", "V1110"),
    # Rheinland-Pfalz
    "mainz":                 ("rp", "0"),
    "koblenz":               ("rp", "0"),
    "trier":                 ("rp", "0"),
    "kaiserslautern":        ("rp", "0"),
    # Schleswig-Holstein
    "kiel":                  ("sh", "0"),
    "lübeck":                ("sh", "0"),
    "flensburg":             ("sh", "0"),
    # Mecklenburg-Vorpommern
    "rostock":               ("mv", "0"),
    "schwerin":              ("mv", "0"),
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
            # Session-Cookie holen
            try:
                r = await self._client.get(HOME_URL)
                logger.info(f"Session: {r.status_code}")
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.warning(f"Session error: {e}")
        return self._client

    def _get_gericht(self, ort: str):
        key = ort.lower().strip()
        if key in STADT_GERICHT:
            return STADT_GERICHT[key]
        for stadt, vals in STADT_GERICHT.items():
            if stadt in key or key in stadt:
                return vals
        return ("he", "M1201")  # Fallback Frankfurt

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=6))
    async def _post_search(self, land_abk: str, ger_id: str) -> Optional[str]:
        client = await self._get_client()
        form_data = {
            "land_abk":    land_abk,
            "ger_id":      ger_id,
            "az_buch":     "",
            "az_nr":       "",
            "art":         "",
            "obj":         "",
            "str":         "",
            "hnr":         "",
            "plz":         "",
            "ort":         "",
            "vtermin_von": "",
            "vtermin_bis": "",
            "wert_von":    "",
            "wert_bis":    "",
            "button":      "Termine suchen",
        }
        try:
            logger.info(f"ZVG POST: land={land_abk} ger_id={ger_id}")
            resp = await client.post(
                SEARCH_URL, data=form_data,
                headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": HOME_URL}
            )
            logger.info(f"Response: {resp.status_code}, {len(resp.text)} chars")
            logger.info(f"HTML[1000:2500]: {resp.text[1000:2500]}")
            return resp.text
        except Exception as e:
            logger.error(f"POST error: {e}")
            return None

    def _parse_results(self, html: str, ort: str) -> list:
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # Suche Tabelle mit Ergebnissen
        table = None
        for t in soup.find_all("table"):
            rows = t.find_all("tr")
            if len(rows) > 1:
                # Prüfe ob Zeilen echte Daten haben (Aktenzeichen-Format)
                for row in rows[1:3]:
                    cells = row.find_all("td")
                    if cells and re.search(r'\d{4}', cells[0].get_text()):
                        table = t
                        break
            if table:
                break

        if not table:
            logger.warning("Keine Ergebnistabelle gefunden")
            for i, t in enumerate(soup.find_all("table")[:4]):
                logger.info(f"  Tabelle {i}: {len(t.find_all('tr'))} rows | {t.get_text()[:100]}")
            return []

        rows = table.find_all("tr")
        logger.info(f"Tabelle mit {len(rows)} Zeilen gefunden")

        for row in rows[1:]:
            listing = self._parse_row(row, ort)
            if listing:
                listings.append(listing)

        logger.info(f"Geparsed: {len(listings)} Objekte")
        return listings

    def _parse_row(self, row, ort: str) -> Optional[dict]:
        cells = row.find_all("td")
        if len(cells) < 3:
            return None

        texts = [c.get_text(strip=True) for c in cells]
        az = texts[0]
        if not az or not re.search(r'\d', az):
            return None

        link = row.find("a")
        detail_url = ""
        if link and link.get("href"):
            href = link["href"]
            detail_url = href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('/')}"

        obj_art = texts[1] if len(texts) > 1 else "Immobilie"
        adresse = texts[2] if len(texts) > 2 else ort
        gericht = texts[3] if len(texts) > 3 else ""
        termin  = texts[4] if len(texts) > 4 else ""

        plz_m = re.search(r'(\d{5})', adresse)
        plz   = plz_m.group(1) if plz_m else ""

        verkehrswert = None
        all_text = " ".join(texts)
        for pat in [r'([\d.]+),\d{2}\s*€', r'€\s*([\d.]+)', r'([\d]{3,})\s*EUR']:
            m = re.search(pat, all_text)
            if m:
                try:
                    vw = float(m.group(1).replace(".", ""))
                    if vw > 1000:
                        verkehrswert = vw
                        break
                except ValueError:
                    pass

        mindestgebot = round(verkehrswert * 0.5, 0) if verkehrswert else None

        wfl = None
        wfl_m = re.search(r'(\d+[,.]?\d*)\s*m[²2]', all_text)
        if wfl_m:
            try:
                wfl = float(wfl_m.group(1).replace(',', '.'))
            except ValueError:
                pass

        return {
            "id":             f"zvg_{re.sub(r'[^a-zA-Z0-9]', '_', az)}",
            "titel":          f"{obj_art} – {adresse[:60]}" if obj_art else adresse[:60],
            "adresse":        adresse,
            "ort":            ort,
            "plz":            plz,
            "preis":          mindestgebot,
            "preis_m2":       round(mindestgebot/wfl, 0) if mindestgebot and wfl else None,
            "wohnflaeche":    wfl,
            "zimmer":         None,
            "baujahr":        None,
            "objekttyp":      obj_art or "Immobilie",
            "zustand":        "Zwangsversteigerung",
            "energie_klasse": "k.A.",
            "heizungsart":    "",
            "balkon":         False,
            "keller":         False,
            "aufzug":         False,
            "kaltmiete":      None,
            "url":            detail_url or SEARCH_URL,
            "bilder":         [],
            "quelle":         "ZVG-Portal",
            "online_seit":    termin,
            "aktenzeichen":   az,
            "amtsgericht":    gericht,
            "termin":         termin,
            "verkehrswert":   verkehrswert,
            "mindestgebot":   mindestgebot,
            "rabatt_pct":     50.0,
        }

    async def search(self, params: SearchParams) -> list:
        land_abk, ger_id = self._get_gericht(params.ort)
        logger.info(f"Suche: {params.ort} → land={land_abk}, ger_id={ger_id}")
        html = await self._post_search(land_abk, ger_id)
        if not html:
            return []
        listings = self._parse_results(html, params.ort)
        if params.max_price:
            listings = [l for l in listings if not l.get("preis") or l["preis"] <= params.max_price]
        logger.info(f"Ergebnis: {len(listings)} Objekte für {params.ort}")
        return listings

    async def get_detail(self, listing_id: str) -> Optional[dict]:
        return None

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


ImmoScout24Scraper = ZVGScraper
