# Cardinality Monitoring Features

## Overview

This document describes the comprehensive cardinality monitoring system added to the Plugged.in observability stack. These features prevent high-cardinality metrics from degrading Prometheus performance.

## What Was Added

### 1. Cardinality Monitoring Guide
**File**: `prometheus/CARDINALITY_MONITORING.md`

Comprehensive 400+ line guide covering:
- **What is cardinality** and why it matters
- **Path normalization** implementation details (7 patterns)
- **Monitoring queries** for cardinality verification
- **Deployment verification** checklist
- **Alert rules** for cardinality issues
- **Grafana dashboards** for cardinality metrics
- **Common issues & fixes** with code examples
- **Testing procedures** before production
- **Recovery procedures** for high cardinality incidents
- **Best practices** and cardinality budgets

### 2. Recording Rules
**File**: `prometheus/rules/recording-rules.yml`

Pre-computed metrics to reduce query load and enable faster dashboards:

#### Cardinality Metrics
- `pluggedin_http:path_cardinality:total` - Unique path count
- `pluggedin_http:status_code_cardinality:total` - Unique status code count
- `pluggedin_http:label_combinations:total` - Total label combinations
- `prometheus:series_growth_rate:1h` - Series growth rate per hour
- `prometheus:memory_per_series:bytes` - Memory usage efficiency

#### HTTP Performance Metrics
- `job:http_requests:rate5m` - Request rate by service
- `path:http_requests:rate5m` - Request rate by path
- `job:http_error_rate:percentage5m` - Error rate percentage
- `job:http_request_duration:p50/p95/p99` - Latency percentiles

#### Database Performance Metrics
- `operation:database_queries:rate5m` - Query rate by operation
- `database:query_error_rate:percentage5m` - Error rate
- `operation:database_query_duration:p95` - Query latency P95

#### Node.js Runtime Metrics
- `job:nodejs_memory_usage:percentage` - Memory usage %
- `job:nodejs_cpu_usage:rate5m` - CPU usage rate
- `job:nodejs_eventloop_lag:avg` - Event loop lag average

#### Service Level Indicators (SLIs)
- `sli:availability:rate5m` - Availability SLI
- `sli:latency:rate5m` - Latency SLI
- `sli:error_budget:consumption5m` - Error budget consumption
- `sli:health_score:current` - Overall health score (0-100)

**Total**: 40+ recording rules for performance and cardinality monitoring

### 3. Cardinality Alert Rules
**File**: `prometheus/rules/cardinality-alerts.yml`

Comprehensive alerts for cardinality issues:

#### High Cardinality Detection
- **HighHTTPMetricCardinality** (warning): > 200 unique paths
- **CriticalHTTPMetricCardinality** (critical): > 500 unique paths
- **HighLabelCombinationCardinality** (warning): > 2,500 label combinations

#### Unbounded Growth Detection
- **UnboundedSeriesGrowth** (critical): > 1MB/hour growth rate
- **SuspiciousSeriesIncrease** (warning): > 10,000 new series in 1 hour

#### Path Normalization Validation
- **UnnormalizedUUIDsInPaths** (warning): Detects UUID patterns that should be `:uuid`
- **UnnormalizedNumericIDsInPaths** (warning): Detects numeric IDs that should be `:id`

#### Memory & Performance Impact
- **HighMemoryPerSeries** (warning): > 5KB per 1000 series
- **PrometheusHighMemoryUsage** (critical): > 85% memory usage
- **CardinalityImpactingQueryPerformance** (warning): Avg query > 5s
- **GrafanaDashboardsSlowDueToCardinality** (warning): P95 > 10s

#### Proactive Monitoring
- **CardinalityGrowthTrend** (info): > 20% growth in 24 hours
- **UnexpectedNewMetrics** (info): > 10 new metrics in 6 hours

**Total**: 15 alert rules with detailed runbooks

### 4. Updated Application Alerts
**File**: `prometheus/rules/pluggedin-app-alerts.yml` (updated)

Enhanced health check alert documentation explaining:
- Health check monitoring relies on 3 components:
  1. The `up` metric (service is scrapeable)
  2. HTTP error metrics for `/api/health` endpoint
  3. Database connectivity check (part of health endpoint)

