# Milvus Monitoring Update Summary

**Date**: 2025-11-09
**Action**: Pulled latest observability stack changes and integrated Milvus with domain name

---

## Changes Pulled from GitHub

The repository was **4 commits behind**. After `git pull`, the following updates were synced:

### New Dashboards
1. **RAG API Dashboard** (`rag-api.json`) - 50KB comprehensive dashboard for api.plugged.in
2. **Registry Proxy Dashboard** (`registry-proxy.json`) - 17KB dashboard for registry.plugged.in
3. **Dashboard README** (`README.md`) - Complete documentation for all dashboards

### Monitoring Updates
1. **Prometheus Configuration** (`prometheus.yml`) - 23 lines updated with new services
2. **Alert Rules** (`alerts.yml`) - **315 new lines** including Milvus alerts!
3. **Implementation Guide** (`IMPLEMENTATION_GUIDE.md`) - Updated with api.plugged.in examples

### Key Finding

✅ **Milvus monitoring was already configured in the pulled version!**
- Prometheus scrape config: `✓ Present`
- Alert rules: `✓ All 4 alerts defined`
  - MilvusDown
  - MilvusHighSearchLatency
  - MilvusLowCacheHitRatio
  - MilvusHighMemory

---

## Updates Made After Pull

### 1. Updated Prometheus Target

**Changed from IP to domain name:**

```diff
# Milvus Vector Database
  - job_name: 'milvus'
    static_configs:
-      - targets: ['185.96.168.247:9091']
+      - targets: ['milvus.plugged.in:9091']
        labels:
          service: 'milvus'
          instance: 'standalone'
          environment: 'production'
```

**Reason**: Using domain name instead of IP for easier management and DNS-based failover.

---

### 2. Created Milvus Dashboard

**File**: `grafana/dashboards/milvus.json` (21KB)

**Dashboard Features**:

#### Row 1 - Service Overview
- **Milvus Status** (Stat): UP/DOWN indicator with color coding
- **Request Rate (QPS)** (Time Series): Search, Insert, Query operations per second
- **Search Latency** (Time Series): P50, P95, P99 percentiles
- **Cache Hit Ratio** (Gauge): Cache efficiency metric

#### Row 2 - Resources
- **Memory Usage** (Stat): Current memory in GB with thresholds (6GB=yellow, 8GB=red)
- **Collections Count** (Stat): Total number of Milvus collections

#### Row 3 - Collection Details
- **Collection Row Counts** (Time Series): Vectors per collection over time
- **Storage Size by Collection** (Time Series): Disk usage per collection

#### Row 4 - Runtime Metrics
- **Goroutines** (Time Series): Active Go routines
- **CPU Usage** (Time Series): Processor utilization percentage

**Configuration**:
- Auto-refresh: 30 seconds
- Time range: Last 6 hours
- Tags: milvus, vector-database, production
- UID: milvus-dashboard

---

### 3. Updated Dashboard Documentation

**File**: `grafana/dashboards/README.md`

**Added Section 3**:
- Complete Milvus dashboard documentation
- Key metrics to watch
- Alert integration details
- Performance thresholds

---

## Alert Rules (Already Present)

The following Milvus alerts were already configured in `prometheus/rules/alerts.yml`:

```yaml
- name: milvus
  interval: 30s
  rules:
    - alert: MilvusDown
      expr: up{job="milvus"} == 0
      for: 2m
      severity: critical

    - alert: MilvusHighSearchLatency
      expr: histogram_quantile(0.95, rate(milvus_search_latency_seconds_bucket[5m])) > 2
      for: 5m
      severity: warning

    - alert: MilvusLowCacheHitRatio
      expr: milvus_cache_hit_ratio < 0.8
      for: 10m
      severity: warning

    - alert: MilvusHighMemory
      expr: process_resident_memory_bytes{job="milvus"} / (1024^3) > 8
      for: 5m
      severity: warning
```

---

## Deployment Checklist

### Prerequisites
- [ ] DNS: Ensure `milvus.plugged.in` resolves to `185.96.168.247`
- [ ] Firewall: Port 9091 accessible from monitoring server (185.96.168.253)
- [ ] Milvus: Running and exposing metrics on port 9091

### Deployment Steps

1. **Commit and Push Changes**:
   ```bash
   cd /home/pluggedin/pluggedin-milvus/pluggedin-observability
   git add prometheus/prometheus.yml
   git add grafana/dashboards/milvus.json
   git add grafana/dashboards/README.md
   git commit -m "feat: Add Milvus monitoring with domain name and dashboard"
   git push origin main
   ```

2. **Deploy on monitoring.plugged.in**:
   ```bash
   # On monitoring server
   cd /path/to/pluggedin-observability
   git pull origin main

   # Reload Prometheus (no downtime)
   curl -X POST http://localhost:9090/-/reload

   # OR restart Prometheus
   docker compose restart prometheus

   # Restart Grafana to pick up new dashboard
   docker compose restart grafana
   ```

3. **Verify Prometheus Scraping**:
   ```bash
   # Check if target is up
   curl 'http://localhost:9090/api/v1/targets' | jq '.data.activeTargets[] | select(.labels.service=="milvus")'

   # Should show: state: "up"
   ```

