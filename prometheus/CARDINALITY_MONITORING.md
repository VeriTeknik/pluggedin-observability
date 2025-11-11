# Metric Cardinality Monitoring Guide

## Overview

High cardinality metrics can cause **serious performance issues** in Prometheus:
- Increased memory usage (up to 10x)
- Slower query performance
- Higher disk usage
- Potential out-of-memory crashes

This guide shows how to monitor and prevent cardinality issues after deployment.

## What is Cardinality?

**Cardinality** = Number of unique time series (unique combinations of metric name + labels)

### Examples

**Low Cardinality** ✅ (Good)
```promql
pluggedin_http_requests_total{method="GET", path="/api/users/:id", status_code="200"}
# Only ~10 methods × ~50 paths × ~10 status codes = ~5,000 series
```

**High Cardinality** ❌ (Bad)
```promql
pluggedin_http_requests_total{method="GET", path="/api/users/12345", status_code="200"}
# Unbounded: methods × users × status codes = potentially millions of series
```

## Why Path Normalization Matters

We implemented path normalization in `lib/observability/http-metrics.ts` to prevent high cardinality:

```typescript
// Before normalization (BAD - creates new series for every user ID)
/api/users/12345 → /api/users/12345  // ❌ Unbounded cardinality
/api/users/67890 → /api/users/67890  // ❌ New time series

// After normalization (GOOD - groups all users under one series)
/api/users/12345 → /api/users/:id    // ✅ Bounded cardinality
/api/users/67890 → /api/users/:id    // ✅ Same time series
```

### Normalization Patterns

Our implementation normalizes:
1. **UUIDs**: `/api/servers/123e4567-...` → `/api/servers/:uuid`
2. **Numeric IDs**: `/api/users/12345` → `/api/users/:id`
3. **Usernames**: `/to/john_doe` → `/to/:username`
4. **API Versions**: `/api/v1/users` → `/api/:version/users`
5. **Locales**: `/en/settings` → `/:locale/settings`
6. **Tokens**: `/auth/eyJhbGci...` → `/auth/:token`
7. **Hashes**: `/files/5d41402a...` → `/files/:hash`

## Cardinality Monitoring Queries

### 1. Check Total Series Count

```promql
# Total unique time series in Prometheus
prometheus_tsdb_symbol_table_size_bytes / 1024 / 1024  # In MB
```

**Expected**: < 100k series for small deployments, < 1M for large

### 2. Check Cardinality by Metric Name

```promql
# Top 10 metrics by cardinality
topk(10, count by (__name__) (
  {job="pluggedin-app"}
))
```

**Expected for HTTP metrics**:
- `pluggedin_http_requests_total`: < 500 series
- `pluggedin_http_request_duration_seconds`: < 1,000 series
- `pluggedin_http_errors_total`: < 200 series

### 3. Check Cardinality by Label

```promql
# Cardinality of 'path' label in HTTP requests
count(count by (path) (pluggedin_http_requests_total))
```

**Expected**: < 100 unique paths (if normalization is working)

**Warning Signs**:
- 500+ unique paths → normalization may be failing
- 1,000+ unique paths → critical issue, investigate immediately

### 4. Identify High-Cardinality Labels

```promql
# Top paths by series count
topk(20, count by (path) (pluggedin_http_requests_total))
```

**Look for**:
- Paths with UUIDs, IDs, or tokens that weren't normalized
- Unexpected patterns like `/users/12345` instead of `/users/:id`

### 5. Check Label Value Distribution

```promql
# Count unique values per label
count(count by (method, path, status_code) (
  pluggedin_http_requests_total
))
```

**Expected combinations**:
- ~5 methods (GET, POST, PUT, PATCH, DELETE)
- ~50 normalized paths
- ~10 status codes
- **Total**: ~2,500 combinations maximum

## Deployment Verification Steps

### Step 1: Baseline Check (First 5 Minutes)

```bash
# Query Prometheus API
curl -s 'http://localhost:9090/api/v1/query?query=count(pluggedin_http_requests_total)' | jq '.data.result[0].value[1]'
```

**Expected**: < 100 series in first 5 minutes

### Step 2: Path Normalization Verification (After 1 Hour)

