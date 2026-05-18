# Multi-Instance Crawler Orchestration Guide

Complete guide to running multiple collector-python instances with centralized work queues and deduplication.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              Nginx Load Balancer                         │
│     (Health checks, metrics aggregation, proxy)         │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
    ┌───▼────┐     ┌───▼────┐     ┌──▼────┐
    │Crawler │     │Crawler │     │Crawler│  ← Scale to N instances
    │  Py 1  │     │  Py 2  │     │ Py N  │
    └────┬───┘     └────┬───┘     └───┬───┘
         │              │              │
         └──────────────┼──────────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
      ┌──▼─────┐    ┌───▼───┐     ┌──▼──────┐
      │  Tor   │    │ Redis │     │Brain-   │
      │ Proxy  │    │Cluster│     │Python   │
      │(shared)│    │ (work  │     │(single) │
      └────────┘    │ queue +│     └────┬────┘
                    │ dedup) │          │
                    └───┬────┘          │
                        │          ┌────▼────┐
                        │     ┌────▼──┐      │
                        │     │Elastic│Neo4j │
                        │     │search │      │
                        │     └───────┴──────┘
                        │
                   ┌────▼─────┐
                   │Persistent│
                   │   Data    │
                   │(AOF, RDB) │
                   └───────────┘
```

## Quick Start

### 1. Start base infrastructure (single instance)

```bash
# Use default docker-compose.yml for single instance
docker compose up
```

### 2. Scale to multiple crawlers

```bash
# Scale collector-python to 5 instances
docker compose -f docker-compose.scale.yml up --scale collector-python=5

# Or step-by-step:
docker compose -f docker-compose.scale.yml up -d
docker compose -f docker-compose.scale.yml up -d --scale collector-python=5
```

### 3. Verify cluster

```bash
# Check all containers
docker ps | grep collector

# Check Redis queue depth
redis-cli -p 6379 -a PASSWORD LLEN raw_html

# Check dedup stats
redis-cli -p 6379 -a PASSWORD KEYS "crawled_url:*" | wc -l

# Monitor throughput
redis-cli -p 6379 -a PASSWORD INFO stats | grep instantaneous_ops_per_sec
```

## Running Multi-Instance Crawler

### Using docker-compose.scale.yml

```bash
# Start infrastructure + 3 collectors
docker compose -f docker-compose.scale.yml up --scale collector-python=3 -d

# Logs from all collectors
docker compose -f docker-compose.scale.yml logs -f collector-python

# Add 2 more collectors dynamically
docker compose -f docker-compose.scale.yml up --scale collector-python=5 -d

# Stop all (but keep data)
docker compose -f docker-compose.scale.yml down

# Clean everything (including data)
docker compose -f docker-compose.scale.yml down -v
```

### Scaling Strategies

#### Strategy 1: CPU-Bound Scaling

For I/O-heavy crawling (downloading pages), scale to # of CPU cores:

```bash
# 8-core machine
docker compose -f docker-compose.scale.yml up --scale collector-python=8 -d
```

**Pros:** Good CPU utilization, simple
**Cons:** May overwhelm Redis/network at high concurrency

#### Strategy 2: Memory-Constrained Scaling

Each collector uses ~1GB. For 16GB machine:

```bash
# Safe limit: 10-12 collectors (leaving 4-6GB for other services)
docker compose -f docker-compose.scale.yml up --scale collector-python=10 -d
```

#### Strategy 3: Queue-Depth Scaling

Dynamically scale based on backlog:

```bash
#!/bin/bash
# Auto-scale script
while true; do
    QUEUE_DEPTH=$(redis-cli -p 6379 -a PASSWORD LLEN raw_html)
    CURRENT=$(docker ps -f "name=collector-python" --format "{{.Names}}" | wc -l)
    
    if (( QUEUE_DEPTH > 1000 && CURRENT < 10 )); then
        echo "Queue depth $QUEUE_DEPTH > 1000, scaling up"
        docker compose -f docker-compose.scale.yml up --scale collector-python=$((CURRENT + 2)) -d
    elif (( QUEUE_DEPTH < 100 && CURRENT > 2 )); then
        echo "Queue depth $QUEUE_DEPTH < 100, scaling down"
        docker compose -f docker-compose.scale.yml up --scale collector-python=$((CURRENT - 1)) -d
    fi
    
    sleep 30
