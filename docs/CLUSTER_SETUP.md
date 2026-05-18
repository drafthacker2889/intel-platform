# Production Cluster Setup Guide

Complete guide to setting up production-grade Elasticsearch and Redis clusters for scale-out architecture.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  Load Balancer / Reverse Proxy              │
│                    (Nginx / HAProxy / Cloud LB)             │
└─────────────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
    ┌───▼───┐            ┌───▼───┐            ┌──▼────┐
    │ Node 1│            │ Node 2│            │ Node 3│
    └───────┘            └───────┘            └───────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
    ┌───▼──────┐         ┌───▼──────┐        ┌───▼──────┐
    │ Data Node│         │ Data Node│        │ Data Node│
    │    (ES)  │         │   (ES)   │        │   (ES)   │
    └──────────┘         └──────────┘        └──────────┘
        │                    │                    │
    ┌───▼──────┐         ┌───▼──────┐        ┌───▼──────┐
    │   Redis  │         │  Redis   │        │  Redis   │
    │ Master 1 │         │ Master 2 │        │ Master 3 │
    └──────────┘         └──────────┘        └──────────┘
        │
    ┌───▼──────────────────────────────────┐
    │    Replica Nodes (Cross-DC)          │
    │  (Optional for HA/Disaster Recovery) │
    └──────────────────────────────────────┘
```

## Part 1: Elasticsearch Cluster Setup

### Single-Node (Development) → 3-Node (Production)

#### 1a. Development Setup (docker-compose.yml)

Single node with basic configuration:

```yaml
elasticsearch:
  image: docker.elastic.co/elasticsearch/elasticsearch:7.17.9
  environment:
    - discovery.type=single-node
    - xpack.security.enabled=false
  ports:
    - "9200:9200"
```

**Limitations:**
- No replication
- No high availability
- Single point of failure

#### 1b. Production Cluster (3-node minimum)

**Requirements:**
- 3 dedicated nodes (master-eligible)
- Each with 2+ vCPU, 4GB+ RAM, 100GB+ storage
- Separate data nodes (optional, for large clusters)
- Network connectivity between nodes

**Docker Compose for 3-node cluster:**

```yaml
version: '3.8'

x-es-env: &es-env
  discovery.seed_hosts: "[es1, es2, es3]"
  cluster.initial_master_nodes: "[es1, es2, es3]"
  xpack.security.enabled: true
  xpack.security.transport.ssl.enabled: true
  xpack.security.transport.ssl.verification_mode: certificate
  xpack.security.transport.ssl.keystore.path: certs/es-nodes.p12
  xpack.security.http.ssl.enabled: true
  xpack.security.http.ssl.keystore.path: certs/es-nodes.p12

services:
  es1:
    image: docker.elastic.co/elasticsearch/elasticsearch:7.17.9
    container_name: es1
    environment:
      <<: *es-env
      node.name: es1
      node.roles: [master, data, ingest]
    volumes:
      - es1_data:/usr/share/elasticsearch/data
      - ./certs/es-nodes.p12:/usr/share/elasticsearch/config/certs/es-nodes.p12:ro
    ports:
      - "9200:9200"
    networks:
      - es_cluster

  es2:
    image: docker.elastic.co/elasticsearch/elasticsearch:7.17.9
    container_name: es2
    environment:
      <<: *es-env
      node.name: es2
      node.roles: [master, data]
    volumes:
      - es2_data:/usr/share/elasticsearch/data
      - ./certs/es-nodes.p12:/usr/share/elasticsearch/config/certs/es-nodes.p12:ro
    networks:
      - es_cluster

  es3:
    image: docker.elastic.co/elasticsearch/elasticsearch:7.17.9
    container_name: es3
    environment:
      <<: *es-env
      node.name: es3
      node.roles: [master, data]
    volumes:
      - es3_data:/usr/share/elasticsearch/data
      - ./certs/es-nodes.p12:/usr/share/elasticsearch/config/certs/es-nodes.p12:ro
    networks:
      - es_cluster

volumes:
  es1_data: {}
  es2_data: {}
  es3_data: {}

networks:
  es_cluster:
    driver: bridge
```

#### 1c. Generate SSL Certificates

```bash
# Create certificate (self-signed for dev, CA-signed for prod)
docker exec es1 elasticsearch-certutil ca -out config/certs/ca.p12 -pass ""
docker exec es1 elasticsearch-certutil cert -ca config/certs/ca.p12 -out config/certs/es-nodes.p12 -pass ""

