# PostgreSQL and Milvus Observability Guide

This document provides specific instructions for monitoring PostgreSQL and Milvus standalone servers in the Plugged.in ecosystem.

## Table of Contents

- [PostgreSQL Monitoring](#postgresql-monitoring)
- [Milvus Monitoring](#milvus-monitoring)
- [Integration with Grafana](#integration-with-grafana)
- [Alerting](#alerting)

---

## PostgreSQL Monitoring

### Overview

PostgreSQL monitoring is handled by `postgres_exporter`, which exposes database metrics in Prometheus format.

### Setup

#### 1. Configure PostgreSQL Connection

Edit `.env` file:

```bash
# PostgreSQL connection string
# Format: postgresql://user:password@host:port/database
POSTGRES_EXPORTER_DSN=postgresql://postgres:yourpassword@your-postgres-host:5432/pluggedin

# Example for local PostgreSQL
POSTGRES_EXPORTER_DSN=postgresql://postgres:password@localhost:5432/pluggedin

# Example for remote PostgreSQL (production)
POSTGRES_EXPORTER_DSN=postgresql://postgres:password@185.96.168.246:5432/v30_beta
```

#### 2. Start PostgreSQL Exporter

The exporter is already configured in `docker-compose.yml`. Start it:

```bash
docker-compose up -d postgres-exporter
```

#### 3. Verify Metrics

Check if metrics are being collected:

```bash
# Check exporter is running
docker ps | grep postgres-exporter

# View metrics
curl http://localhost:9187/metrics

# Check Prometheus is scraping
curl http://localhost:9090/api/v1/query?query=pg_up
```

### Available PostgreSQL Metrics

#### Connection Metrics

- `pg_up` - PostgreSQL server availability (1 = up, 0 = down)
- `pg_stat_activity_count` - Number of connections by state
- `pg_stat_activity_max_tx_duration` - Longest running transaction
- `pg_settings_max_connections` - Maximum allowed connections

#### Database Metrics

- `pg_database_size_bytes` - Database size in bytes
- `pg_stat_database_tup_inserted` - Rows inserted
- `pg_stat_database_tup_updated` - Rows updated
- `pg_stat_database_tup_deleted` - Rows deleted
- `pg_stat_database_blks_read` - Disk blocks read
- `pg_stat_database_blks_hit` - Blocks found in cache (buffer hit ratio)

#### Table Metrics

- `pg_stat_user_tables_n_tup_ins` - Rows inserted per table
- `pg_stat_user_tables_n_tup_upd` - Rows updated per table
- `pg_stat_user_tables_n_tup_del` - Rows deleted per table
- `pg_stat_user_tables_seq_scan` - Sequential scans
- `pg_stat_user_tables_idx_scan` - Index scans

#### Performance Metrics

- `pg_stat_bgwriter_buffers_alloc` - Buffers allocated
- `pg_stat_bgwriter_buffers_checkpoint` - Buffers written during checkpoints
- `pg_locks_count` - Number of locks by type
- `pg_stat_replication_lag` - Replication lag in seconds

### PromQL Query Examples

```promql
# Connection usage percentage
(pg_stat_activity_count / pg_settings_max_connections) * 100

# Buffer hit ratio (should be > 90%)
100 * pg_stat_database_blks_hit / (pg_stat_database_blks_hit + pg_stat_database_blks_read)

# Database size growth rate (per hour)
rate(pg_database_size_bytes[1h])

# Slow queries (transactions > 60 seconds)
pg_stat_activity_max_tx_duration > 60

# Index scan ratio (should be > 95%)
100 * sum(pg_stat_user_tables_idx_scan) / (sum(pg_stat_user_tables_idx_scan) + sum(pg_stat_user_tables_seq_scan))
```

### Recommended Alerts

Already configured in `prometheus/rules/alerts.yml`:

```yaml
- alert: PostgreSQLDown
  expr: pg_up == 0
  for: 1m
  severity: critical

- alert: HighDatabaseConnections
  expr: (pg_stat_activity_count / pg_settings_max_connections) > 0.8
  for: 5m
  severity: warning

- alert: SlowQueries
  expr: pg_stat_activity_max_tx_duration > 60
  for: 5m
  severity: warning
```

### Grafana Dashboard

Import the PostgreSQL dashboard:

1. Go to Grafana → Dashboards → Import
2. Use dashboard ID: `9628` (PostgreSQL Database)
3. Select Prometheus datasource
4. Click Import

Or use the custom dashboard in `grafana/dashboards/databases.json`.

---

## Milvus Monitoring

### Overview

Milvus exposes Prometheus metrics natively. You need to configure Prometheus to scrape the Milvus metrics endpoint.

### Setup

#### 1. Enable Milvus Metrics

Edit your Milvus configuration (`milvus.yaml`):

```yaml
metrics:
  # Enable metrics
  enable: true
  # Metrics port (default: 9091)
  port: 9091
  # Metrics path (default: /metrics)
  path: /metrics
```

Restart Milvus:

```bash
docker-compose restart milvus-standalone
# or
systemctl restart milvus
```

#### 2. Configure Prometheus to Scrape Milvus

Add to `prometheus/prometheus.yml`:

```yaml
scrape_configs:
  # Milvus Standalone
  - job_name: 'milvus'
    static_configs:
      - targets: ['milvus-host:9091']  # Replace with your Milvus host
        labels:
          service: 'milvus'
          instance: 'standalone'
          environment: 'production'
    scrape_interval: 30s
    scrape_timeout: 10s

  # If using Milvus Cluster, add each component:
  # - job_name: 'milvus-rootcoord'
  #   static_configs:
  #     - targets: ['rootcoord-host:9091']
  #
  # - job_name: 'milvus-datanode'
  #   static_configs:
  #     - targets: ['datanode-host:9091']
  #
  # - job_name: 'milvus-querynode'
  #   static_configs:
  #     - targets: ['querynode-host:9091']
  #
  # - job_name: 'milvus-indexnode'
  #   static_configs:
  #     - targets: ['indexnode-host:9091']
```

Reload Prometheus:

```bash
curl -X POST http://localhost:9090/-/reload
# or restart
docker-compose restart prometheus
```

#### 3. Verify Metrics

```bash
# Check Milvus metrics endpoint
curl http://milvus-host:9091/metrics

# Check Prometheus is scraping
curl http://localhost:9090/api/v1/query?query=milvus_up
```

### Available Milvus Metrics

#### System Metrics

- `milvus_up` - Milvus service availability
- `process_cpu_seconds_total` - CPU usage
- `process_resident_memory_bytes` - Memory usage
- `process_open_fds` - Open file descriptors

#### Collection Metrics

- `milvus_collection_num` - Number of collections
- `milvus_collection_row_count` - Row count per collection
- `milvus_collection_index_task_num` - Indexing tasks

#### Query Metrics

- `milvus_search_request_count` - Search request count
- `milvus_search_latency_seconds` - Search latency histogram
- `milvus_query_request_count` - Query request count
- `milvus_query_latency_seconds` - Query latency histogram

#### Data Metrics

- `milvus_insert_request_count` - Insert request count
- `milvus_insert_latency_seconds` - Insert latency
- `milvus_delete_request_count` - Delete request count
- `milvus_flush_request_count` - Flush request count

#### Cache Metrics

- `milvus_cache_hit_ratio` - Cache hit ratio
- `milvus_cache_size_bytes` - Cache size

#### Storage Metrics

- `milvus_storage_size_bytes` - Storage usage per collection
- `milvus_segment_num` - Number of segments

### PromQL Query Examples

```promql
# Average search latency (p95)
histogram_quantile(0.95, rate(milvus_search_latency_seconds_bucket[5m]))

# Search QPS
rate(milvus_search_request_count[1m])

# Cache hit ratio
milvus_cache_hit_ratio

# Collection row counts
milvus_collection_row_count

# Storage usage per collection
milvus_storage_size_bytes

# Memory usage
process_resident_memory_bytes{job="milvus"}

# Insert throughput (rows/sec)
rate(milvus_insert_request_count[1m])
```

### Recommended Alerts

Add to `prometheus/rules/alerts.yml`:

```yaml
groups:
  - name: milvus
    interval: 30s
    rules:
      # Milvus Down
      - alert: MilvusDown
        expr: up{job="milvus"} == 0
        for: 2m
        labels:
          severity: critical
          category: availability
        annotations:
          summary: "Milvus is down"
          description: "Milvus instance {{ $labels.instance }} has been down for more than 2 minutes."

      # High Search Latency
      - alert: MilvusHighSearchLatency
        expr: |
          histogram_quantile(0.95,
            rate(milvus_search_latency_seconds_bucket[5m])
          ) > 2
        for: 5m
        labels:
          severity: warning
          category: performance
        annotations:
          summary: "High Milvus search latency"
          description: "Milvus p95 search latency is above 2 seconds (current: {{ $value | humanizeDuration }})"

      # Low Cache Hit Ratio
      - alert: MilvusLowCacheHitRatio
        expr: milvus_cache_hit_ratio < 0.8
        for: 10m
        labels:
          severity: warning
          category: performance
        annotations:
          summary: "Low Milvus cache hit ratio"
          description: "Milvus cache hit ratio is below 80% (current: {{ $value | humanizePercentage }})"

      # High Memory Usage
      - alert: MilvusHighMemory
        expr: |
          process_resident_memory_bytes{job="milvus"} /
          (1024 * 1024 * 1024) > 8
        for: 5m
        labels:
          severity: warning
          category: resources
        annotations:
          summary: "High Milvus memory usage"
          description: "Milvus is using more than 8GB memory (current: {{ $value | humanize }}GB)"
```

### Grafana Dashboard

Create a custom Milvus dashboard:

```json
{
  "title": "Milvus Monitoring",
  "panels": [
    {
      "title": "Search QPS",
      "targets": [
        {
          "expr": "rate(milvus_search_request_count[1m])"
        }
      ]
    },
    {
      "title": "Search Latency (p95)",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(milvus_search_latency_seconds_bucket[5m]))"
        }
      ]
    },
    {
      "title": "Cache Hit Ratio",
      "targets": [
        {
          "expr": "milvus_cache_hit_ratio"
        }
      ]
    },
    {
      "title": "Collection Row Counts",
      "targets": [
        {
          "expr": "milvus_collection_row_count"
        }
      ]
    }
  ]
}
```

---

## Integration with Grafana

### Setup Database Dashboard

1. **PostgreSQL**:
   - Import dashboard ID `9628`
   - Or use `grafana/dashboards/databases.json`

2. **Milvus**:
   - Create custom dashboard using examples above
   - Or import from Milvus documentation

### Unified View

Create a single dashboard showing both PostgreSQL and Milvus:

```
+----------------------------------+
|     Database Health Overview     |
+----------------------------------+
| PostgreSQL Status | Milvus Status|
+----------------------------------+
|   PG Connections  | Vector Search|
|                   |   Latency    |
+----------------------------------+
|   Slow Queries    | Cache Hit    |
|                   |   Ratio      |
+----------------------------------+
```

---

## Alerting

### PostgreSQL Critical Alerts

1. **Database Down**: Immediate notification
2. **Connection Pool Exhausted**: Warning at 80%, critical at 95%
3. **Slow Queries**: Queries > 60 seconds
4. **Replication Lag**: Lag > 30 seconds

### Milvus Critical Alerts

1. **Service Down**: Immediate notification
2. **High Search Latency**: p95 > 2 seconds
3. **Low Cache Hit Ratio**: < 80%
4. **Memory Pressure**: > 8GB usage

### Alert Channels

Configure in `.env`:

```bash
# Slack webhook
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Email
ALERT_EMAIL=ops@plugged.in

# PagerDuty
PAGERDUTY_KEY=your-pagerduty-key
```

---

## Troubleshooting

### PostgreSQL Exporter Issues

**Problem**: `pg_up` is 0

**Solutions**:
1. Check connection string: `docker logs postgres-exporter`
2. Verify PostgreSQL is accessible: `psql -h host -U user -d database`
3. Check firewall rules
4. Verify credentials in `.env`

### Milvus Metrics Not Appearing

**Problem**: No Milvus metrics in Prometheus

**Solutions**:
1. Verify metrics are enabled: `curl http://milvus-host:9091/metrics`
2. Check Prometheus configuration: `prometheus/prometheus.yml`
3. Reload Prometheus: `curl -X POST http://localhost:9090/-/reload`
4. Check Prometheus targets: http://localhost:9090/targets

---

## Best Practices

### PostgreSQL

1. **Connection Pooling**: Use PgBouncer or connection pooling in your app
2. **Index Optimization**: Monitor index usage ratio (should be > 95%)
3. **Vacuum**: Ensure autovacuum is running properly
4. **Backup Monitoring**: Track last backup timestamp

### Milvus

1. **Collection Design**: Monitor collection sizes and segment counts
2. **Index Tuning**: Optimize index parameters for your use case
3. **Cache Configuration**: Adjust cache size based on working set
4. **Query Optimization**: Monitor and optimize slow queries

---

## Next Steps

1. Configure PostgreSQL exporter with your database credentials
2. Enable Milvus metrics endpoint
3. Add scrape configs to Prometheus
4. Import or create Grafana dashboards
5. Configure alerts for critical metrics
6. Set up notification channels (Slack, email, PagerDuty)

## Resources

- [PostgreSQL Exporter](https://github.com/prometheus-community/postgres_exporter)
- [Milvus Monitoring](https://milvus.io/docs/monitor.md)
- [PostgreSQL Monitoring Best Practices](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [Milvus Performance Tuning](https://milvus.io/docs/performance_faq.md)
