"""
PropAI Scraper – Keep-Alive Service

Pingt den eigenen Server alle 10 Minuten damit Render.com
nicht einschläft. Läuft als Background-Task beim Start.
"""

import asyncio
import logging
import os
import httpx

logger = logging.getLogger(__name__)

PING_INTERVAL = 10 * 60  # 10 Minuten


async def keep_alive():
    """Endlosschleife die den eigenen /health Endpoint pingt."""
    # Warte beim Start kurz bis der Server hochgefahren ist
    await asyncio.sleep(30)

    # Eigene URL – Render setzt diese automatisch als Umgebungsvariable
    own_url = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if not own_url:
        logger.info("Keep-alive: kein RENDER_EXTERNAL_URL gesetzt – deaktiviert")
        return

    if not own_url.startswith("http"):
        own_url = f"https://{own_url}"

    ping_url = f"{own_url}/health"
    logger.info(f"Keep-alive gestartet → pingt {ping_url} alle {PING_INTERVAL//60} Min")

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            try:
                r = await client.get(ping_url)
                logger.info(f"Keep-alive ping: {r.status_code}")
            except Exception as e:
                logger.warning(f"Keep-alive ping fehlgeschlagen: {e}")

            await asyncio.sleep(PING_INTERVAL)