# Copy to host
docker cp es1:/usr/share/elasticsearch/config/certs/es-nodes.p12 ./certs/
```

#### 1d. Index Lifecycle Management (ILM)

Automatic index management for time-based retention:

```bash
# Create ILM policy (keep indices 30 days, then delete)
curl -u elastic:password -X PUT "localhost:9200/_ilm/policy/threat-intel-policy" \
  -H "Content-Type: application/json" \
  -d '{
    "policy": "threat-intel-policy",
    "phases": {
      "hot": {
        "min_age": "0ms",
        "actions": {
          "rollover": {
            "max_primary_shard_size": "50GB",
            "max_age": "1d"
          }
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "set_priority": {"priority": 50}
        }
      },
      "cold": {
        "min_age": "14d",
        "actions": {
          "set_priority": {"priority": 0}
        }
      },
      "delete": {
        "min_age": "30d",
        "actions": {
          "delete": {}
        }
      }
    }
  }'

# Create index template using ILM
curl -u elastic:password -X PUT "localhost:9200/_index_template/threat-intel" \
  -H "Content-Type: application/json" \
  -d '{
    "index_patterns": ["intel-data-*"],
    "template": {
      "settings": {
        "index.lifecycle.name": "threat-intel-policy",
        "index.lifecycle.rollover_alias": "intel-data",
        "number_of_shards": 3,
        "number_of_replicas": 1
      }
    }
  }'
```

#### 1e. Cluster Health Monitoring

```bash
# Check cluster status
curl -u elastic:password "localhost:9200/_cluster/health"

# Response:
# {
#   "cluster_name": "elasticsearch",
#   "status": "green",
#   "timed_out": false,
#   "number_of_nodes": 3,
#   "number_of_data_nodes": 3,
#   "active_primary_shards": 5,
#   "active_shards": 10,
#   "relocating_shards": 0,
#   "initializing_shards": 0,
#   "unassigned_shards": 0,
#   "delayed_unassigned_shards": 0,
#   "number_of_pending_tasks": 0,
#   "number_of_in_flight_fetch": 0,
#   "task_max_waiting_in_queue_millis": 0,
#   "active_shards_percent_as_number": 100
# }

# List all nodes
curl -u elastic:password "localhost:9200/_nodes?pretty"

# Check shard allocation
curl -u elastic:password "localhost:9200/_cat/shards?v"
```

## Part 2: Redis Cluster Setup

### Single-Node (Development) → Cluster (Production)

#### 2a. Development Setup (docker-compose.yml)

Single Redis instance (no replication):

```yaml
redis:
  image: redis:7-alpine
  command: >
    redis-server
    --requirepass ${REDIS_PASSWORD}
    --appendonly yes
  ports:
    - "6379:6379"
```

**Limitations:**
- No replication, no HA
- AOF persistence can be slow

#### 2b. Production Cluster (Redis Cluster Protocol)

3+ master nodes with automatic failover:

**Prerequisites:**
- Redis 7.0+ (supports cluster)
- 3+ nodes minimum (for quorum)
- Each with 1vCPU, 2GB RAM, 50GB storage

**Setup using docker-compose:**

```yaml
version: '3.8'

services:
  redis1:
    image: redis:7-alpine
    container_name: redis1
    command: >
      redis-server
      --port 6379
      --cluster-enabled yes
      --cluster-config-file nodes.conf
      --cluster-node-timeout 5000
      --appendonly yes
      --requirepass ${REDIS_PASSWORD}
      --masterauth ${REDIS_PASSWORD}
    volumes:
      - redis1_data:/data
    ports:
      - "6379:6379"
      - "16379:16379"
    networks:
      - redis_cluster

  redis2:
    image: redis:7-alpine
    container_name: redis2
    command: >
      redis-server
      --port 6379
      --cluster-enabled yes
      --cluster-config-file nodes.conf
      --cluster-node-timeout 5000
      --appendonly yes
      --requirepass ${REDIS_PASSWORD}
      --masterauth ${REDIS_PASSWORD}
    volumes:
      - redis2_data:/data
    ports:
      - "6380:6379"
      - "16380:16379"
    networks:
      - redis_cluster

  redis3:
    image: redis:7-alpine
    container_name: redis3
    command: >
      redis-server
      --port 6379
      --cluster-enabled yes
      --cluster-config-file nodes.conf
      --cluster-node-timeout 5000
      --appendonly yes
      --requirepass ${REDIS_PASSWORD}
      --masterauth ${REDIS_PASSWORD}
    volumes:
      - redis3_data:/data
    ports:
      - "6381:6379"
      - "16381:16379"
    networks:
      - redis_cluster

  # Replicas for HA
  redis4:
    image: redis:7-alpine
    container_name: redis4
    command: >
      redis-server
      --port 6379
      --cluster-enabled yes
      --cluster-config-file nodes.conf
      --cluster-node-timeout 5000
      --appendonly yes
      --requirepass ${REDIS_PASSWORD}
      --masterauth ${REDIS_PASSWORD}
    volumes:
      - redis4_data:/data
    ports:
      - "6382:6379"
      - "16382:16379"
    networks:
      - redis_cluster

  redis5:
    image: redis:7-alpine
    container_name: redis5
    command: >
      redis-server
      --port 6379
      --cluster-enabled yes
      --cluster-config-file nodes.conf
      --cluster-node-timeout 5000
      --appendonly yes
      --requirepass ${REDIS_PASSWORD}
      --masterauth ${REDIS_PASSWORD}
    volumes:
      - redis5_data:/data
    ports:
      - "6383:6379"
      - "16383:16379"
    networks:
      - redis_cluster

  redis6:
    image: redis:7-alpine
    container_name: redis6
    command: >
      redis-server
      --port 6379
      --cluster-enabled yes
      --cluster-config-file nodes.conf
      --cluster-node-timeout 5000
      --appendonly yes
      --requirepass ${REDIS_PASSWORD}
      --masterauth ${REDIS_PASSWORD}
    volumes:
      - redis6_data:/data
    ports:
      - "6384:6379"
      - "16384:16379"
    networks:
      - redis_cluster

