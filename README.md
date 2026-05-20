# PropAI Scraper API

Ein Python FastAPI Service der ImmoScout24 scrapt, ROI/Cashflow berechnet
und Daten in Supabase speichert – für die PropAI App.

## Architektur

```
PropAI Frontend (React)
       ↓ HTTP POST /search
PropAI Scraper API (FastAPI, Port 8001)
       ↓ scrapes
ImmoScout24.de (hidden JSON API)
       ↓ saves
Supabase (listings table)
```

## Setup

### 1. Python installieren (3.11+)
```bash
python3 --version   # should be 3.11+
```

### 2. Dependencies installieren
```bash
pip install -r requirements.txt
```

### 3. Umgebungsvariablen setzen
```bash
cp .env.example .env
# Öffne .env und trage deine Supabase Keys ein
```

### 4. Supabase Schema anlegen
Führe `supabase_schema.sql` im Supabase SQL Editor aus.

### 5. Server starten
```bash
uvicorn app.main:app --reload --port 8001
```

Server läuft auf: http://localhost:8001

## API Endpunkte

### POST /search
Sucht Inserate auf ImmoScout24 mit Investment-Berechnung.

**Request:**
```json
{
  "ort": "Frankfurt am Main",
  "objekttyp": "wohnung-kauf",
  "max_price": 500000,
  "min_rooms": 2,
  "max_pages": 3,
  "save_to_db": true
}
```

**Response:**
```json
{
  "listings": [
    {
      "id": "123456789",
      "titel": "Nordend · 3Zi · 82m²",
      "preis": 310000,
      "preis_m2": 3780,
      "roi": 5.2,
      "cashflow_mo": 244,
      "monatsrate": 1180,
      "bewertung": "günstig",
      "marktwert_diff_pct": -8.5,
      ...
    }
  ],
  "total": 47,
  "ort": "Frankfurt am Main",
  "source": "immoscout24"
}
```

### GET /listing/{id}
Holt Details zu einem einzelnen Inserat.

### POST /scan/{ort}
Startet einen vollständigen Hintergrund-Scan einer Stadt.
Gibt `job_id` zurück.

### GET /scan/status/{job_id}
Prüft den Status eines laufenden Scans.

## Deploy auf Railway / Fly.io

```bash
# Railway
railway init
railway up

# Fly.io
fly launch
fly deploy
```

## PropAI Frontend einbinden

In `App.jsx` die `getSearchResults` Funktion anpassen:

```javascript
const SCRAPER_URL = "http://localhost:8001"; // or production URL

const fetchRealListings = async (searchParams) => {
  const res = await fetch(`${SCRAPER_URL}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ort: searchParams.ort,
      objekttyp: searchParams.typ,
      max_price: searchParams.maxPreis,
      min_rooms: searchParams.minZimmer,
      max_pages: 3,
    })
  });
  const data = await res.json();
  return data.listings;
};
```

## Rechtliches

- Scraping öffentlich zugänglicher Daten ist in Deutschland legal (BGH Urteil)
- Keine personenbezogenen Daten von Privatpersonen speichern (DSGVO)
- Rate Limiting eingebaut (1.5s zwischen Requests)
- Robots.txt respektieren

## Deploy auf Render.com (kostenlos + Keep-Alive)

### Schritt 1: GitHub Repository erstellen
```bash
cd propai-scraper
git init
git add .
git commit -m "Initial scraper"
git remote add origin https://github.com/DEIN-USERNAME/propai-scraper.git
git push -u origin main
```

### Schritt 2: Render.com
1. render.com → "New Web Service"
2. GitHub Repository verbinden
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Umgebungsvariablen setzen:
   - `SUPABASE_URL` = deine Supabase URL
   - `SUPABASE_SERVICE_KEY` = dein Service Key
   - `RENDER_EXTERNAL_URL` = wird automatisch gesetzt
6. Deploy klicken

Der Keep-Alive Ping startet automatisch und pingt `/health`
alle 10 Minuten → Server schläft nie ein!

### Schritt 3: URL in PropAI eintragen
In App.jsx Zeile ~520:
```js
const SCRAPER_URL = "https://propai-scraper.onrender.com";
```

## Deploy auf Railway ($5/Mo, kein Keep-Alive nötig)

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```
