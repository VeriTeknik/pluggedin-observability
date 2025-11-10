# Standalone PostgreSQL Monitoring Setup

This guide shows how to monitor a standalone PostgreSQL server (non-Docker) and send metrics to monitoring.plugged.in.

## Architecture

```
┌──────────────────────────────────────┐
│  PostgreSQL Server (Standalone)      │
│                                       │
│  ┌────────────────────────────────┐  │
│  │      PostgreSQL 15+            │  │
│  │      Port: 5432                │  │
│  └────────────┬───────────────────┘  │
│               │ localhost            │
│               │ connection           │
│  ┌────────────▼───────────────────┐  │
│  │   postgres_exporter            │  │
│  │   Port: 9187                   │  │
│  │   /metrics endpoint            │  │
│  └────────────┬───────────────────┘  │
│               │                       │
└───────────────┼───────────────────────┘
                │
                │ HTTP Scrape
                │ every 30s
                │
┌───────────────▼───────────────────────┐
│  Monitoring Server                    │
│  (monitoring.plugged.in)              │
│                                       │
│  ┌─────────────────────────────────┐ │
│  │        Prometheus               │ │
│  │        Port: 9090               │ │
│  │                                 │ │
│  │  Scrapes postgres_exporter      │ │
│  │  http://PG_SERVER_IP:9187       │ │
│  └─────────────────────────────────┘ │
│                                       │
│  ┌─────────────────────────────────┐ │
│  │         Grafana                 │ │
│  │  Pre-built PostgreSQL           │ │
│  │  dashboards available           │ │
│  └─────────────────────────────────┘ │
└───────────────────────────────────────┘
```

## Prerequisites

- Root or sudo access on PostgreSQL server
- PostgreSQL 9.4+ (tested with 15+)
- Network connectivity between PostgreSQL server and monitoring server
- PostgreSQL user with monitoring permissions

## Part 1: Create PostgreSQL Monitoring User

### 1.1 Connect to PostgreSQL

```bash
# SSH to PostgreSQL server
ssh user@your-postgres-server

# Connect as postgres superuser
sudo -u postgres psql
```

### 1.2 Create Monitoring User

```sql
-- Create a dedicated monitoring user with limited permissions
CREATE USER postgres_exporter WITH PASSWORD 'SECURE_PASSWORD_HERE';

-- Grant connection privileges
GRANT CONNECT ON DATABASE postgres TO postgres_exporter;

-- For PostgreSQL 10+: Grant pg_monitor role (recommended)
GRANT pg_monitor TO postgres_exporter;

-- For PostgreSQL 9.x (if pg_monitor not available):
-- GRANT SELECT ON pg_stat_database TO postgres_exporter;
-- GRANT SELECT ON pg_stat_replication TO postgres_exporter;

-- Allow monitoring user to see all databases
\c postgres
GRANT USAGE ON SCHEMA public TO postgres_exporter;

-- Repeat for each database you want to monitor
\c your_app_database
GRANT USAGE ON SCHEMA public TO postgres_exporter;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO postgres_exporter;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO postgres_exporter;

-- For monitoring replication (optional, if using replication)
GRANT EXECUTE ON FUNCTION pg_ls_waldir() TO postgres_exporter;

-- Exit psql
\q
```

### 1.3 Configure pg_hba.conf

Allow postgres_exporter to connect locally:

```bash
# Edit pg_hba.conf
sudo nano /etc/postgresql/15/main/pg_hba.conf
# Or find your pg_hba.conf location:
# sudo -u postgres psql -c "SHOW hba_file;"
```

Add this line (before the "local all all" line):

```
# TYPE  DATABASE        USER                ADDRESS                 METHOD
local   all             postgres_exporter                           md5
host    all             postgres_exporter   127.0.0.1/32            md5
host    all             postgres_exporter   ::1/128                 md5
```

Reload PostgreSQL configuration:

```bash
sudo systemctl reload postgresql
# Or: sudo -u postgres psql -c "SELECT pg_reload_conf();"
```

### 1.4 Test Monitoring User