Existing comprehensive alerts (40+ rules):
- **Service Health** (4 alerts): Down, high/critical error rates
- **Performance & Latency** (3 alerts): High/very high latency, slow API endpoints
- **Resource Usage** (4 alerts): Memory, CPU, event loop lag
- **Database Operations** (3 alerts): Down, slow queries, high error rate
- **Authentication & Security** (3 alerts): Failure spikes, rate limiting, unauthorized access
- **Business Metrics** (3 alerts): No user activity, document upload failures, slow processing
- **MCP Integration** (2 alerts): Proxy down, high error rate
- **External Dependencies** (2 alerts): RAG backend down, registry proxy down
- **Deployment** (2 alerts): Frequent restarts, configuration errors

## How Cardinality Monitoring Works

### The Problem
Without path normalization, every unique URL creates a new time series:
```promql
# BAD - Unbounded cardinality
pluggedin_http_requests_total{path="/api/users/1"}
pluggedin_http_requests_total{path="/api/users/2"}
pluggedin_http_requests_total{path="/api/users/3"}
...millions more...
```

This causes:
- **10x memory usage increase** in Prometheus
- **Slow queries** (seconds instead of milliseconds)
- **Dashboard timeouts** in Grafana
- **Potential OOM crashes**

### The Solution
Path normalization groups dynamic segments:
```promql
# GOOD - Bounded cardinality
pluggedin_http_requests_total{path="/api/users/:id"}  # All user requests
pluggedin_http_requests_total{path="/api/servers/:uuid"}  # All server requests
```

### 7 Normalization Patterns
Implemented in `lib/observability/http-metrics.ts`:

1. **Locales**: `/en/settings` → `/:locale/settings`
2. **API Versions**: `/api/v1/users` → `/api/:version/users`
3. **UUIDs**: `/api/servers/123e4567-...` → `/api/servers/:uuid`
4. **Hashes**: `/files/5d41402a...` → `/files/:hash`
5. **Tokens**: `/auth/eyJhbGci...` → `/auth/:token`
6. **Numeric IDs**: `/api/users/12345` → `/api/users/:id`
7. **Usernames**: `/to/john_doe` → `/to/:username`

**Test coverage**: 45 test cases in `tests/lib/http-metrics.test.ts`

## Deployment Verification Checklist

After deploying to production, follow this checklist from `CARDINALITY_MONITORING.md`:

### ✅ Step 1: Baseline Check (First 5 Minutes)
```bash
curl -s 'http://localhost:9090/api/v1/query?query=count(pluggedin_http_requests_total)' | jq
```
**Expected**: < 100 series

### ✅ Step 2: Path Normalization Verification (After 1 Hour)
Query all unique paths in Prometheus:
```promql
group by (path) (pluggedin_http_requests_total)
```
**Verify**:
- ✅ See normalized paths: `/api/users/:id`, `/to/:username`, `/:locale/settings`
- ❌ No raw IDs: `/api/users/12345`, `/to/john_doe`

### ✅ Step 3: Growth Rate Monitoring (After 24 Hours)
```promql
rate(prometheus_tsdb_symbol_table_size_bytes[1h])
```
**Expected**: Near-zero growth (if normalization is working)

### ✅ Step 4: Memory Impact Assessment
```promql
process_resident_memory_bytes{job="prometheus"} / 1024 / 1024 / 1024  # GB
```
**Expected**: < 4GB for 100k series

## Alert Response Playbook

### When You Receive: "HighHTTPMetricCardinality"

**Severity**: Warning
**Threshold**: > 200 unique paths

**Immediate Actions**:
1. Query all paths:
   ```promql
   group by (path) (pluggedin_http_requests_total)
   ```

2. Look for unnormalized patterns:
   - UUIDs: `/api/servers/123e4567-e89b-12d3-a456-426614174000`
   - IDs: `/api/users/12345`
   - Tokens: `/auth/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9`

3. Update `lib/observability/http-metrics.ts`:
   - Add missing regex pattern to `normalizePath()` function
   - Add test case to `tests/lib/http-metrics.test.ts`

4. Deploy fix and monitor

### When You Receive: "UnboundedSeriesGrowth"

