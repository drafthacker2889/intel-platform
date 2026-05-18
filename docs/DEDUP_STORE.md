# Persistent Deduplication Store (Redis + PostgreSQL)

Complete guide to cluster-wide, persistent deduplication for distributed web crawling.

## Architecture

### Single-Crawler Model (Redis Only)

```
┌──────────────┐
│   Crawler    │
│   Instance   │
└──────┬───────┘
       │
       ▼
┌──────────────────────┐
│   Redis Cache        │ (volatile, 90-day TTL)
│                      │
│ - URL tracking      │
│ - Content hashing   │ In-memory:
│ - Dedup hits        │ ~500MB per 50K URLs
└──────────────────────┘
```

**Pros:** Fast, simple
**Cons:** Lost on restart, not shared

### Clustered Model (Redis + PostgreSQL)

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Crawler 1  │    │  Crawler 2  │    │  Crawler 3  │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │
       └──────────────────┼──────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │Redis 1  │     │Redis 2  │     │Redis 3  │
    │(cache)  │     │(cache)  │     │(cache)  │
    └────┬────┘     └────┬────┘     └────┬────┘
         │               │               │
         └───────────────┼───────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │   PostgreSQL Cluster          │
         │   (persistent, distributed)   │
         │                               │
         │ - Authoritative dedup store  │
         │ - Survives restarts          │
         │ - All crawlers see same state│
         │ - 90-day TTL with cleanup    │
         │                               │
         │ Features:                     │
         │ - UPSERT atomicity           │
         │ - Content hash dedup         │
         │ - URL tracking               │
         │ - Crawler heartbeat          │
         │ - Audit trail               │
         └───────────────────────────────┘
```

**Pros:** Persistent, distributed, cluster-aware
**Cons:** Slightly slower (~10-100ms vs ~1ms Redis)

## Usage

### Single Crawler (Redis Only)

```bash
# Use default Redis dedup (existing system)
docker compose up

# No configuration needed
```

### Multi-Crawler Cluster

```bash
# 1. Start PostgreSQL
docker compose up postgres

# 2. Initialize schema
docker exec intel_postgres psql -U intel_user -d intel_dedup -f /docker-entrypoint-initdb.d/01-init.sh

# 3. Start crawlers with hybrid dedup
DEDUP_BACKEND=hybrid docker compose up
```

### Environment Variables

```bash
# .env
# ─── Dedup Configuration ───
DEDUP_BACKEND=hybrid              # redis, postgres, or hybrid
DEDUP_TTL_DAYS=90                 # Retention period

# ─── PostgreSQL Configuration ───
POSTGRES_USER=intel_user
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=intel_dedup
POSTGRES_CONNECTION_URL=postgres://intel_user:secure_password@postgres:5432/intel_dedup

# ─── Redis Configuration (cache layer) ───
REDIS_CACHE_TTL_SECONDS=600       # 10-minute cache for hybrid mode
```

## API Reference

### PostgresDedupManager

```python
from postgres_dedup import PostgresDedupManager

manager = PostgresDedupManager(
    "postgres://user:password@host:5432/dedup",
    logger,
    ttl_days=90
)

# Check if URL crawled
if manager.is_url_crawled("https://example.com/page"):
    print("Already crawled, skip it")
else:
    # Crawl and mark
    content = crawl_url("https://example.com/page")
    manager.mark_content_crawled(
        "https://example.com/page",
        content,
        metadata={"source": "darkweb", "language": "en"}
    )

# Check content duplicates
is_dup, original_url = manager.is_content_duplicate(content)
if is_dup:
    print(f"Content duplicate of {original_url}")

# Get statistics
stats = manager.get_crawl_stats()
print(f"Total URLs: {stats['total_urls']}")
print(f"Active URLs: {stats['active_urls']}")
print(f"Unique content: {stats['unique_content_hashes']}")

# Cleanup expired entries
deleted = manager.cleanup_expired()
print(f"Deleted {deleted} expired entries")
```

### HybridDedupManager

```python
from postgres_dedup import HybridDedupManager

manager = HybridDedupManager(
    redis_client,
    "postgres://user:password@host:5432/dedup",
    logger
)

