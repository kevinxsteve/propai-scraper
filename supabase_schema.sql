-- PropAI Scraper – Supabase Schema
-- Run this in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS listings (
  id               TEXT PRIMARY KEY,
  titel            TEXT,
  adresse          TEXT,
  ort              TEXT,
  plz              TEXT,
  preis            NUMERIC,
  preis_m2         NUMERIC,
  wohnflaeche      NUMERIC,
  zimmer           NUMERIC,
  baujahr          INTEGER,
  objekttyp        TEXT,
  zustand          TEXT,
  energie_klasse   TEXT,
  balkon           BOOLEAN DEFAULT false,
  keller           BOOLEAN DEFAULT false,
  aufzug           BOOLEAN DEFAULT false,
  kaltmiete        NUMERIC,
  roi              NUMERIC,
  brutto_rendite   NUMERIC,
  cashflow_mo      NUMERIC,
  monatsrate       NUMERIC,
  darlehen         NUMERIC,
  bewertung        TEXT,
  marktwert_diff_pct NUMERIC,
  url              TEXT,
  bilder           JSONB DEFAULT '[]',
  quelle           TEXT DEFAULT 'immoscout24',
  scraped_at       TIMESTAMPTZ DEFAULT NOW(),
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_listings_ort     ON listings(ort);
CREATE INDEX IF NOT EXISTS idx_listings_roi     ON listings(roi DESC);
CREATE INDEX IF NOT EXISTS idx_listings_preis   ON listings(preis);
CREATE INDEX IF NOT EXISTS idx_listings_scraped ON listings(scraped_at DESC);

-- Enable Row Level Security
ALTER TABLE listings ENABLE ROW LEVEL SECURITY;

-- Allow anyone to read (PropAI frontend uses anon key)
CREATE POLICY "Public read" ON listings
  FOR SELECT USING (true);

-- Only service role can write (scraper uses service key)
CREATE POLICY "Service write" ON listings
  FOR ALL USING (auth.role() = 'service_role');