```bash
# Test connection
psql -U postgres_exporter -d postgres -h localhost -W

# Should prompt for password and connect successfully
# If successful, exit with \q
```

## Part 2: Install postgres_exporter

### 2.1 Download and Install

```bash
# Create directory for postgres_exporter
sudo mkdir -p /opt/postgres_exporter
cd /opt/postgres_exporter

# Download latest version (check https://github.com/prometheus-community/postgres_exporter/releases)
POSTGRES_EXPORTER_VERSION="0.15.0"
sudo wget https://github.com/prometheus-community/postgres_exporter/releases/download/v${POSTGRES_EXPORTER_VERSION}/postgres_exporter-${POSTGRES_EXPORTER_VERSION}.linux-amd64.tar.gz

# Extract
sudo tar xvf postgres_exporter-${POSTGRES_EXPORTER_VERSION}.linux-amd64.tar.gz
sudo mv postgres_exporter-${POSTGRES_EXPORTER_VERSION}.linux-amd64/postgres_exporter .
sudo chmod +x postgres_exporter

# Clean up
sudo rm -rf postgres_exporter-${POSTGRES_EXPORTER_VERSION}.linux-amd64*

# Create symlink
sudo ln -sf /opt/postgres_exporter/postgres_exporter /usr/local/bin/postgres_exporter

# Verify installation
postgres_exporter --version
```

### 2.2 Create Configuration File

```bash
# Create environment file for configuration
sudo mkdir -p /etc/postgres_exporter
sudo nano /etc/postgres_exporter/postgres_exporter.env
```

Add the following content:

```bash
# PostgreSQL connection string
# Format: postgresql://username:password@host:port/database?sslmode=disable
DATA_SOURCE_NAME="postgresql://postgres_exporter:SECURE_PASSWORD_HERE@localhost:5432/postgres?sslmode=disable"

# If you have multiple databases, you can use a URI with multiple db params
# DATA_SOURCE_NAME="postgresql://postgres_exporter:SECURE_PASSWORD_HERE@localhost:5432/?sslmode=disable"

# Disable default metrics that might be too verbose (optional)
# PG_EXPORTER_DISABLE_DEFAULT_METRICS=false

# Disable settings metrics (contains passwords in some cases)
PG_EXPORTER_DISABLE_SETTINGS_METRICS=true

# Custom query file (optional, for advanced metrics)
# PG_EXPORTER_EXTEND_QUERY_PATH=/etc/postgres_exporter/queries.yaml

# Log level (debug, info, warn, error)
PG_EXPORTER_LOG_LEVEL=info

# Web listen address
PG_EXPORTER_WEB_LISTEN_ADDRESS=:9187

# Telemetry path
PG_EXPORTER_WEB_TELEMETRY_PATH=/metrics
```

**Important**: Replace `SECURE_PASSWORD_HERE` with the actual password you set for postgres_exporter user.

Set correct permissions:

```bash
sudo chmod 600 /etc/postgres_exporter/postgres_exporter.env
sudo chown root:root /etc/postgres_exporter/postgres_exporter.env
```

### 2.3 Create Custom Queries (Optional)

If you want additional custom metrics:

```bash
sudo nano /etc/postgres_exporter/queries.yaml
```

Example custom queries:

```yaml
# Custom queries for specific monitoring needs
pg_database_size:
  query: "SELECT pg_database.datname, pg_database_size(pg_database.datname) as size_bytes FROM pg_database"
  master: true
  metrics:
    - datname:
        usage: "LABEL"
        description: "Name of the database"
    - size_bytes:
        usage: "GAUGE"
        description: "Size of the database in bytes"

pg_table_sizes:
  query: |
    SELECT
      schemaname,
      tablename,
      pg_total_relation_size(schemaname||'.'||tablename) AS total_bytes,
      pg_relation_size(schemaname||'.'||tablename) AS table_bytes,
      pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename) AS index_bytes
    FROM pg_tables
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
    ORDER BY total_bytes DESC
    LIMIT 20
  metrics:
    - schemaname:
        usage: "LABEL"
        description: "Schema name"
    - tablename:
        usage: "LABEL"
        description: "Table name"
    - total_bytes:
        usage: "GAUGE"
        description: "Total table size including indexes"
    - table_bytes:
        usage: "GAUGE"
        description: "Table size without indexes"
    - index_bytes:
        usage: "GAUGE"
        description: "Index size"

pg_replication_lag:
  query: |
    SELECT
      CASE
        WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn() THEN 0
        ELSE EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp())
      END AS lag_seconds
  master: false
  metrics:
    - lag_seconds:
        usage: "GAUGE"
        description: "Replication lag in seconds"
```

