"""
Extract links from rendered pages using BeautifulSoup.
"""

import logging
import re
from typing import Set
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import Page


class LinkExtractor:
    """Extracts links from rendered HTML pages."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    async def extract(self, page: Page, base_url: str, allowed_domains: Set[str]) -> Set[str]:
        """
        Extract all valid links from a page.
        Filters by allowed domains and content type.
        """
        links = set()
        
        try:
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")
            
            # Find all links
            for link in soup.find_all("a", href=True):
                href = link["href"].strip()
                
                # Skip empty, fragment, and javascript links
                if not href or href.startswith("#") or href.startswith("javascript:"):
                    continue
                
                # Resolve relative URLs
                absolute_url = urljoin(base_url, href)
                
                # Parse URL
                try:
                    parsed = urlparse(absolute_url)
                except:
                    continue
                
                # Filter by domain
                domain = parsed.netloc.lower()
                if not self._is_allowed_domain(domain, allowed_domains):
                    continue
                
                # Skip unwanted file types
                if self._is_unwanted_file(absolute_url):
                    continue
                
                # Normalize URL (remove fragment, trim query)
                normalized = self._normalize_url(absolute_url)
                links.add(normalized)
            
            return links
        
        except Exception as e:
            self.logger.error('"Link extraction failed: %s"', e)
            return set()
    
    def _is_allowed_domain(self, domain: str, allowed_domains: Set[str]) -> bool:
        """Check if domain is in allowed list (supports wildcards)."""
        for allowed in allowed_domains:
            if domain == allowed or domain.endswith("." + allowed):
                return True
        return False
    
    def _is_unwanted_file(self, url: str) -> bool:
        """Skip media, archive, and executable files."""
        unwanted_extensions = {
            ".pdf", ".zip", ".tar", ".gz", ".exe", ".dmg",
            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
            ".mp4", ".webm", ".mp3", ".wav",
        }
        
        for ext in unwanted_extensions:
            if url.lower().endswith(ext):
                return True
        
        return False
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication."""
        # Remove fragment
        if "#" in url:
            url = url[:url.index("#")]
        
        # Remove tracking parameters
        tracking_params = {"utm_", "fbclid", "gclid"}
        parsed = urlparse(url)
        
        if parsed.query:
            params = parsed.query.split("&")
            params = [p for p in params if not any(p.startswith(t) for t in tracking_params)]
            query = "&".join(params)
            url = url[:url.index("?")] + ("?" + query if query else "")
        
        return url.rstrip("/")
