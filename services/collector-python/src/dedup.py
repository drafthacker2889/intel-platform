"""
Persistent content deduplication using Redis.

Tracks:
- Crawled URLs (to avoid re-crawling)
- Content hashes (SHA-256 of HTML)
- Prevents duplicate indexing across crawl sessions
"""

import redis
from datetime import datetime, timedelta, timezone


class DedupManager:
    """
    Manages content deduplication with persistent storage in Redis.
    
    Redis keys:
    - crawled_urls:{url_hash} → TTL 90 days
    - content_hashes:{content_hash} → TTL 90 days
    """
    
    def __init__(self, redis_client: redis.Redis, ttl_days: int = 90):
        self.redis = redis_client
        self.ttl = timedelta(days=ttl_days).total_seconds()
    
    async def is_duplicate(self, content_hash: str) -> bool:
        """Check if content hash already indexed."""
        key = f"content_hash:{content_hash}"
        return bool(self.redis.get(key))
    
    async def mark_crawled(self, url: str, content_hash: str) -> None:
        """Mark URL and content as crawled."""
        url_key = f"crawled_url:{url}"
        hash_key = f"content_hash:{content_hash}"
        
        self.redis.setex(url_key, int(self.ttl), "1")
        self.redis.setex(hash_key, int(self.ttl), datetime.now(timezone.utc).isoformat())
    
    async def was_crawled(self, url: str) -> bool:
        """Check if URL was already crawled."""
        key = f"crawled_url:{url}"
        return bool(self.redis.get(key))
    
    async def get_dedup_stats(self) -> dict:
        """Return deduplication statistics."""
        url_count = len([k for k in self.redis.scan_iter("crawled_url:*")][0:])
        hash_count = len([k for k in self.redis.scan_iter("content_hash:*")][0:])
        
        return {
            "crawled_urls": url_count,
            "content_hashes": hash_count,
            "ttl_days": self.ttl / 86400,
        }