Enable custom queries in the env file:

```bash
sudo nano /etc/postgres_exporter/postgres_exporter.env
# Uncomment:
# PG_EXPORTER_EXTEND_QUERY_PATH=/etc/postgres_exporter/queries.yaml
```

## Part 3: Create Systemd Service

### 3.1 Create Service File

```bash
sudo nano /etc/systemd/system/postgres_exporter.service
```

Add the following content:

```ini
[Unit]
Description=PostgreSQL Prometheus Exporter
Documentation=https://github.com/prometheus-community/postgres_exporter
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=postgres
Group=postgres

# Load environment variables
EnvironmentFile=/etc/postgres_exporter/postgres_exporter.env

# Start postgres_exporter
ExecStart=/usr/local/bin/postgres_exporter

# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=postgres_exporter

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadOnlyPaths=/etc/postgres_exporter
PrivateTmp=true

# Resource limits
LimitNOFILE=8192
MemoryLimit=256M

[Install]
WantedBy=multi-user.target
```

### 3.2 Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable postgres_exporter

# Start service
sudo systemctl start postgres_exporter

# Check status
sudo systemctl status postgres_exporter

# View logs
sudo journalctl -u postgres_exporter -f
```

**Expected output**: Service should be active (running) with no errors.

### 3.3 Test Metrics Endpoint

```bash
# Test metrics endpoint locally
curl http://localhost:9187/metrics | head -20

# Should see Prometheus format metrics like:
# pg_up 1
# pg_database_size_bytes{datname="postgres"} 8388608
# pg_stat_database_numbackends{datname="postgres"} 3
# etc.
```

## Part 4: Configure Firewall

### 4.1 On PostgreSQL Server

Allow Prometheus from monitoring server to scrape metrics:

```bash
# Allow monitoring server to access postgres_exporter
sudo ufw allow from 185.96.168.253 to any port 9187 proto tcp comment 'Prometheus metrics scraping'

# Verify rule
sudo ufw status numbered
```

### 4.2 On Monitoring Server

No changes needed (outbound connections are typically allowed).

## Part 5: Update Prometheus Configuration

### 5.1 Edit Prometheus Config

On your **monitoring server** (monitoring.plugged.in):

```bash
cd /Users/ckaraca/Mns/pluggedin-observability

# Edit prometheus.yml
nano prometheus/prometheus.yml
```

Find the existing `postgres` job and update it:

```yaml
# PostgreSQL Exporter - Standalone server
- job_name: 'postgres'
  static_configs:
    - targets: ['YOUR_POSTGRES_SERVER_IP:9187']
      labels:
        service: 'postgresql'
        instance: 'main'
        environment: 'production'
        host: 'postgres-server-hostname'
  scrape_interval: 30s
  scrape_timeout: 10s
```

**Important**: Replace `YOUR_POSTGRES_SERVER_IP` with the actual IP address of your PostgreSQL server.

If you have multiple PostgreSQL instances, add them as separate targets:

```yaml
- job_name: 'postgres'
  static_configs:
    - targets: ['10.0.0.10:9187']
      labels:
        service: 'postgresql'
        instance: 'main'
        environment: 'production'
        host: 'pg-main'
    - targets: ['10.0.0.11:9187']
      labels:
        service: 'postgresql'
        instance: 'replica'
        environment: 'production'
        host: 'pg-replica'
  scrape_interval: 30s
  scrape_timeout: 10s
```

### 5.2 Reload Prometheus

```bash
# Reload Prometheus configuration
docker-compose restart prometheus

