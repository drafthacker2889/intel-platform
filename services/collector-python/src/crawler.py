"""
Playwright-based web crawler with JS rendering, CAPTCHA detection, and deduplication.
"""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page
import redis

from captcha_solver import CaptchaSolver
from dedup import DedupManager
from extractor import LinkExtractor
from tor import TorManager


class PlaywrightCrawler:
    """
    Production-grade web crawler with:
    - JavaScript rendering (Playwright headless browser)
    - Tor routing with circuit rotation
    - CAPTCHA detection and solving
    - Content deduplication
    - Structured logging
    """
    
    def __init__(self, redis_client: redis.Redis, tor_manager: TorManager, 
                 dedup_manager: DedupManager, config, logger: logging.Logger):
        self.redis = redis_client
        self.tor = tor_manager
        self.dedup = dedup_manager
        self.config = config
        self.logger = logger
        
        self.visited_urls: Set[str] = set()
        self.pages_visited = 0
        self.errors_total = 0
        self.captchas_hit = 0
        self.dupes_rejected = 0
        
        self.captcha_solver = CaptchaSolver(
            api_key=config.CAPTCHA_API_KEY if config.CAPTCHA_SOLVER_ENABLED else "",
            logger=logger,
        )
        self.link_extractor = LinkExtractor(logger=logger)
        self.allowed_domains = set(config.ALLOWED_DOMAINS.split(","))
    
    async def run(self, shutdown_event: asyncio.Event):
        """Main crawler event loop."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch_persistent_context(
                user_data_dir="/tmp/playwright-chrome",
                proxy={"server": f"socks5://127.0.0.1:{self.config.TOR_PROXY_PORT}"},
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            
            try:
                queue = asyncio.Queue()
                await queue.put(self.config.START_URL)
                
                tasks = []
                for i in range(self.config.MAX_CONCURRENT):
                    task = asyncio.create_task(
                        self._crawler_worker(i, browser, queue, shutdown_event)
                    )
                    tasks.append(task)
                
                await asyncio.gather(*tasks)
            finally:
                await browser.close()
                self.logger.info(
                    '"Crawler finished" | pages=%d errors=%d captchas=%d dupes=%d',
                    self.pages_visited, self.errors_total, self.captchas_hit, self.dupes_rejected,
                )
    
    async def _crawler_worker(self, worker_id: int, browser, queue: asyncio.Queue, shutdown_event: asyncio.Event):
        """Worker that processes URLs from the queue."""
        page = None
        try:
            page = await browser.new_page()
            page.set_default_timeout(self.config.PLAYWRIGHT_TIMEOUT_MS)
            
            while not shutdown_event.is_set():
                try:
                    url = queue.get_nowait()
                except asyncio.QueueEmpty:
                    if self.pages_visited >= self.config.MAX_PAGES:
                        break
                    await asyncio.sleep(0.5)
                    continue
                
                await self._crawl_page(worker_id, page, url, queue)
                
                if self.pages_visited >= self.config.MAX_PAGES:
                    break
                
                # Rotate Tor circuit every N pages
                if self.pages_visited % self.config.CIRCUIT_ROTATION_INTERVAL == 0:
                    await self.tor.get_new_circuit()
                    self.logger.info('"Rotated Tor circuit after %d pages"', self.pages_visited)
        
        finally:
            if page:
                await page.close()
    
    async def _crawl_page(self, worker_id: int, page: Page, url: str, queue: asyncio.Queue):
        """Crawl a single page, extract links, push to queue."""
        if url in self.visited_urls or self.pages_visited >= self.config.MAX_PAGES:
            return
        
        self.visited_urls.add(url)
        self.pages_visited += 1
        
        try:
            self.logger.info(
                '"Crawling [%d/%d]" | url="%s" worker=%d',
                self.pages_visited, self.config.MAX_PAGES, url, worker_id,
            )
            
            # Navigate to page with timeout
            await page.goto(url, wait_until="networkidle", timeout=self.config.PAGE_LOAD_TIMEOUT_MS)
            
            # Check for CAPTCHA
            if await self._detect_captcha(page):
                self.captchas_hit += 1
                self.logger.warning('"CAPTCHA detected on %s, attempting to solve…"', url)
                if await self._solve_captcha(page):
                    self.logger.info('"CAPTCHA solved"')
                else:
                    self.logger.warning('"CAPTCHA solve failed, skipping page"')
                    return
            
            # Extract page content
            html = await page.content()
            text = await page.evaluate("() => document.body.innerText")
            
            # Check for duplication
            content_hash = hashlib.sha256(html.encode()).hexdigest()
            if await self.dedup.is_duplicate(content_hash):
                self.dupes_rejected += 1
                self.logger.info('"Content already indexed (duplicate hash): %s"', content_hash)
                return
            
            # Mark as indexed
            await self.dedup.mark_crawled(url, content_hash)
            
            # Push to Redis queue
            payload = {
                "raw_html": html,
                "text": text,
                "source_url": url,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": content_hash,
                "traceparent": "00-" + hashlib.md5(url.encode()).hexdigest() + "-" + 
                               hashlib.md5(str(self.pages_visited).encode()).hexdigest() + "-01",
            }
            
            self.redis.lpush(self.config.RAW_QUEUE_NAME, json.dumps(payload))
            
            # Extract and queue new links
            new_links = await self.link_extractor.extract(page, url, self.allowed_domains)
            for link in new_links:
                if link not in self.visited_urls and self.pages_visited < self.config.MAX_PAGES:
                    try:
                        queue.put_nowait(link)
                    except asyncio.QueueFull:
                        pass
            
            self.logger.info('"Queued %d new links from %s"', len(new_links), url)
        
        except Exception as e:
            self.errors_total += 1
            self.logger.error('"Crawl error on %s: %s"', url, e)
            dlq_payload = {
                "error": str(e),
                "url": url,
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.redis.lpush(self.config.RAW_DLQ_QUEUE, json.dumps(dlq_payload))
    
    async def _detect_captcha(self, page: Page) -> bool:
        """Detect if page is showing a CAPTCHA."""
        captcha_selectors = [
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
            'iframe[src*="captcha"]',
            '[class*="captcha"]',
            '[id*="captcha"]',
            'img[alt*="CAPTCHA" i]',
        ]
        
        for selector in captcha_selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    return True
            except:
                pass
        
        return False
    
    async def _solve_captcha(self, page: Page) -> bool:
        """Attempt to solve CAPTCHA."""
        try:
            return await self.captcha_solver.solve(page)
        except Exception as e:
            self.logger.error('"CAPTCHA solve error: %s"', e)
            return False