done
```

## Centralized Deduplication

All instances share the same Redis dedup store:

### How it Works

```
Instance 1                Instance 2                Instance 3
    │                         │                         │
    ├─ Fetch page URL A       ├─ Fetch page URL B       ├─ Fetch page URL C
    │  Check dedup: MISS      │  Check dedup: MISS      │  Check dedup: MISS
    │  Download page          │  Download page          │  Download page
    │  Hash content           │  Hash content           │  Hash content
    │  Store hash in Redis    │  Store hash in Redis    │  Store hash in Redis
    │                         │                         │
    └─ Parse links: A1, A2    └─ Parse links: B1, B2    └─ Parse links: C1, C2
       Push A1, A2 to queue      Push B1, B2 to queue      Push C1, C2 to queue
       
       Later...
    ├─ Fetch page URL A1      ├─ Fetch page URL B1      ├─ Fetch page URL C1
    │  Check dedup: HIT       │  Check dedup: HIT       │  Check dedup: HIT (from Instance 1)
    │  (Skip, already crawled)│  (Skip, already crawled)│  (Skip, already crawled)
    │  Continue to next       │  Continue to next       │  Continue to next
```

### Redis Dedup Keys

```bash
# URL tracking (already crawled)
redis-cli -p 6379 -a PASSWORD GET crawled_url:https://example.com/page
# Returns: "1" if crawled, nil if not

# Content hash tracking (already indexed)
redis-cli -p 6379 -a PASSWORD GET content_hash:abc123def456
# Returns: "2024-05-17T10:30:00Z" (timestamp when indexed)

# TTL: 90 days (7,776,000 seconds)
redis-cli -p 6379 -a PASSWORD TTL crawled_url:https://example.com/page
```

### Dedup Statistics

```bash
# Count crawled URLs
redis-cli -p 6379 -a PASSWORD DBSIZE | head -1

# Sample recent crawls
redis-cli -p 6379 -a PASSWORD RANDOMKEY

# Memory usage
redis-cli -p 6379 -a PASSWORD INFO memory
# Total used: ~500MB for 50K deduplicated URLs
```

## Load Balancing

### Nginx Upstream Load Balancer

The Nginx container (`nginx_lb`) provides:

1. **Health checks** — Validates each collector is running
2. **Metrics aggregation** — Collects stats from all instances
3. **Request distribution** — Load-balances across healthy instances
4. **Proxy services** — Direct access to Elasticsearch, Neo4j, Kibana

### Accessing Services

```bash
# Collector health (round-robin across instances)
curl http://localhost/health

# All collectors' metrics (aggregated)
curl http://localhost/metrics

# Elasticsearch (proxied)
curl http://localhost/es/_cluster/health

# Neo4j (proxied)
curl http://localhost/neo4j/db/neo4j/

# Kibana (proxied)
curl http://localhost/kibana/app/kibana
```

## Monitoring Multi-Instance Cluster

### Real-Time Queue Monitoring

```bash
#!/bin/bash
# Monitor queue depth in real-time
watch -n 1 "redis-cli -p 6379 -a PASSWORD LLEN raw_html"
```

### Per-Instance Metrics

```bash
# Get metrics from each collector
for i in {1..3}; do
  echo "=== Collector $i ==="
  docker logs intel_collector_py_$i 2>/dev/null | tail -5
done
```

### Aggregate Statistics

```bash
# Total documents crawled (across all instances)
redis-cli -p 6379 -a PASSWORD GET crawler:pages_total

# Total dedup hits (cost savings)
redis-cli -p 6379 -a PASSWORD GET crawler:dedup_hits_total

# Crawl rate (docs/second)
redis-cli -p 6379 -a PASSWORD GET crawler:crawl_rate
```

## Failure Handling

### Instance Failure

**Scenario:** Collector instance crashes or becomes unresponsive

**Automatic handling:**
- Nginx removes unhealthy instance from load balancer
- Work already fetched is lost (tolerable for web crawling)
- Other instances continue processing queue
- Dead container is restarted by Docker `restart: unless-stopped`

**Example:**

```bash
# Simulate crash of one instance
docker kill intel_collector_py_2

# Nginx automatically routes around it
curl http://localhost/health  # Still returns OK from other instances

# Auto-restart happens
sleep 10 && docker ps | grep collector  # Shows recreated instance
```

### Redis Failure

**Scenario:** Redis crashes, losing queue state

**Prevention:**
- AOF persistence: All queue operations logged to disk
- RDB snapshots: Full backup every 60 seconds
- Cluster mode (see CLUSTER_SETUP.md): 3+ nodes with replication

**Recovery:**

```bash
# Data is restored from AOF on restart
docker compose -f docker-compose.scale.yml down
docker compose -f docker-compose.scale.yml up

# All queued URLs are restored
redis-cli -p 6379 -a PASSWORD LLEN raw_html  # Should match pre-crash value
```

### Network Partition

**Scenario:** Collectors can't reach Redis (network issue)

**Behavior:**
- Collectors re-attempt connection every 5 seconds
- Exponential backoff: 5s, 10s, 20s, 30s, ...
- Errors logged to stderr
- On reconnect, processing resumes

## Performance Tuning

### Redis Optimization

```bash
# Increase memory to 4GB (for larger dedup stores)
docker compose -f docker-compose.scale.yml down
# Edit docker-compose.scale.yml: --maxmemory 4gb
docker compose -f docker-compose.scale.yml up -d

