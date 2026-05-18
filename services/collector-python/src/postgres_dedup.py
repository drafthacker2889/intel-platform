"""
PostgreSQL-backed persistent deduplication store for cluster-wide crawling.

Replaces or complements Redis dedup for distributed crawler scenarios where
multiple instances need synchronized deduplication state.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import psycopg2
from psycopg2 import pool, sql


class PostgresDedupManager:
    """
    Persistent URL and content deduplication using PostgreSQL.
    
    Features:
    - Cluster-wide dedup (all crawler instances see same state)
    - Persistent across restarts
    - TTL-based cleanup (90-day retention)
    - Atomic operations (UPSERT with ON CONFLICT)
    - Connection pooling for efficiency
    """
    
    # Default TTL in days (90-day retention, then auto-delete)
    DEFAULT_TTL_DAYS = 90
    
    def __init__(
        self,
        connection_string: str,
        logger: logging.Logger,
        ttl_days: int = DEFAULT_TTL_DAYS,
        pool_minconn: int = 1,
        pool_maxconn: int = 20,
    ):
        """
        Initialize PostgreSQL dedup manager.
        
        Args:
            connection_string: PostgreSQL connection URL
                Format: postgres://user:password@host:5432/database
            logger: Python logger
            ttl_days: Retention period in days
            pool_minconn: Min connections in pool
            pool_maxconn: Max connections in pool
        """
        self.logger = logger
        self.ttl_days = ttl_days
        self.connection_string = connection_string
        
        # Create connection pool
        try:
            self.pool = psycopg2.pool.SimpleConnectionPool(
                pool_minconn,
                pool_maxconn,
                connection_string,
            )
            self.logger.info(f'PostgreSQL connection pool created ({pool_minconn}-{pool_maxconn})')
        except Exception as e:
            self.logger.error(f'Failed to create connection pool: {e}')
            raise
        
        # Ensure schema exists
        self._ensure_schema()
    
    def _get_connection(self):
        """Get connection from pool."""
        try:
            return self.pool.getconn()
        except pool.PoolError as e:
            self.logger.warning(f'Pool exhausted: {e}')
            raise
    
    def _return_connection(self, conn):
        """Return connection to pool."""
        if conn:
            self.pool.putconn(conn)
    
    def _ensure_schema(self):
        """Create schema if not exists."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Create dedup_urls table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dedup_urls (
                    url TEXT PRIMARY KEY,
                    content_hash VARCHAR(64),
                    first_crawled TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_crawled TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    crawl_count INTEGER DEFAULT 1,
                    expires_at TIMESTAMP,
                    metadata JSONB
                )
            """)
            
            # Create index on expires_at for efficient cleanup
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_dedup_urls_expires_at
                ON dedup_urls (expires_at)
            """)
            
            # Create index on content_hash for duplicate content detection
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_dedup_urls_content_hash
                ON dedup_urls (content_hash)
            """)
            
            conn.commit()
            self.logger.info('PostgreSQL schema initialized')
            
        except Exception as e:
            self.logger.error(f'Failed to create schema: {e}')
            if conn:
                conn.rollback()
            raise
        finally:
            self._return_connection(conn)
    
    def is_url_crawled(self, url: str) -> bool:
        """Check if URL has been crawled (not expired)."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 1 FROM dedup_urls
                WHERE url = %s
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                LIMIT 1
            """, (url,))
            
            result = cursor.fetchone() is not None
            cursor.close()
            
            return result
            
        except Exception as e:
            self.logger.error(f'Error checking URL: {e}')
            return False
        finally:
            self._return_connection(conn)
    
    def mark_url_crawled(
        self,
        url: str,
        content_hash: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Mark URL as crawled with optional content hash and metadata.
        
        Returns True if new entry, False if updated existing.
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            expires_at = datetime.now(timezone.utc) + timedelta(days=self.ttl_days)
            
            cursor.execute("""
                INSERT INTO dedup_urls (url, content_hash, expires_at, metadata)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (url) DO UPDATE SET
                    content_hash = COALESCE(EXCLUDED.content_hash, dedup_urls.content_hash),
                    last_crawled = CURRENT_TIMESTAMP,
                    crawl_count = crawl_count + 1,
                    expires_at = EXCLUDED.expires_at,
                    metadata = COALESCE(EXCLUDED.metadata, dedup_urls.metadata)
                RETURNING (xmax = 0) AS is_new
            """, (url, content_hash, expires_at, metadata))
            
            is_new = cursor.fetchone()[0]
            conn.commit()
            cursor.close()
            
            return is_new
            
        except Exception as e:
            self.logger.error(f'Error marking URL crawled: {e}')
            if conn:
                conn.rollback()
            return False
        finally:
            self._return_connection(conn)
    
    def is_content_duplicate(self, content: str) -> Tuple[bool, Optional[str]]:
        """
        Check if content hash already exists.
        
        Returns (is_duplicate, first_url_with_content)
        """
        conn = None
        try:
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT url FROM dedup_urls
                WHERE content_hash = %s
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                ORDER BY first_crawled ASC
                LIMIT 1
            """, (content_hash,))
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                return True, result[0]
            return False, None
            
        except Exception as e:
            self.logger.error(f'Error checking content duplicate: {e}')
            return False, None
        finally:
            self._return_connection(conn)
    
    def mark_content_crawled(self, url: str, content: str, metadata: Optional[dict] = None) -> bool:
        """Mark URL with content hash as crawled."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return self.mark_url_crawled(url, content_hash, metadata)
    
    def get_crawl_stats(self) -> dict:
        """Get deduplication statistics."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Total URLs in dedup store
            cursor.execute("SELECT COUNT(*) FROM dedup_urls")
            total_urls = cursor.fetchone()[0]
            
            # URLs not yet expired
            cursor.execute("""
                SELECT COUNT(*) FROM dedup_urls
                WHERE expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP
            """)
            active_urls = cursor.fetchone()[0]
            
            # Unique content hashes
            cursor.execute("""
                SELECT COUNT(DISTINCT content_hash) FROM dedup_urls
                WHERE content_hash IS NOT NULL
            """)
            unique_content = cursor.fetchone()[0]
            
            # Average crawl count
            cursor.execute("SELECT AVG(crawl_count) FROM dedup_urls")
            avg_crawl_count = cursor.fetchone()[0] or 0
            
            cursor.close()
            
            return {
                "total_urls": total_urls,
                "active_urls": active_urls,
                "expired_urls": total_urls - active_urls,
                "unique_content_hashes": unique_content,
                "avg_crawl_count": float(avg_crawl_count),
            }
            
        except Exception as e:
            self.logger.error(f'Error getting stats: {e}')
            return {}
        finally:
            self._return_connection(conn)
    
    def cleanup_expired(self) -> int:
        """Delete expired entries. Returns count deleted."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM dedup_urls
                WHERE expires_at IS NOT NULL
                AND expires_at <= CURRENT_TIMESTAMP
            """)
            
            deleted_count = cursor.rowcount
            conn.commit()
            cursor.close()
            
            if deleted_count > 0:
                self.logger.info(f'Cleaned up {deleted_count} expired entries')
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f'Error cleaning up expired: {e}')
            if conn:
                conn.rollback()
            return 0
        finally:
            self._return_connection(conn)
    
    def clear_all(self) -> bool:
        """Clear all deduplication data (use with caution)."""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("TRUNCATE TABLE dedup_urls")
            conn.commit()
            cursor.close()
            
            self.logger.warning('All deduplication data cleared')
            return True
            
        except Exception as e:
            self.logger.error(f'Error clearing data: {e}')
            if conn:
                conn.rollback()
            return False
        finally:
            self._return_connection(conn)
    
    def close(self):
        """Close all connections in pool."""
        try:
            self.pool.closeall()
            self.logger.info('PostgreSQL connection pool closed')
        except Exception as e:
            self.logger.error(f'Error closing pool: {e}')


