"""
PropAI Scraper – Data Models (pydantic v1 compatible)
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any


class SearchParams(BaseModel):
    ort: str = "Frankfurt am Main"
    objekttyp: str = "wohnung-kauf"
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_rooms: Optional[float] = None
    max_rooms: Optional[float] = None
    min_sqm: Optional[float] = None
    max_sqm: Optional[float] = None
    min_roi: Optional[float] = None
    max_pages: int = Field(default=3, le=20)
    save_to_db: bool = False
    kaltmiete: Optional[float] = None
    kaufnebenkosten_pct: float = 0.10
    verwaltung_mo: float = 150.0
    instandhaltung_pct: float = 0.01
    eigenkapital_pct: float = 0.20
    zinssatz: float = 0.039
    tilgung: float = 0.02

    class Config:
        extra = "ignore"


class SearchResult(BaseModel):
    listings: List[Any]
    total: int
    ort: str
    source: str


class ScrapeStatus(BaseModel):
    job_id: str
    ort: str
    status: str
    count: int = 0
    error: Optional[str] = None