# Workflow: Check cache (Redis), then persistent (PostgreSQL)
if not manager.is_url_crawled(url):
    # Crawl and mark in both Redis (fast) and PostgreSQL (persistent)
    manager.mark_url_crawled(url, content, metadata)

# Get statistics from both stores
stats = manager.get_stats()
print(f"Redis cache entries: {stats['redis_cache_entries']}")
print(f"PostgreSQL total: {stats['total_urls']}")
```

## Database Schema

### dedup_urls table

Primary table for URL and content tracking:

```sql
CREATE TABLE dedup_urls (
    id BIGSERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    content_hash VARCHAR(64),              -- SHA-256 of content
    first_crawled TIMESTAMP,               -- When first crawled
    last_crawled TIMESTAMP,                -- Most recent crawl
    crawl_count INTEGER,                   -- Times crawled
    expires_at TIMESTAMP,                  -- When to delete (TTL)
    metadata JSONB,                        -- Custom data
    created_at TIMESTAMP,                  -- Record creation
    updated_at TIMESTAMP                   -- Record modification
);

Indices:
  - url (unique)
  - content_hash (find duplicates)
  - expires_at (cleanup queries)
  - last_crawled (monitoring)
```

### crawler_instances table

Track active crawler instances:

```sql
CREATE TABLE crawler_instances (
    id SERIAL PRIMARY KEY,
    instance_id VARCHAR(255) UNIQUE,       -- Docker container ID
    hostname VARCHAR(255),                 -- Host running crawler
    status VARCHAR(50),                    -- active/inactive
    last_heartbeat TIMESTAMP,              -- Last activity
    urls_crawled BIGINT,                   -- Counter
    created_at TIMESTAMP
);

View: active_crawlers
  - Shows only crawlers active in last 5 minutes
  - Useful for monitoring cluster health
```

### dedup_audit_log table

Audit trail for debugging and monitoring:

```sql
CREATE TABLE dedup_audit_log (
    id BIGSERIAL PRIMARY KEY,
    instance_id VARCHAR(255),              -- Which crawler
    operation VARCHAR(50),                 -- crawl/skip_duplicate/error
    url TEXT,                              -- URL processed
    content_hash VARCHAR(64),              -- Content hash
    duplicate_of_url TEXT,                 -- If duplicate, original URL
    crawler_name VARCHAR(255),             -- Human-readable name
    created_at TIMESTAMP
);
```

## Performance Characteristics

### PostgreSQL Dedup

| Operation | Time | Notes |
|-----------|------|-------|
| Check URL | 10-50ms | B-tree index on url |
| Mark URL | 20-100ms | Includes INSERT/UPDATE |
| Content duplicate check | 15-80ms | Hash index lookup |
| Cleanup expired (10K entries) | 100-500ms | Batch DELETE |
| Get statistics | 50-200ms | Full table scans |

### Hybrid (Redis + PostgreSQL)

| Operation | Time | Notes |
|-----------|------|-------|
| Check URL (cache hit) | 1-5ms | Redis only |
| Check URL (cache miss) | 10-50ms | Falls through to PostgreSQL |
| Mark URL | 20-150ms | Both Redis and PostgreSQL |
| Effective hit rate | 90%+ | With 10-min Redis TTL |

**Expected Performance:**
- 90%+ Redis hits (1-5ms)
- 10% PostgreSQL queries (10-50ms)
- **Average latency: ~5-10ms**

## Scaling Strategies

### Small Cluster (3-5 crawlers)

```bash
# Use single PostgreSQL instance
# Redis cluster for cache
# ~5GB total storage for 1M URLs

docker-compose.yml:
  postgres: 1 instance
  redis: 3-node cluster
  collectors: 5 instances
```

### Medium Cluster (10-20 crawlers)

```bash
# PostgreSQL with replication
# Redis cluster (6-node)
# ~20GB storage for 5M URLs

docker-compose.yml:
  postgres: 3-node cluster + Pgpool
  redis: 6-node cluster + Sentinel
  collectors: 20 instances
```

### Large Cluster (50+ crawlers)

```bash
# PostgreSQL with multi-region replication
# Redis cluster with cross-DC failover
# Dedicated dedup service tier
# ~100GB+ storage