class HybridDedupManager:
    """
    Hybrid deduplication: Redis (fast, volatile) + PostgreSQL (persistent, distributed).
    
    Strategy:
    - Redis: Primary cache (10-minute TTL for fast lookups)
    - PostgreSQL: Secondary persistent store (90-day TTL across crawlers)
    
    Workflow:
    1. Check Redis (O(1), ~1ms)
    2. If miss, check PostgreSQL (O(log n), ~10-100ms)
    3. If PostgreSQL hit, cache in Redis
    4. On crawl success, update both Redis and PostgreSQL
    """
    
    def __init__(
        self,
        redis_client,
        postgres_connection_string: str,
        logger: logging.Logger,
    ):
        self.redis = redis_client
        self.postgres = PostgresDedupManager(postgres_connection_string, logger)
        self.logger = logger
        self.redis_ttl_seconds = 600  # 10-minute cache TTL
    
    def is_url_crawled(self, url: str) -> bool:
        """Check URL in Redis cache first, then PostgreSQL."""
        redis_key = f"crawled_url:{url}"
        
        # Check Redis (fast)
        if self.redis.exists(redis_key):
            return True
        
        # Check PostgreSQL (persistent)
        if self.postgres.is_url_crawled(url):
            # Cache in Redis for next time
            self.redis.setex(redis_key, self.redis_ttl_seconds, "1")
            return True
        
        return False
    
    def is_content_duplicate(self, content: str) -> tuple:
        """
        Check whether identical content has already been crawled.

        Checks Redis first (fast), then falls back to PostgreSQL.
        Returns (is_duplicate, original_url_or_None).
        """
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        hash_key = f"content_hash:{content_hash}"

        # Fast path: Redis cache
        cached_url = self.redis.get(hash_key)
        if cached_url:
            return True, cached_url

        # Slow path: PostgreSQL persistent store
        is_dup, original_url = self.postgres.is_content_duplicate(content)
        if is_dup and original_url:
            # Populate Redis cache for next time
            self.redis.setex(hash_key, self.redis_ttl_seconds, original_url)
        return is_dup, original_url

    def mark_url_crawled(
        self,
        url: str,
        content: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> bool:
        """Mark URL (and optional content hash) in both Redis and PostgreSQL."""
        redis_key = f"crawled_url:{url}"

        content_hash: Optional[str] = None
        if content:
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            hash_key = f"content_hash:{content_hash}"
            self.redis.setex(hash_key, self.redis_ttl_seconds, url)

        # Persist to PostgreSQL with content hash so other crawler instances benefit
        is_new = self.postgres.mark_url_crawled(url, content_hash=content_hash, metadata=metadata)

        # Cache URL in Redis
        self.redis.setex(redis_key, self.redis_ttl_seconds, "1")

        return is_new

    def get_stats(self) -> dict:
        """Get deduplication statistics from both stores."""
        postgres_stats = self.postgres.get_crawl_stats()
        return {
            **postgres_stats,
            "redis_cache_entries": self.redis.dbsize(),
        }
