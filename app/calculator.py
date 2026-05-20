"""
PropAI Scraper – Investment Calculator

Calculates ROI, cashflow, mortgage payment and market rating
for each scraped listing.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Market price reference (€/m²) per city ────────────────────────────────────
# Updated Q1 2025 – source: Empirica, IVD
MARKTPREISE: dict[str, dict] = {
    "münchen":           {"kauf": 8800, "miete": 22.5},
    "frankfurt am main": {"kauf": 6200, "miete": 17.8},
    "frankfurt":         {"kauf": 6200, "miete": 17.8},
    "hamburg":           {"kauf": 6100, "miete": 16.2},
    "berlin":            {"kauf": 5100, "miete": 15.1},
    "stuttgart":         {"kauf": 6300, "miete": 16.8},
    "düsseldorf":        {"kauf": 5400, "miete": 15.3},
    "köln":              {"kauf": 5600, "miete": 15.8},
    "bonn":              {"kauf": 4800, "miete": 13.9},
    "mannheim":          {"kauf": 4200, "miete": 12.8},
    "heidelberg":        {"kauf": 5200, "miete": 14.5},
    "nürnberg":          {"kauf": 4600, "miete": 12.9},
    "dortmund":          {"kauf": 2800, "miete": 9.8},
    "essen":             {"kauf": 2600, "miete": 9.2},
    "leipzig":           {"kauf": 3200, "miete": 11.2},
    "dresden":           {"kauf": 3400, "miete": 11.8},
    "hannover":          {"kauf": 3600, "miete": 12.1},
    "wiesbaden":         {"kauf": 5100, "miete": 15.2},
    "mainz":             {"kauf": 4900, "miete": 14.8},
    "freiburg":          {"kauf": 5600, "miete": 16.1},
    "augsburg":          {"kauf": 5200, "miete": 14.6},
    "regensburg":        {"kauf": 5000, "miete": 14.2},
    "default":           {"kauf": 3500, "miete": 11.0},
}


def _get_markt(city: str) -> dict:
    """Get market prices for a city."""
    key = city.lower().strip()
    return MARKTPREISE.get(key, MARKTPREISE["default"])


class InvestmentCalculator:

    def enrich(self, listing: dict, params) -> dict:
        """
        Add investment metrics to a listing dict.
        Returns the listing with roi, cashflow_mo, monatsrate, bewertung etc.
        """
        listing = dict(listing)  # copy

        preis     = listing.get("preis") or 0
        wfl       = listing.get("wohnflaeche") or 0
        ort       = listing.get("ort", "")
        preis_m2  = listing.get("preis_m2") or (preis / wfl if wfl else 0)
        markt     = _get_markt(ort)

        if not preis or not wfl:
            listing["bewertung"] = "keine Daten"
            return listing

        # ── Estimated rent ────────────────────────────────────────────────────
        # Use provided kaltmiete, or estimate from market rent/m²
        kaltmiete = listing.get("kaltmiete")
        if not kaltmiete:
            miete_m2 = markt["miete"]
            kaltmiete = round(wfl * miete_m2, 0)
        listing["kaltmiete_geschaetzt"] = kaltmiete

        # ── Financing ────────────────────────────────────────────────────────
        ek_pct    = getattr(params, "eigenkapital_pct", 0.20) if params else 0.20
        zins      = getattr(params, "zinssatz", 0.039) if params else 0.039
        tilg      = getattr(params, "tilgung", 0.02) if params else 0.02
        nk_pct    = getattr(params, "kaufnebenkosten_pct", 0.10) if params else 0.10
        vw_mo     = getattr(params, "verwaltung_mo", 150.0) if params else 150.0
        ih_pct    = getattr(params, "instandhaltung_pct", 0.01) if params else 0.01

        kaufpreis_ges = preis * (1 + nk_pct)  # including purchase costs
        eigenkapital  = kaufpreis_ges * ek_pct
        darlehen      = kaufpreis_ges - eigenkapital

        # Monthly mortgage payment (annuity)
        monatsrate = round(darlehen * (zins + tilg) / 12, 2)

        # ── Annual costs ─────────────────────────────────────────────────────
        instandhaltung_mo = round(preis * ih_pct / 12, 2)
        kosten_mo = monatsrate + vw_mo + instandhaltung_mo

        # ── Cashflow ─────────────────────────────────────────────────────────
        cashflow_mo = round(kaltmiete - kosten_mo, 2)

        # ── Gross yield (Bruttorendite) ───────────────────────────────────────
        brutto_rendite = round((kaltmiete * 12) / preis * 100, 2)

        # ── Net yield (Nettorendite) ──────────────────────────────────────────
        jahrliche_kosten_ohne_tilg = (vw_mo + instandhaltung_mo + darlehen * zins / 12) * 12
        netto_rendite = round(
            ((kaltmiete * 12) - jahrliche_kosten_ohne_tilg) / eigenkapital * 100, 2
        )
        roi = max(netto_rendite, 0)

        # ── Market comparison ─────────────────────────────────────────────────
        markt_kauf_m2 = markt["kauf"]
        diff_pct = round((preis_m2 - markt_kauf_m2) / markt_kauf_m2 * 100, 1) if markt_kauf_m2 else 0

        if diff_pct <= -15:
            bewertung = "sehr günstig"
        elif diff_pct <= -5:
            bewertung = "günstig"
        elif diff_pct <= 5:
            bewertung = "marktüblich"
        elif diff_pct <= 15:
            bewertung = "leicht überteuert"
        else:
            bewertung = "überteuert"

        # ── Write back ───────────────────────────────────────────────────────
        listing.update({
            "roi":               roi,
            "brutto_rendite":    brutto_rendite,
            "cashflow_mo":       cashflow_mo,
            "monatsrate":        monatsrate,
            "darlehen":          round(darlehen, 0),
            "eigenkapital":      round(eigenkapital, 0),
            "instandhaltung_mo": instandhaltung_mo,
            "marktwert_m2":      markt_kauf_m2,
            "marktwert_diff_pct": diff_pct,
            "bewertung":         bewertung,
        })

        return listing

    def batch_stats(self, listings: list) -> dict:
        """Calculate aggregate stats for a list of listings."""
        if not listings:
            return {}
        rois      = [l["roi"] for l in listings if l.get("roi")]
        cashflows = [l["cashflow_mo"] for l in listings if l.get("cashflow_mo")]
        prices    = [l["preis"] for l in listings if l.get("preis")]
        preis_m2s = [l["preis_m2"] for l in listings if l.get("preis_m2")]
        return {
            "avg_roi":        round(sum(rois) / len(rois), 2)         if rois else None,
            "max_roi":        round(max(rois), 2)                      if rois else None,
            "avg_cashflow":   round(sum(cashflows) / len(cashflows), 2) if cashflows else None,
            "avg_preis":      round(sum(prices) / len(prices), 0)     if prices else None,
            "avg_preis_m2":   round(sum(preis_m2s) / len(preis_m2s), 0) if preis_m2s else None,
            "total":          len(listings),
            "positive_cashflow": sum(1 for c in cashflows if c > 0),
        }