Query all unique paths:
```promql
group by (path) (pluggedin_http_requests_total)
```

**Verify**:
- ✅ Paths like `/api/users/:id`, `/to/:username`, `/:locale/settings`
- ❌ No raw IDs like `/api/users/12345`, `/to/john_doe`

### Step 3: Growth Rate Monitoring (After 24 Hours)

```promql
# Series growth rate
rate(prometheus_tsdb_symbol_table_size_bytes[1h])
```

**Expected**: Near-zero growth after initial spike (if paths are normalized)

**Warning**: Continuous growth means new unique series are being created

### Step 4: Memory Impact Assessment

```promql
# Prometheus memory usage
process_resident_memory_bytes{job="prometheus"} / 1024 / 1024 / 1024  # In GB
```

**Expected**: < 4GB for 100k series, < 16GB for 1M series

## Cardinality Alert Rules

Add these to `prometheus/rules/cardinality-alerts.yml`:

```yaml
groups:
  - name: metric_cardinality
    interval: 60s
    rules:
      - alert: HighMetricCardinality
        expr: count(count by (__name__, path) (pluggedin_http_requests_total)) > 500
        for: 10m
        labels:
          severity: warning
          service: pluggedin-app
          category: observability
        annotations:
          summary: "High metric cardinality detected"
          description: "HTTP metrics have {{ $value }} unique series (threshold: 500). Path normalization may be failing."
          runbook: "1. Query: group by (path) (pluggedin_http_requests_total)\n2. Check for unnormalized paths with IDs/UUIDs\n3. Review lib/observability/http-metrics.ts normalizePath function\n4. Check if new path patterns need to be added"

      - alert: UnboundedMetricGrowth
        expr: rate(prometheus_tsdb_symbol_table_size_bytes[1h]) > 1000000  # 1MB/hour
        for: 30m
        labels:
          severity: critical
          service: pluggedin-app
          category: observability
        annotations:
          summary: "Unbounded metric growth detected"
          description: "Time series growing at {{ $value | humanize }}bytes/hour. Critical cardinality issue."
          runbook: "1. Identify source: topk(10, count by (__name__) ({job=\"pluggedin-app\"}))\n2. Check recent code changes\n3. Consider metric reset or disable if needed"

      - alert: SuspiciousPathPattern
        expr: |
          count(
            count by (path) (
              pluggedin_http_requests_total{path=~".*/[0-9a-f]{8}-[0-9a-f]{4}.*"}
            )
          ) > 0
        for: 5m
        labels:
          severity: warning
          service: pluggedin-app
          category: observability
        annotations:
          summary: "UUID pattern detected in normalized paths"
          description: "Found paths with UUID patterns that should have been normalized to :uuid"
          runbook: "1. Query paths with UUIDs: {path=~\".*/[0-9a-f]{8}-[0-9a-f]{4}.*\"}\n2. Update normalizePath regex patterns\n3. Add test cases for missed patterns"
```

## Grafana Dashboards for Cardinality

### Panel 1: Total Series Count

```promql
count({job="pluggedin-app"})
```

**Graph**: Single stat with trend line

**Thresholds**:
- Green: < 10,000
- Yellow: 10,000 - 50,000
- Red: > 50,000

### Panel 2: Cardinality by Metric

```promql
topk(10, count by (__name__) ({job="pluggedin-app"}))
```

**Graph**: Bar chart

### Panel 3: Path Label Cardinality

```promql
count(count by (path) (pluggedin_http_requests_total))
```

**Graph**: Single stat with alert threshold at 100

### Panel 4: Recent Paths (Last Hour)

```promql
# Show paths that received traffic in last hour
count_over_time(
  pluggedin_http_requests_total[1h]
) > 0
```

**Graph**: Table showing all active paths

## Common Cardinality Issues & Fixes

### Issue 1: User IDs in Metrics

**Symptom**: Thousands of unique series
```promql
pluggedin_user_requests_total{user_id="12345"}  # ❌
```

**Fix**: Remove user_id from labels, or aggregate
```typescript
// Don't do this
counter.inc({ user_id: userId });

// Do this instead
counter.inc({ user_type: isAuthenticated ? 'authenticated' : 'anonymous' });
```