volumes:
  redis1_data: {}
  redis2_data: {}
  redis3_data: {}
  redis4_data: {}
  redis5_data: {}
  redis6_data: {}

networks:
  redis_cluster:
    driver: bridge
```

#### 2c. Initialize Redis Cluster

```bash
# Create cluster (3 masters + 3 replicas)
docker exec redis1 redis-cli -p 6379 -a ${REDIS_PASSWORD} \
  --cluster create \
  redis1:6379 redis2:6379 redis3:6379 \
  redis4:6379 redis5:6379 redis6:6379 \
  --cluster-replicas 1 \
  --cluster-yes

# Verify cluster status
docker exec redis1 redis-cli -p 6379 -a ${REDIS_PASSWORD} cluster info

# Output:
# cluster_state:ok
# cluster_slots_assigned:16384
# cluster_slots_ok:16384
# cluster_slots_pfail:0
# cluster_slots_fail:0
# cluster_known_nodes:6
# cluster_size:3
```

#### 2d. Cluster Client Configuration

Update brain-python and collector-python to use Redis Cluster:

**Python client:**

```python
from rediscluster import RedisCluster

# Connect to cluster (any node will work)
redis = RedisCluster(
    startup_nodes=[
        {"host": "redis1", "port": 6379},
        {"host": "redis2", "port": 6379},
        {"host": "redis3", "port": 6379},
    ],
    decode_responses=True,
    password=os.getenv("REDIS_PASSWORD"),
    skip_full_coverage_check=True,
)

# Use like normal Redis
redis.lpush("raw_html", "...")
value = redis.lpop("raw_html")
```

#### 2e. Cluster Monitoring

```bash
# Check nodes
redis-cli -p 6379 -a PASSWORD cluster nodes

# Output:
# id1 redis1:6379@16379 master - 0 xxx 1 connected 0-5460
# id2 redis2:6379@16379 master - 0 xxx 2 connected 5461-10922
# id3 redis3:6379@16379 master - 0 xxx 3 connected 10923-16383
# id4 redis4:6379@16379 slave id1 - 0 xxx 1 connected
# id5 redis5:6379@16379 slave id2 - 0 xxx 2 connected
# id6 redis6:6379@16379 slave id3 - 0 xxx 3 connected

# Check slots
redis-cli -p 6379 -a PASSWORD cluster slots

# Check memory
redis-cli -p 6379 -a PASSWORD info memory
```

## Part 3: Cross-Datacenter Replication

For disaster recovery across regions:

### Elasticsearch Replication (CCR)

```bash
# Create cross-cluster replication policy
curl -u elastic:password -X PUT "https://leader-es:9200/_ccr/auto_follow/threat-intel" \
  -H "Content-Type: application/json" \
  -d '{
    "remote_cluster": "leader",
    "leader_index_patterns": ["intel-data-*"],
    "follow_index_pattern": "follower-{{leader_index}}"
  }'
```

### Redis Replication (REPLICAOF + SSL)

```bash
# On replica node
redis-cli -p 6379 -a PASSWORD \
  REPLICAOF redis-leader-dc1 6379

# With SSL tunneling (e.g., using SSH or VPN)
redis-cli -p 6379 -a PASSWORD \
  REPLICAOF tunnel-host 6379
```

## Part 4: High Availability (HA) Architecture

### Elasticsearch HA with Kibana

```yaml
kibana:
  image: docker.elastic.co/kibana/kibana:7.17.9
  environment:
    ELASTICSEARCH_HOSTS: http://es1:9200,http://es2:9200,http://es3:9200
    ELASTICSEARCH_USERNAME: kibana_system
    ELASTICSEARCH_PASSWORD: ${KIBANA_PASSWORD}
    # Kibana automatically round-robins across ES nodes