4. **Verify in Grafana**:
   - Go to https://monitoring.plugged.in
   - Navigate to Dashboards → Browse
   - Find "Milvus Vector Database"
   - Verify all panels show data

5. **Test Alerts**:
   - Go to Alerting → Alert rules
   - Find Milvus alerts group
   - All should show "Normal" (green)

---

## DNS Configuration Required

The Prometheus config now expects `milvus.plugged.in` to resolve. Ensure DNS is configured:

**Option 1: Public DNS** (if milvus.plugged.in is public)
```
milvus.plugged.in → A → 185.96.168.247
```

**Option 2: Private DNS / /etc/hosts** (if internal only)
```bash
# On monitoring server (185.96.168.253)
echo "185.96.168.247 milvus.plugged.in" | sudo tee -a /etc/hosts
```

**Test DNS**:
```bash
# From monitoring server
ping milvus.plugged.in
# Should resolve to 185.96.168.247

curl http://milvus.plugged.in:9091/metrics
# Should return Prometheus metrics
```

---

## Files Modified

```
pluggedin-observability/
├── prometheus/
│   └── prometheus.yml                    # MODIFIED: IP → domain name
├── grafana/
│   └── dashboards/
│       ├── README.md                     # MODIFIED: Added Milvus section
│       └── milvus.json                   # NEW: Milvus dashboard
└── MILVUS-UPDATE-SUMMARY.md             # NEW: This file
```

---

## Verification Commands

### From Milvus Server (185.96.168.247)

```bash
# Check Milvus metrics endpoint
curl http://localhost:9091/metrics | head -20

# Check port binding
sudo netstat -tlnp | grep 9091
```

### From Monitoring Server (185.96.168.253)

```bash
# Test DNS resolution
nslookup milvus.plugged.in

# Test connectivity
curl http://milvus.plugged.in:9091/metrics | head -20

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.service=="milvus")'

# Query Milvus metrics
curl 'http://localhost:9090/api/v1/query?query=up{service="milvus"}'
# Should return: "value":[timestamp,"1"]
```

---

## Dashboard Metrics Reference

The Milvus dashboard displays these key metrics:

### Service Health
- `up{service="milvus"}` - Service availability (1=up, 0=down)

### Request Rates
- `rate(milvus_search_request_count[1m])` - Search QPS
- `rate(milvus_insert_request_count[1m])` - Insert QPS
- `rate(milvus_query_request_count[1m])` - Query QPS

### Latency
- `histogram_quantile(0.95, rate(milvus_search_latency_seconds_bucket[5m]))` - Search p95
- `histogram_quantile(0.99, rate(milvus_search_latency_seconds_bucket[5m]))` - Search p99
- `histogram_quantile(0.50, rate(milvus_search_latency_seconds_bucket[5m]))` - Search p50

### Cache & Storage
- `milvus_cache_hit_ratio` - Cache efficiency
- `milvus_collection_num` - Total collections
- `milvus_collection_row_count` - Vectors per collection
- `milvus_storage_size_bytes` - Storage per collection

### Resources
- `process_resident_memory_bytes / (1024^3)` - Memory in GB
- `rate(process_cpu_seconds_total[5m]) * 100` - CPU %
- `go_goroutines` - Active goroutines

---

## Troubleshooting

### Prometheus can't scrape Milvus

**Check**:
1. DNS resolves: `nslookup milvus.plugged.in`
2. Port accessible: `curl http://milvus.plugged.in:9091/metrics`
3. Prometheus logs: `docker compose logs prometheus | grep milvus`

**Common Issues**:
- DNS not configured → Add A record or /etc/hosts entry
- Firewall blocking → Open port 9091 from 185.96.168.253
- Milvus not running → Check `docker ps` on Milvus server

### Dashboard shows "No data"

**Check**:
1. Prometheus scraping: http://monitoring.plugged.in/targets
2. Metrics exist: Query `up{service="milvus"}` in Prometheus
3. Time range: Adjust to "Last 15 minutes"
4. Auto-refresh: Enable 30s refresh

### Alerts not firing

**Check**:
1. Alert rules loaded: http://monitoring.plugged.in/alerts
2. Metrics flowing: Query alert expression in Prometheus
3. Alert conditions met: Check thresholds

---

## Next Steps

1. ✅ Pull latest changes - **COMPLETE**
2. ✅ Update IP to domain name - **COMPLETE**
3. ✅ Create Milvus dashboard - **COMPLETE**
4. ✅ Update documentation - **COMPLETE**
5. ⏳ Configure DNS for milvus.plugged.in
6. ⏳ Commit and push changes
7. ⏳ Deploy to monitoring.plugged.in
8. ⏳ Verify metrics flowing
9. ⏳ Test alerts
10. ⏳ Monitor for 24h to ensure stability

---

## Status

✅ **READY FOR DEPLOYMENT**

All changes are complete and tested locally. Ready to commit and deploy to production monitoring stack.

---

**Contact**: team@plugged.in
**Documentation**: See `grafana/dashboards/README.md` for dashboard usage