### Issue 2: Session IDs in Paths

**Symptom**: Paths like `/api/sessions/abc123xyz`

**Fix**: Add normalization pattern
```typescript
// In normalizePath function
{ regex: /\/sessions\/[a-zA-Z0-9]{10,}/g, replacement: '/sessions/:session_id' }
```

### Issue 3: Query Parameters as Labels

**Symptom**: `{path="/api/users?page=1"}`, `{path="/api/users?page=2"}`

**Fix**: Already handled - we strip query params
```typescript
const pathWithoutQuery = path.split('?')[0];
```

### Issue 4: Timestamps in Paths

**Symptom**: `/api/exports/2024-01-15-report.pdf`

**Fix**: Add date pattern normalization
```typescript
{ regex: /\/\d{4}-\d{2}-\d{2}/g, replacement: '/:date' }
```

## Testing Cardinality Before Production

### 1. Load Testing with Realistic Data

```bash
# Generate 1000 requests with different user IDs
for i in {1..1000}; do
  curl "http://localhost:12005/api/users/$i"
done

# Check cardinality
curl -s 'http://localhost:9090/api/v1/query?query=count(pluggedin_http_requests_total)' | jq
```

**Expected**: Series count should NOT increase by 1000

### 2. Path Pattern Validation

```bash
# Test all common path patterns
curl http://localhost:12005/api/users/123
curl http://localhost:12005/to/john_doe
curl http://localhost:12005/en/dashboard
curl http://localhost:12005/api/servers/550e8400-e29b-41d4-a716-446655440000

# Query Prometheus for normalized paths
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

### 3. Unit Tests (Already Implemented)

See `tests/lib/http-metrics.test.ts`:
- 45 test cases covering all normalization patterns
- Real-world path examples
- Edge cases and pattern order verification

## Recovery from High Cardinality

If you detect runaway cardinality in production:

### Emergency Response

1. **Identify the source**:
   ```promql
   topk(10, count by (__name__) ({job="pluggedin-app"}))
   ```

2. **Temporary fix**: Restart Prometheus (clears in-memory series)
   ```bash
   docker-compose restart prometheus
   ```

3. **Fix normalization**: Add missing pattern to `lib/observability/http-metrics.ts`

4. **Deploy fix**: Push updated code to production

5. **Monitor**: Verify series count stabilizes

### Long-term Fix

1. Add comprehensive test coverage for new patterns
2. Add cardinality alerts (see alert rules above)
3. Regular cardinality audits (weekly query review)
4. Document new path patterns in team wiki

## Cardinality Budget

Recommended limits per environment:

| Environment | Max Series | Max Paths | Max Labels/Metric |
|-------------|-----------|-----------|-------------------|
| Development | 10,000    | 50        | 5                 |
| Staging     | 50,000    | 100       | 5                 |
| Production  | 500,000   | 200       | 5                 |

## Useful Prometheus CLI Commands

```bash
# Check Prometheus TSDB stats
curl http://localhost:9090/api/v1/status/tsdb

# Get label values for debugging
curl 'http://localhost:9090/api/v1/label/path/values'

# Query series count by job
curl -s 'http://localhost:9090/api/v1/query?query=count by (job) ({__name__=~".%2B"})' | jq

# Check memory usage
curl -s 'http://localhost:9090/api/v1/query?query=process_resident_memory_bytes' | jq
```

## Best Practices Summary

✅ **Do**:
- Always normalize dynamic path segments (IDs, UUIDs, tokens)
- Use low-cardinality labels (status codes, HTTP methods)
- Test normalization with realistic data before production
- Monitor cardinality metrics after every deployment
- Set up alerts for cardinality growth

❌ **Don't**:
- Use user IDs, session IDs, or timestamps as labels
- Create metrics for individual users or resources
- Use unbounded string values as labels
- Skip path normalization for "just this one endpoint"

## Additional Resources

- [Prometheus Best Practices](https://prometheus.io/docs/practices/naming/)
- [Avoiding High Cardinality](https://www.robustperception.io/cardinality-is-key)
- [Prometheus TSDB Format](https://ganeshvernekar.com/blog/prometheus-tsdb-the-head-block/)