```

### Redis HA with Sentinel (Alternative to Cluster)

For simpler setups, use Redis Sentinel instead of Cluster:

```yaml
sentinel1:
  image: redis:7-alpine
  command: >
    redis-sentinel /etc/redis/sentinel.conf
    --port 26379
  volumes:
    - ./sentinel.conf:/etc/redis/sentinel.conf

sentinel2:
  image: redis:7-alpine
  command: >
    redis-sentinel /etc/redis/sentinel.conf
    --port 26379

sentinel3:
  image: redis:7-alpine
  command: >
    redis-sentinel /etc/redis/sentinel.conf
    --port 26379
```

**sentinel.conf:**

```
port 26379
sentinel monitor mymaster redis-master 6379 2
sentinel auth-pass mymaster ${REDIS_PASSWORD}
sentinel down-after-milliseconds mymaster 5000
sentinel parallel-syncs mymaster 1
```

## Capacity Planning

| Component | Dev | Production (Small) | Production (Large) |
|-----------|-----|-------------------|-------------------|
| **Elasticsearch** |
| Nodes | 1 | 3 | 10+ |
| Shards per index | 1 | 3-5 | 10-20 |
| Replicas | 0 | 1 | 2+ |
| Storage per node | 50GB | 500GB | 2TB+ |
| Memory per node | 2GB | 8GB | 32GB+ |
| **Redis** |
| Masters | 1 | 3 | 6+ |
| Replicas | 0 | 1 per master | 2+ per master |
| Memory per node | 1GB | 4GB | 16GB+ |
| Persistence | RDB | AOF | AOF + RDB snapshots |

## Performance Tuning

### Elasticsearch

```elasticsearch.yml
# Increase JVM heap (match 1/2 of available RAM, max 31GB)
-Xmx16g
-Xms16g

# Disable swapping
bootstrap.memory_lock: true

# Thread pools for bulk indexing
thread_pool.bulk.queue_size: 1000
thread_pool.bulk.size: 8

# Refresh interval (higher = more throughput, higher latency)
index.refresh_interval: 30s
```

### Redis

```conf
# Save less frequently (RDB is expensive)
save 900 1    # Save after 900s if 1+ key changed (default)
save ""       # Disable RDB entirely (use AOF only)

# AOF rewrite threshold
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# Client output buffer
client-output-buffer-limit normal 0 0 0
client-output-buffer-limit replica 256mb 64mb 60
client-output-buffer-limit pubsub 32mb 8mb 60

# Slowlog
slowlog-log-slower-than 10000  # microseconds
slowlog-max-len 128
```

## Monitoring & Alerting

### Elasticsearch Metrics

```bash
# Monitor indices
curl "localhost:9200/_stats/docs,store"

# Monitor JVM
curl "localhost:9200/_nodes/stats/jvm"

# Monitor threadpools
curl "localhost:9200/_nodes/stats/thread_pool"
```

### Redis Metrics

```bash
# Get info
redis-cli info stats
redis-cli info memory
redis-cli info replication

# Slow log
redis-cli slowlog get 10

# Memory fragmentation
redis-cli info stats | grep mem_fragmentation_ratio
```

## Troubleshooting

### Elasticsearch Cluster Status: YELLOW/RED

```bash
# Check unassigned shards
curl "localhost:9200/_cat/shards?h=index,shard,prirep,state,node"

# Allocate shards manually if needed
curl -X POST "localhost:9200/_cluster/reroute?retry_failed=true"
```

### Redis Cluster CLUSTERDOWN

```bash
# Check cluster state
redis-cli cluster info

# Force cluster recovery
redis-cli cluster reset HARD
redis-cli cluster meet <ip> <port>
```

### High CPU Usage

- **Elasticsearch:** Check GC logs, increase JVM heap, reduce refresh interval
- **Redis:** Check slow log, reduce RDB frequency, use pipeline for bulk operations

## Deployment Checklist

- [ ] 3+ nodes per cluster (master quorum)
- [ ] SSL/TLS enabled (production)
- [ ] Authentication configured (strong passwords)
- [ ] Replication enabled (1+ replicas)
- [ ] Backup strategy (ES snapshots, Redis AOF + RDB)
- [ ] Monitoring configured (Prometheus + Grafana)
- [ ] Alerting rules set (cluster health, disk usage, memory)
- [ ] Network segmentation (only allow internal traffic)
- [ ] Resource limits enforced (Docker/Kubernetes)
- [ ] Regular failover tests performed

## References

- [Elasticsearch Official Documentation](https://www.elastic.co/guide/en/elasticsearch/reference/current/)
- [Redis Cluster Specification](https://redis.io/docs/management/sentinel/)
- [Redis HA Best Practices](https://redis.io/docs/management/high-availability/)