# Or if Prometheus supports hot reload:
curl -X POST http://localhost:9090/-/reload
```

### 5.3 Verify Prometheus Scraping

1. Navigate to: https://monitoring.plugged.in/prometheus/targets
2. Find the `postgres` job
3. Status should be **UP** (green)
4. Last scrape should be recent (< 30 seconds ago)

If status is **DOWN**, check:
- Firewall rules on PostgreSQL server
- postgres_exporter service is running
- Network connectivity: `curl http://PG_SERVER_IP:9187/metrics` from monitoring server

## Part 6: Create PostgreSQL Alerts

Create alert rules for PostgreSQL monitoring:

```bash
cd /Users/ckaraca/Mns/pluggedin-observability
nano prometheus/rules/postgres-alerts.yml
```

Add the following:

```yaml
groups:
  - name: postgresql_health
    interval: 30s
    rules:
      - alert: PostgreSQLDown
        expr: pg_up == 0
        for: 2m
        labels:
          severity: critical
          service: postgresql
          category: availability
        annotations:
          summary: "PostgreSQL instance is down"
          description: "PostgreSQL on {{ $labels.instance }} has been down for more than 2 minutes."
          runbook: "1. Check PostgreSQL service: systemctl status postgresql\n2. Check logs: journalctl -u postgresql -n 100\n3. Verify postgres_exporter can connect"

      - alert: PostgreSQLTooManyConnections
        expr: sum by (instance) (pg_stat_database_numbackends) / pg_settings_max_connections > 0.8
        for: 5m
        labels:
          severity: warning
          service: postgresql
          category: resources
        annotations:
          summary: "PostgreSQL has too many connections"
          description: "{{ $labels.instance }} is using {{ $value | humanizePercentage }} of max connections (threshold: 80%)"
          runbook: "1. Check active connections: SELECT count(*) FROM pg_stat_activity\n2. Identify long-running queries\n3. Consider increasing max_connections"

      - alert: PostgreSQLSlowQueries
        expr: avg by (instance) (rate(pg_stat_database_blks_hit[5m]) / (rate(pg_stat_database_blks_hit[5m]) + rate(pg_stat_database_blks_read[5m]))) < 0.95
        for: 10m
        labels:
          severity: warning
          service: postgresql
          category: performance
        annotations:
          summary: "Low cache hit ratio detected"
          description: "Cache hit ratio is {{ $value | humanizePercentage }} on {{ $labels.instance }} (threshold: 95%)"
          runbook: "1. Check shared_buffers setting\n2. Review query patterns\n3. Consider increasing cache size"

      - alert: PostgreSQLDeadlocks
        expr: rate(pg_stat_database_deadlocks[5m]) > 0
        for: 5m
        labels:
          severity: warning
          service: postgresql
          category: performance
        annotations:
          summary: "Database deadlocks detected"
          description: "{{ $value }} deadlocks/sec on {{ $labels.instance }}"
          runbook: "1. Check pg_stat_database for deadlock counts\n2. Review application transaction logic\n3. Check for lock contention"

      - alert: PostgreSQLHighRollbackRate
        expr: rate(pg_stat_database_xact_rollback[5m]) / rate(pg_stat_database_xact_commit[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
          service: postgresql
          category: application
        annotations:
          summary: "High transaction rollback rate"
          description: "{{ $value | humanizePercentage }} of transactions are rolling back on {{ $labels.instance }}"
          runbook: "1. Check application error logs\n2. Review transaction patterns\n3. Investigate constraint violations"

      - alert: PostgreSQLReplicationLag
        expr: pg_replication_lag_seconds > 30
        for: 5m
        labels:
          severity: warning
          service: postgresql
          category: replication
        annotations:
          summary: "PostgreSQL replication lag is high"
          description: "Replication lag is {{ $value }}s on {{ $labels.instance }} (threshold: 30s)"
          runbook: "1. Check replication status\n2. Verify network connectivity\n3. Check for long-running transactions on master"

      - alert: PostgreSQLDiskUsageHigh
        expr: (pg_database_size_bytes / 1024 / 1024 / 1024) > 100
        for: 10m
        labels:
          severity: warning
          service: postgresql
          category: storage
        annotations:
          summary: "Database size is growing large"
          description: "Database {{ $labels.datname }} is {{ $value }}GB (threshold: 100GB)"
          runbook: "1. Check disk space: df -h\n2. Vacuum old data: VACUUM ANALYZE\n3. Consider archiving old data"

      - alert: PostgreSQLTableBloat
        expr: (pg_stat_user_tables_n_dead_tup / (pg_stat_user_tables_n_live_tup + pg_stat_user_tables_n_dead_tup)) > 0.2
        for: 30m
        labels:
          severity: info
          service: postgresql
          category: maintenance
        annotations:
          summary: "Table bloat detected"
          description: "Table {{ $labels.schemaname }}.{{ $labels.tablename }} has {{ $value | humanizePercentage }} dead tuples"
          runbook: "1. Run VACUUM ANALYZE on affected tables\n2. Consider autovacuum tuning\n3. Check for long-running transactions blocking vacuum"
```