**Severity**: Critical
**Threshold**: > 1MB/hour series growth

**Emergency Response**:
1. Identify source metric:
   ```promql
   topk(10, count by (__name__) ({__name__=~".+"}))
   ```

2. Check series count by job:
   ```promql
   count by (job) ({__name__=~".+"})
   ```

3. Review recent deployments (last 2 hours)

4. Emergency action options:
   - **Option A**: Restart Prometheus (clears in-memory series)
     ```bash
     docker-compose restart prometheus
     ```
   - **Option B**: Temporarily disable problematic scrape job
   - **Option C**: Emergency hotfix to normalization code

5. Root cause analysis and permanent fix

## Grafana Dashboards

Recommended panels to add to dashboards:

### Panel 1: Total Series Count
```promql
count({job="pluggedin-app"})
```
**Thresholds**: Green < 10k, Yellow 10k-50k, Red > 50k

### Panel 2: Path Cardinality
```promql
pluggedin_http:path_cardinality:total
```
**Alert Threshold**: 100

### Panel 3: Top Paths by Traffic
```promql
topk(20, sum by (path) (rate(pluggedin_http_requests_total[5m])))
```

### Panel 4: Cardinality Growth Rate
```promql
prometheus:series_growth_rate:1h
```
**Expected**: Near-zero after initial spike

### Panel 5: Memory Per Series
```promql
prometheus:memory_per_series:bytes
```
**Threshold**: < 5KB per 1000 series

### Panel 6: Service Health Score
```promql
sli:health_score:current
```
**Ranges**: 90-100 (Excellent), 80-90 (Good), 70-80 (Fair), <70 (Poor)

## Testing Before Production

### Load Test with Realistic Data
```bash
# Generate 1000 requests with different user IDs
for i in {1..1000}; do
  curl "http://localhost:12005/api/users/$i"
done

# Verify cardinality did NOT increase by 1000
curl -s 'http://localhost:9090/api/v1/query?query=count(pluggedin_http_requests_total)' | jq
```

### Path Pattern Validation
```bash
# Test all normalization patterns
curl http://localhost:12005/api/users/123
curl http://localhost:12005/to/john_doe
curl http://localhost:12005/en/dashboard
curl http://localhost:12005/api/servers/550e8400-e29b-41d4-a716-446655440000

# Verify normalized paths
curl -s 'http://localhost:9090/api/v1/label/path/values' | jq
```

**Expected**:
```json
[
  "/api/users/:id",
  "/to/:username",
  "/:locale/dashboard",
  "/api/servers/:uuid"
]
```

## Cardinality Budget

Recommended limits per environment:

| Environment | Max Series | Max Paths | Max Labels/Metric |
|-------------|-----------|-----------|-------------------|
| Development | 10,000    | 50        | 5                 |
| Staging     | 50,000    | 100       | 5                 |
| Production  | 500,000   | 200       | 5                 |

## Benefits

✅ **Performance**
- Pre-computed metrics reduce query time by 10-100x
- Dashboards load instantly instead of timing out

✅ **Proactive Monitoring**
- Detect cardinality issues before they impact users
- Automated alerts with detailed runbooks

✅ **Cost Savings**
- Reduced memory usage (can use smaller Prometheus instance)
- Lower storage costs (fewer series to store)

✅ **Reliability**
- Prevents OOM crashes from runaway cardinality
- Ensures dashboards remain fast and responsive

## Next Steps

1. **Deploy to production** with all new alert rules enabled
2. **Monitor for first 24 hours** using verification checklist
3. **Set up Grafana dashboards** with cardinality panels
4. **Review alerts weekly** to tune thresholds
5. **Document new patterns** when adding features that create new paths

## Additional Resources

- **Full Guide**: `prometheus/CARDINALITY_MONITORING.md`
- **Recording Rules**: `prometheus/rules/recording-rules.yml`
- **Alert Rules**: `prometheus/rules/cardinality-alerts.yml`
- **Application Alerts**: `prometheus/rules/pluggedin-app-alerts.yml`
- **Implementation**: See `lib/observability/http-metrics.ts` in pluggedin-app
- **Tests**: See `tests/lib/http-metrics.test.ts` in pluggedin-app (45 test cases)