kubernetes:
  postgres: StatefulSet with PersistentVolumes
  redis: StatefulSet with dynamic scaling
  collectors: Horizontal Pod Autoscaling
```

## Monitoring & Maintenance

### Check Dedup Health

```sql
-- PostgreSQL
SELECT * FROM dedup_stats;

-- Output:
-- total_urls: 1250000
-- active_urls: 1125000
-- expired_urls: 125000
-- unique_content_hashes: 987000
-- avg_crawl_count: 1.23
```

### Monitor Active Crawlers

```sql
SELECT * FROM active_crawlers;

-- instance_id  | hostname | urls_crawled | inactivity_duration
-- crawler_1   | host1    | 45000        | 00:02:15
-- crawler_2   | host2    | 52000        | 00:00:45
-- crawler_3   | host3    | 38000        | 00:01:30
```

### Cleanup Expired Entries

```sql
-- Manual cleanup (remove >90 days old)
SELECT cleanup_expired_urls();

-- Scheduled cleanup (daily via cron)
0 2 * * * psql -U intel_user -d intel_dedup -c "SELECT cleanup_expired_urls();"
```

### Check Audit Trail

```sql
-- Find all operations for specific URL
SELECT * FROM dedup_audit_log
WHERE url = 'https://example.com/page'
ORDER BY created_at DESC;

-- Count operations per instance
SELECT instance_id, COUNT(*) as operations
FROM dedup_audit_log
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY instance_id;
```

## Migration from Redis-Only to Hybrid

### Step 1: Add PostgreSQL

```bash
# Start PostgreSQL service
docker compose up postgres

# Wait for health check
docker compose ps postgres
```

### Step 2: Pre-populate PostgreSQL with existing Redis data

```python
#!/usr/bin/env python3
# Export Redis dedup to PostgreSQL

import redis
from postgres_dedup import PostgresDedupManager

redis_client = redis.Redis(host='localhost', password='...')
pg = PostgresDedupManager('postgres://...', logger)

# Get all URLs from Redis
for key in redis_client.scan_iter("crawled_url:*"):
    url = key.decode().replace("crawled_url:", "")
    pg.mark_url_crawled(url)
    print(f"Migrated {url}")

print("Migration complete")
```

### Step 3: Enable hybrid mode

```bash
# Update .env
DEDUP_BACKEND=hybrid

# Restart collectors
docker compose restart collector-python
```

### Step 4: Verify

```bash
# Check PostgreSQL has data
psql -U intel_user -d intel_dedup -c "SELECT COUNT(*) FROM dedup_urls;"

# Check logs show PostgreSQL usage
docker logs collector-python 2>&1 | grep -i "postgres\|dedup"
```

## Troubleshooting

### "PostgreSQL connection refused"

```bash
# Check if service running
docker ps | grep postgres

# Check logs
docker logs intel_postgres

# Verify network connectivity from collector
docker exec collector-python ping postgres
```

### "Dedup not working (duplicates appearing)"

```bash
# Check dedup backend
echo $DEDUP_BACKEND

# Check if PostgreSQL has data
docker exec intel_postgres psql -U intel_user -d intel_dedup \
  -c "SELECT COUNT(*) FROM dedup_urls;"

# Check audit log for errors
docker exec intel_postgres psql -U intel_user -d intel_dedup \
  -c "SELECT * FROM dedup_audit_log WHERE operation='error' ORDER BY created_at DESC LIMIT 10;"
```

### "PostgreSQL disk space full"

```bash
# Check storage usage
docker exec intel_postgres du -sh /var/lib/postgresql/data

# Cleanup old entries
docker exec intel_postgres psql -U intel_user -d intel_dedup \
  -c "SELECT cleanup_expired_urls();"

# If needed, adjust TTL
# Update DEDUP_TTL_DAYS=30 (from 90) to delete older entries faster
```

## References

- PostgreSQL Documentation: https://www.postgresql.org/docs/
- psycopg2 (Python PostgreSQL driver): https://www.psycopg.org/
- Redis-PostgreSQL Hybrid Pattern: https://aws.amazon.com/blogs/database/