Reload Prometheus to load the new rules:

```bash
docker-compose restart prometheus
```

## Part 7: Import Grafana Dashboard

### 7.1 Option A: Use Pre-built Dashboard

1. Navigate to Grafana: https://monitoring.plugged.in
2. Go to **Dashboards** → **Import**
3. Enter dashboard ID: **9628** (Official PostgreSQL Database dashboard)
4. Click **Load**
5. Select your **Prometheus** datasource
6. Click **Import**

Popular PostgreSQL dashboards:
- **9628** - PostgreSQL Database (comprehensive)
- **455** - PostgreSQL Stats
- **12120** - PostgreSQL Exporter Quickstart

### 7.2 Option B: Create Custom Dashboard

Key panels to include:

**Connection Metrics**:
- Query: `pg_stat_database_numbackends`
- Panel: Time series graph

**Transaction Rate**:
- Query: `rate(pg_stat_database_xact_commit[5m])`
- Panel: Time series graph

**Cache Hit Ratio**:
- Query: `avg by (instance) (rate(pg_stat_database_blks_hit[5m]) / (rate(pg_stat_database_blks_hit[5m]) + rate(pg_stat_database_blks_read[5m])))`
- Panel: Gauge (target: 95%+)

**Database Size**:
- Query: `pg_database_size_bytes`
- Panel: Bar gauge

**Query Performance**:
- Query: `rate(pg_stat_statements_total_time[5m]) / rate(pg_stat_statements_calls[5m])`
- Panel: Time series (requires pg_stat_statements extension)

## Part 8: Testing & Validation

### 8.1 Verify Exporter is Working

```bash
# On PostgreSQL server
systemctl status postgres_exporter
curl http://localhost:9187/metrics | grep pg_up

# Expected: pg_up 1
```

### 8.2 Verify Prometheus Scraping

```bash
# From monitoring server
curl http://YOUR_POSTGRES_SERVER_IP:9187/metrics | head -20

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="postgres")'
```

### 8.3 Test in Grafana

1. Go to **Explore** → Select **Prometheus**
2. Query: `pg_up{job="postgres"}`
3. Should return `1` (up and running)
4. Query: `pg_stat_database_numbackends`
5. Should show current connection counts

### 8.4 Generate Test Load

```bash
# Create test connections
for i in {1..10}; do
  psql -U postgres_exporter -d postgres -h localhost -W -c "SELECT pg_sleep(5);" &
done

# Watch connection count in Grafana
# Query: pg_stat_database_numbackends{datname="postgres"}
```

## Troubleshooting

### Issue: postgres_exporter Can't Connect to PostgreSQL

**Symptoms**: `pg_up 0`, logs show "connection refused" or "authentication failed"

**Solutions**:
1. Verify monitoring user exists: `psql -U postgres -c "\du postgres_exporter"`
2. Test connection manually: `psql -U postgres_exporter -d postgres -h localhost`
3. Check pg_hba.conf has correct entry
4. Reload PostgreSQL: `sudo systemctl reload postgresql`
5. Check DATA_SOURCE_NAME in `/etc/postgres_exporter/postgres_exporter.env`

### Issue: Metrics Not Appearing in Prometheus

