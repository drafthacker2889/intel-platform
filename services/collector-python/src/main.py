"""
Production threat intelligence web crawler.

Handles:
- JavaScript-rendered pages (Playwright)
- CAPTCHA detection and solving
- Tor routing with circuit rotation
- Content deduplication (SHA-256)
- Multilingual link extraction
- Both clearnet and .onion URLs
"""

import asyncio
import hashlib
import json
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from typing import Optional

import redis
from pydantic import BaseSettings

from crawler import PlaywrightCrawler
from dedup import DedupManager
from tor import TorManager

# ── Structured JSON logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("collector-python")


class Config(BaseSettings):
    """Collector configuration from environment."""
    REDIS_ADDR: str = "localhost:6379"
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    
    TOR_PROXY_PORT: int = 9050
    TOR_CONTROL_PORT: int = 9051
    TOR_CONTROL_PASSWORD: str = ""
    
    START_URL: str = "https://www.torproject.org"
    ALLOWED_DOMAINS: str = "www.torproject.org,support.torproject.org,community.torproject.org"
    
    RAW_QUEUE_NAME: str = "raw_html"
    RAW_DLQ_QUEUE: str = "raw_html_dlq"
    
    MAX_PAGES: int = 250
    MAX_CONCURRENT: int = 4
    CIRCUIT_ROTATION_INTERVAL: int = 10
    
    PLAYWRIGHT_TIMEOUT_MS: int = 30_000
    PAGE_LOAD_TIMEOUT_MS: int = 15_000
    
    CAPTCHA_SOLVER_ENABLED: bool = True
    CAPTCHA_API_KEY: str = ""
    
    HEALTH_PORT: int = 8081
    
    class Config:
        env_file = ".env"
        case_sensitive = True


async def main():
    config = Config()
    logger.info('"Collector starting" | start_url="%s" max_pages=%d', config.START_URL, config.MAX_PAGES)
    
    # Redis connection
    try:
        r = redis.Redis(
            host=config.REDIS_ADDR.split(":")[0],
            port=int(config.REDIS_ADDR.split(":")[1]),
            password=config.REDIS_PASSWORD,
            db=config.REDIS_DB,
            decode_responses=True,
        )
        r.ping()
    except redis.ConnectionError as e:
        logger.error('"Redis unavailable: %s"', e)
        sys.exit(1)
    
    logger.info('"Connected to Redis"')
    
    # Deduplication manager
    dedup = DedupManager(r)
    
    # Tor manager
    tor_mgr = TorManager(
        socks_port=config.TOR_PROXY_PORT,
        control_port=config.TOR_CONTROL_PORT,
        control_password=config.TOR_CONTROL_PASSWORD,
    )
    
    # Crawler
    crawler = PlaywrightCrawler(
        redis_client=r,
        tor_manager=tor_mgr,
        dedup_manager=dedup,
        config=config,
        logger=logger,
    )
    
    # Graceful shutdown
    shutdown_event = asyncio.Event()
    
    def _handle_signal(sig, frame):
        logger.info('"Shutdown signal received (%s), draining…"', sig)
        shutdown_event.set()
    
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    
    # Run crawler
    try:
        await crawler.run(shutdown_event)
    except Exception as e:
        logger.error('"Crawler failed: %s"', e, exc_info=True)
        sys.exit(1)
    finally:
        logger.info('"Collector shutdown complete"')


if __name__ == "__main__":
    asyncio.run(main())