# Check memory usage
redis-cli -p 6379 -a PASSWORD INFO memory | grep used_memory_human
```

### Collector Optimization

```bash
# Reduce playwright timeout for faster failures
docker compose -f docker-compose.scale.yml down
# Edit docker-compose.scale.yml: PLAYWRIGHT_TIMEOUT_MS=15000
docker compose -f docker-compose.scale.yml up --scale collector-python=5 -d
```

### Elasticsearch Optimization

```bash
# Increase bulk indexing queue
docker compose -f docker-compose.scale.yml down
# Edit docker-compose.scale.yml: thread_pool.bulk.queue_size=2000
docker compose -f docker-compose.scale.yml up -d
```

## Capacity Planning

| Metric | Small (5 collectors) | Medium (10) | Large (20+) |
|--------|----------------------|------------|------------|
| **Throughput** |
| Pages/minute | 300-500 | 600-1000 | 1200-2000 |
| Links extracted/minute | 1500-2500 | 3000-5000 | 6000-10K |
| **Storage** |
| Queue backlog | ~10K URLs | ~50K URLs | ~100K URLs |
| Dedup store (Redis) | 500MB | 1GB | 2-3GB |
| ES index growth/day | 20-30GB | 50-80GB | 100-150GB |
| **Resources** |
| Total RAM | 10GB | 15GB | 25GB+ |
| Total CPU | 5 cores | 10 cores | 20 cores |
| Network bandwidth | 50Mbps | 100Mbps | 200Mbps+ |

## A/B Testing

Run different collector configurations in parallel:

```bash
# Create separate compose file with different settings
# docker-compose.experimental.yml
services:
  collector-python-experimental:
    # ... same as collector-python but with:
    environment:
      - CAPTCHA_SOLVER_ENABLED=false  # Disable CAPTCHA to test impact
      - PLAYWRIGHT_TIMEOUT_MS=10000   # Faster timeout
      - ...

# Run both versions
docker compose up -d  # Original (3 instances)
docker compose -f docker-compose.experimental.yml up --scale collector-python-experimental=3 -d

# Compare metrics in Redis
redis-cli GET metrics:crawl_rate_original
redis-cli GET metrics:crawl_rate_experimental
```

## Upgrading Collector Version

Rolling update without downtime:

```bash
# 1. Rebuild new image
docker compose -f docker-compose.scale.yml build collector-python

# 2. Stop instances one at a time
for i in {1..3}; do
    echo "Updating collector $i..."
    docker compose -f docker-compose.scale.yml up --scale collector-python=$((3-i+1)) -d
    sleep 30  # Let other instances drain queue
done

# 3. Verify all healthy
docker compose -f docker-compose.scale.yml ps
```

## Troubleshooting

### "Collectors not consuming queue"

```bash
# Check logs
docker compose -f docker-compose.scale.yml logs -f collector-python

# Check Redis connectivity
docker exec $(docker ps -qf "name=collector") redis-cli -h redis ping

# Check Tor connectivity
docker exec $(docker ps -qf "name=collector") curl -x socks5://tor-proxy:9050 https://icanhazip.com
```

### "High memory usage"

```bash
# Check memory per container
docker stats --no-stream | grep collector

# Reduce instance count or increase container limits
docker compose -f docker-compose.scale.yml down
# Edit: mem_limit: 1500m
docker compose -f docker-compose.scale.yml up --scale collector-python=5 -d
```

### "Skewed work distribution"

```bash
# Check if all instances are consuming equally
for container in $(docker ps -qf "name=collector"); do
    echo "Instance: $container"
    docker logs $container 2>&1 | grep "processed" | tail -1
done
```

## Scaling Beyond Docker Compose

For Kubernetes or cloud deployments:

### Kubernetes StatefulSet

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: collector-python
spec:
  replicas: 5  # Scale this value
  serviceName: collector-python
  selector:
    matchLabels:
      app: collector-python
  template:
    metadata:
      labels:
        app: collector-python
    spec:
      containers:
      - name: collector-python
        image: myregistry/collector-python:latest
        env:
        - name: REDIS_HOST
          value: redis-service
        - name: TOR_PROXY
          value: tor-proxy-service:9050
        resources:
          requests:
            memory: "1Gi"
            cpu: "1"
          limits:
            memory: "1.2Gi"
            cpu: "1.2"
        livenessProbe:
          httpGet:
            path: /health
            port: 8081
          initialDelaySeconds: 10
          periodSeconds: 10
```

## References

- [Docker Compose Scaling](https://docs.docker.com/compose/compose-file/compose-file-v3/#scale)
- [Redis Replication](https://redis.io/docs/management/replication/)
- [Kubernetes Horizontal Pod Autoscaling](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