**Symptoms**: Prometheus targets page shows postgres as DOWN

**Solutions**:
1. Check postgres_exporter is running: `systemctl status postgres_exporter`
2. Test metrics endpoint: `curl http://localhost:9187/metrics`
3. Verify firewall allows connections: `sudo ufw status | grep 9187`
4. Test from monitoring server: `curl http://PG_SERVER_IP:9187/metrics`
5. Check Prometheus config has correct IP address
6. Review Prometheus logs: `docker-compose logs prometheus`

### Issue: Permission Denied Errors

**Symptoms**: Logs show "permission denied for table" or "permission denied for function"

**Solutions**:
1. Grant pg_monitor role: `GRANT pg_monitor TO postgres_exporter;`
2. Grant specific table access: `GRANT SELECT ON table_name TO postgres_exporter;`
3. For functions: `GRANT EXECUTE ON FUNCTION function_name() TO postgres_exporter;`
4. Reconnect exporter: `systemctl restart postgres_exporter`

### Issue: High Memory Usage by Exporter

**Symptoms**: postgres_exporter using excessive memory

**Solutions**:
1. Disable unnecessary metrics in env file
2. Reduce scrape frequency in Prometheus (increase scrape_interval)
3. Limit custom queries
4. Set MemoryLimit in systemd service (already set to 256MB)

## Useful Queries

### PromQL Queries

```promql
# Database connections
sum by (datname) (pg_stat_database_numbackends)

# Connection usage percentage
100 * sum(pg_stat_database_numbackends) / pg_settings_max_connections

# Transaction rate
rate(pg_stat_database_xact_commit[5m])

# Rollback rate
rate(pg_stat_database_xact_rollback[5m])

# Cache hit ratio
avg(rate(pg_stat_database_blks_hit[5m]) / (rate(pg_stat_database_blks_hit[5m]) + rate(pg_stat_database_blks_read[5m])))

# Database size in GB
pg_database_size_bytes / 1024 / 1024 / 1024

# Query performance (requires pg_stat_statements)
rate(pg_stat_statements_total_time[5m]) / rate(pg_stat_statements_calls[5m])

# Deadlocks
rate(pg_stat_database_deadlocks[5m])

# Index usage
sum by (schemaname, tablename) (pg_stat_user_tables_idx_scan)

# Table bloat
pg_stat_user_tables_n_dead_tup / (pg_stat_user_tables_n_live_tup + pg_stat_user_tables_n_dead_tup)
```

## Security Best Practices

1. **Use Strong Password**: Generate secure password for postgres_exporter user
   ```bash
   openssl rand -base64 32
   ```

2. **Restrict Network Access**: Only allow monitoring server IP
   ```bash
   sudo ufw allow from 185.96.168.253 to any port 9187
   ```

3. **Limit Permissions**: Use pg_monitor role, don't grant superuser

4. **Secure Config Files**:
   ```bash
   chmod 600 /etc/postgres_exporter/postgres_exporter.env
   ```

5. **Use SSL** (optional): Add `sslmode=require` to DATA_SOURCE_NAME

6. **Regular Updates**: Keep postgres_exporter updated
   ```bash
   # Check for new releases
   curl -s https://api.github.com/repos/prometheus-community/postgres_exporter/releases/latest | grep tag_name
   ```

## Maintenance

### Weekly
- Check Grafana dashboards for anomalies
- Review slow query logs
- Verify backup completion metrics

### Monthly
- Update postgres_exporter if new version available
- Review alert thresholds based on actual usage patterns
- Check disk space trends

### Quarterly
- Review and optimize monitoring queries
- Test disaster recovery procedures
- Audit user permissions

## Summary

After completing this setup, you'll have:
- ✅ PostgreSQL metrics exported to Prometheus
- ✅ Comprehensive monitoring of connections, queries, transactions
- ✅ Alerts for common issues (connection limits, slow queries, replication lag)
- ✅ Grafana dashboards showing database health
- ✅ Historical metrics for capacity planning

All PostgreSQL metrics will flow to `monitoring.plugged.in` alongside your application metrics! 🎉
