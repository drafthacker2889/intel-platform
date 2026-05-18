#!/bin/bash
# PostgreSQL Schema Migration for Deduplication Store
# 
# Usage:
#   ./init_postgres_dedup.sh
#   psql -h localhost -U intel_user -d intel_dedup -f init_postgres_dedup.sql
#

cat > init_postgres_dedup.sql << 'EOF'
-- Create deduplication database (if running separate instance)
-- CREATE DATABASE intel_dedup;

-- Connect to the database
-- \c intel_dedup

-- Create dedup_urls table
CREATE TABLE IF NOT EXISTS dedup_urls (
    id BIGSERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    content_hash VARCHAR(64),
    first_crawled TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_crawled TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    crawl_count INTEGER DEFAULT 1,
    expires_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indices for efficient queries
CREATE INDEX IF NOT EXISTS idx_dedup_urls_url ON dedup_urls (url);
CREATE INDEX IF NOT EXISTS idx_dedup_urls_content_hash ON dedup_urls (content_hash);
CREATE INDEX IF NOT EXISTS idx_dedup_urls_expires_at ON dedup_urls (expires_at);
CREATE INDEX IF NOT EXISTS idx_dedup_urls_last_crawled ON dedup_urls (last_crawled);
CREATE INDEX IF NOT EXISTS idx_dedup_urls_crawler_status ON dedup_urls (expires_at, crawl_count);

-- Create update timestamp trigger
CREATE OR REPLACE FUNCTION update_dedup_urls_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_dedup_urls_timestamp ON dedup_urls;
CREATE TRIGGER trigger_dedup_urls_timestamp
BEFORE UPDATE ON dedup_urls
FOR EACH ROW
EXECUTE FUNCTION update_dedup_urls_timestamp();

-- Create materialized view for statistics
CREATE MATERIALIZED VIEW IF NOT EXISTS dedup_stats AS
SELECT
    COUNT(*) as total_urls,
    SUM(CASE WHEN expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP THEN 1 ELSE 0 END) as active_urls,
    SUM(CASE WHEN expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP THEN 1 ELSE 0 END) as expired_urls,
    COUNT(DISTINCT content_hash) as unique_content_hashes,
    AVG(crawl_count)::NUMERIC(10,2) as avg_crawl_count,
    MAX(crawl_count) as max_crawl_count,
    MIN(first_crawled) as oldest_entry,
    MAX(last_crawled) as newest_entry,
    CURRENT_TIMESTAMP as last_updated
FROM dedup_urls;

-- Create index on materialized view
CREATE INDEX IF NOT EXISTS idx_dedup_stats ON dedup_stats (last_updated);

-- Create cleanup stored procedure
CREATE OR REPLACE FUNCTION cleanup_expired_urls()
RETURNS TABLE(deleted_count INT) AS $$
DECLARE
    v_deleted INT;
BEGIN
    DELETE FROM dedup_urls
    WHERE expires_at IS NOT NULL
    AND expires_at <= CURRENT_TIMESTAMP;
    
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    
    RETURN QUERY SELECT v_deleted;
END;
$$ LANGUAGE plpgsql;

-- Create crawler instance tracking table
CREATE TABLE IF NOT EXISTS crawler_instances (
    id SERIAL PRIMARY KEY,
    instance_id VARCHAR(255) UNIQUE NOT NULL,
    hostname VARCHAR(255),
    status VARCHAR(50) DEFAULT 'active',
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    urls_crawled BIGINT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_crawler_instances_heartbeat ON crawler_instances (last_heartbeat);

-- Create heartbeat update function for crawlers
CREATE OR REPLACE FUNCTION update_crawler_heartbeat(
    p_instance_id VARCHAR,
    p_hostname VARCHAR,
    p_urls_crawled BIGINT
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO crawler_instances (instance_id, hostname, urls_crawled)
    VALUES (p_instance_id, p_hostname, p_urls_crawled)
    ON CONFLICT (instance_id) DO UPDATE SET
        last_heartbeat = CURRENT_TIMESTAMP,
        hostname = EXCLUDED.hostname,
        urls_crawled = EXCLUDED.urls_crawled;
END;
$$ LANGUAGE plpgsql;

-- Create view for active crawlers
CREATE OR REPLACE VIEW active_crawlers AS
SELECT
    instance_id,
    hostname,
    status,
    last_heartbeat,
    urls_crawled,
    CURRENT_TIMESTAMP - last_heartbeat as inactivity_duration
FROM crawler_instances
WHERE status = 'active'
AND (last_heartbeat > CURRENT_TIMESTAMP - INTERVAL '5 minutes'
     OR last_heartbeat IS NULL);

-- Log deduplication operations for audit trail
CREATE TABLE IF NOT EXISTS dedup_audit_log (
    id BIGSERIAL PRIMARY KEY,
    instance_id VARCHAR(255),
    operation VARCHAR(50),
    url TEXT,
    content_hash VARCHAR(64),
    duplicate_of_url TEXT,
    crawler_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dedup_audit_log_created_at ON dedup_audit_log (created_at);
CREATE INDEX IF NOT EXISTS idx_dedup_audit_log_instance_id ON dedup_audit_log (instance_id);

-- Create function to log dedup operations
CREATE OR REPLACE FUNCTION log_dedup_operation(
    p_instance_id VARCHAR,
    p_operation VARCHAR,
    p_url TEXT,
    p_content_hash VARCHAR,
    p_duplicate_of_url TEXT,
    p_crawler_name VARCHAR
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO dedup_audit_log (instance_id, operation, url, content_hash, duplicate_of_url, crawler_name)
    VALUES (p_instance_id, p_operation, p_url, p_content_hash, p_duplicate_of_url, p_crawler_name);
END;
$$ LANGUAGE plpgsql;

-- Grant permissions (adjust user as needed)
-- GRANT SELECT, INSERT, UPDATE ON dedup_urls TO intel_user;
-- GRANT SELECT ON dedup_stats TO intel_user;
-- GRANT SELECT ON active_crawlers TO intel_user;
-- GRANT INSERT ON dedup_audit_log TO intel_user;

-- Create retention policy view (for analytics)
CREATE OR REPLACE VIEW dedup_retention_policy AS
SELECT
    '90 days' as retention_period,
    CURRENT_TIMESTAMP - INTERVAL '90 days' as cutoff_date,
    COUNT(*) as eligible_for_deletion
FROM dedup_urls
WHERE expires_at IS NOT NULL
AND expires_at <= CURRENT_TIMESTAMP - INTERVAL '90 days';

EOF

echo "PostgreSQL schema migration created: init_postgres_dedup.sql"
