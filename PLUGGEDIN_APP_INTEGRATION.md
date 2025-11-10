# Pluggedin-App Observability Integration

**Status**: ✅ Complete
**Date**: 2025-11-10
**Services**: pluggedin-app (Next.js) → monitoring.plugged.in

## Overview

This document describes the complete observability integration between pluggedin-app and the centralized monitoring stack at monitoring.plugged.in.

## Architecture

```
┌─────────────────────────────────────┐
│   Production Server (plugged.in)    │
│                                      │
│  ┌────────────────────────────────┐ │
│  │      pluggedin-app             │ │
│  │   (Next.js 15 / Node.js)       │ │
│  │                                 │ │
│  │  - Port: 12005                  │ │
│  │  - Systemd service              │ │
│  │  - Logs: /var/log/pluggedin/    │ │
│  │  - Metrics: /api/metrics        │ │
│  │  - Health: /api/health          │ │
│  └────────┬───────────┬────────────┘ │
│           │           │               │
│           │           │               │
│     Logs  │           │  Metrics      │
│      (JSON)           │ (Prometheus)  │
│           │           │               │
│  ┌────────▼────────┐  │              │
│  │   Promtail      │  │              │
│  │  (Log Shipper)  │  │              │
│  │  - Port: 9080   │  │              │
│  └────────┬────────┘  │              │
│           │           │               │
└───────────┼───────────┼───────────────┘
            │           │
            │           │ HTTP Scrape
       Loki │           │ every 30s
       Push │           │
            │           │
┌───────────▼───────────▼──────────────┐
│ Monitoring Server (monitoring.pl...  │
│                                       │
│  ┌─────────────┐  ┌────────────────┐ │
│  │    Loki     │  │   Prometheus   │ │
│  │  Port: 3100 │  │   Port: 9090   │ │
│  │             │  │                │ │
│  │ - Stores    │  │ - Scrapes      │ │
│  │   logs      │  │   /api/metrics │ │
│  │ - 15d       │  │ - 15d retention│ │
│  │   retention │  │ - Alert rules  │ │
│  └──────┬──────┘  └───────┬────────┘ │
│         │                 │           │
│         └────────┬────────┘           │
│                  │                    │
│         ┌────────▼────────┐           │
│         │    Grafana      │           │
│         │   Port: 3000    │           │
│         │                 │           │
│         │ - Dashboards    │           │
│         │ - Alerts UI     │           │
│         │ - Log Explorer  │           │
│         └─────────────────┘           │
│                                       │
│  Access: https://monitoring.plugged.in│
└───────────────────────────────────────┘
```

## Implementation Summary

### 1. Application Instrumentation (pluggedin-app)

#### Enhanced Middleware
**File**: `pluggedin-app/middleware.ts`

**Features**:
- Automatic trace ID generation for every request (UUID v4)
- Request/response logging with correlation IDs
- Performance timing for all requests
- HTTP metrics tracking per endpoint
- Structured Pino JSON logging
- Non-blocking async logging

**Headers Added**:
- `x-trace-id`: Unique request identifier
- `x-request-id`: Alias for trace_id
- All existing security headers preserved

#### HTTP Metrics Module
**File**: `pluggedin-app/lib/observability/http-metrics.ts`

**Metrics Exposed**:
1. `pluggedin_http_requests_total` - Total requests by method, path, status, user_type
2. `pluggedin_http_request_duration_seconds` - Request latency histogram (10ms-10s buckets)
3. `pluggedin_http_request_size_bytes` - Request payload size
4. `pluggedin_http_response_size_bytes` - Response payload size
5. `pluggedin_http_requests_active` - Currently processing requests (gauge)
6. `pluggedin_http_errors_total` - Errors by type (server_error, rate_limit, unauthorized, etc.)

**Authentication Metrics**:
7. `pluggedin_auth_events_total` - Login/logout/token refresh events
8. `pluggedin_auth_sessions_active` - Active authenticated sessions

**Database Metrics**:
9. `pluggedin_database_query_duration_seconds` - Query latency by operation and table
10. `pluggedin_database_queries_total` - Total queries by operation, table, success
11. `pluggedin_database_connections_active` - Active connections to PostgreSQL

**Document/RAG Metrics**:
12. `pluggedin_document_operations_total` - Upload/delete/search/download by status
13. `pluggedin_document_processing_duration_seconds` - Processing time by document type

**Plus all default Node.js metrics** (CPU, memory, event loop, GC, heap, etc.)

#### Health Check Endpoint
**File**: `pluggedin-app/app/api/health/route.ts`

**Endpoints**:
- `GET /api/health` - Full health status with database check (JSON response)
- `HEAD /api/health` - Lightweight check for load balancers (status code only)

**Response Example**:
```json
{
  "status": "healthy",
  "timestamp": "2025-11-10T12:00:00.000Z",
  "uptime": 86400,
  "checks": {
    "service": true,
    "database": true
  },
  "version": "2.18.0",
  "environment": "production"
}
```

**Status Codes**:
- `200 OK` - Service healthy
- `503 Service Unavailable` - Database or critical component down

### 2. Log Shipping (Production Server)

**Setup File**: `PRODUCTION_SETUP.md` (Step-by-step manual)

#### Promtail Configuration
**File**: `/etc/promtail/promtail-config.yml` (on production server)

**Features**:
- Tails `/var/log/pluggedin/pluggedin_app.log`
- JSON log parsing with field extraction
- Batching: 2s intervals (near real-time)
- Remote Loki push to monitoring server
- Automatic timestamp parsing (RFC3339/ISO8601)
- Retry logic with backoff

**Labels Applied**:
- `service`: pluggedin-app
- `environment`: production
- `host`: plugged.in
- `level`: error, warn, info, debug, trace
- `trace_id`: From JSON logs
- `event`: From JSON logs (auth, mcp, document, etc.)

#### Systemd Service
**File**: `/etc/systemd/system/promtail.service` (on production server)

**Configuration**:
- Runs as `pluggedin` user
- Auto-restart on failure
- Memory limit: 256MB
- Read-only access to log files
- Journal logging for monitoring

### 3. Metrics Collection (Monitoring Server)

#### Prometheus Scrape Configuration
**File**: `pluggedin-observability/prometheus/prometheus.yml`

**Scrape Job**:
```yaml
- job_name: 'pluggedin-app'
  metrics_path: '/api/metrics'
  scheme: 'https'
  static_configs:
    - targets: ['plugged.in']
      labels:
        service: 'pluggedin-app'
        environment: 'production'
  scrape_interval: 30s
  scrape_timeout: 10s
```

**Security**: Metrics endpoint IP whitelisted (monitoring server IP already in `METRICS_ALLOWED_IPS`)

### 4. Alert Rules (Monitoring Server)

#### Alert Configuration
**File**: `pluggedin-observability/prometheus/rules/pluggedin-app-alerts.yml`

**Alert Groups** (10 groups, 40+ alerts):

1. **Service Health** (4 alerts):
   - `PluggedinAppDown` - Service unreachable (critical)
   - `PluggedinAppHealthCheckFailing` - Health endpoint failing (critical)
   - `PluggedinAppHighErrorRate` - >5% errors (warning)
   - `PluggedinAppCriticalErrorRate` - >15% errors (critical)

2. **Performance** (3 alerts):
   - `PluggedinAppHighLatency` - P95 >2s (warning)
   - `PluggedinAppVeryHighLatency` - P95 >5s (critical)
   - `PluggedinAppSlowApiEndpoints` - API P95 >3s (warning)

3. **Resources** (4 alerts):
   - `PluggedinAppHighMemoryUsage` - >80% heap (warning)
   - `PluggedinAppCriticalMemoryUsage` - >90% heap (critical)
   - `PluggedinAppHighCpuUsage` - >80% CPU (warning)
   - `PluggedinAppEventLoopLag` - >100ms lag (warning)

4. **Database** (3 alerts):
   - `PluggedinAppDatabaseDown` - No connections (critical)
   - `PluggedinAppSlowDatabaseQueries` - P95 >1s (warning)
   - `PluggedinAppHighDatabaseErrorRate` - >0.1 err/s (critical)

5. **Security** (3 alerts):
   - `PluggedinAppAuthFailureSpike` - >1 failure/sec (warning)
   - `PluggedinAppHighRateLimitHits` - >5 hits/sec (info)
   - `PluggedinAppUnauthorizedAccessAttempts` - >2 err/sec (warning)

6. **Business Metrics** (3 alerts):
   - `PluggedinAppNoUserActivity` - No auth users for 15m (info)
   - `PluggedinAppHighDocumentUploadFailures` - >20% failures (warning)
   - `PluggedinAppSlowDocumentProcessing` - P95 >30s (warning)

7. **MCP Integration** (2 alerts):
   - `PluggedinAppMcpProxyDown` - MCP proxy unreachable (critical)
   - `PluggedinAppHighMcpErrorRate` - >0.5 err/sec (warning)

8. **External Dependencies** (2 alerts):
   - `PluggedinAppRagBackendDown` - api.plugged.in down (critical)
   - `PluggedinAppRegistryProxyDown` - Registry unavailable (warning)

9. **Deployment** (2 alerts):
   - `PluggedinAppFrequentRestarts` - >3 restarts in 15m (warning)
   - `PluggedinAppConfigurationError` - 503 errors on health (critical)

10. **Detailed Alert Annotations**:
    - Summary, description, runbook for every alert
    - Severity labels: critical, warning, info
    - Category labels: availability, performance, security, etc.

### 5. Grafana Dashboard

#### Dashboard Configuration
**File**: `pluggedin-observability/grafana/dashboards/pluggedin-app.json`

**Panels** (20+ visualizations organized in 7 rows):

**Row 1: Service Health Overview**
- Service Status (UP/DOWN indicator)
- Request Rate (req/s gauge)
- Error Rate (percentage gauge)
- P95 Latency (seconds stat)
- Memory Usage (heap percentage graph)

**Row 2: HTTP Traffic & Performance**
- Request Rate by Status Code (stacked area chart)
- Response Time Percentiles (P50, P95, P99 line chart)

**Row 3: Authentication & Security**
- Authentication Events (bar chart by event type)
- Error Rate by Type (stacked area by error type)

**Row 4: Document Operations & RAG**
- Document Operations Rate (line chart by operation)
- Document Processing Duration P95 (line chart by operation)

**Row 5: Database & Resources**
- Database Query Duration P95 (line chart by operation)
- Node.js Memory Usage (heap used/total/external)

**Row 6: Application Logs**
- Error Logs Panel (Loki data source, live tail)

**Dashboard Features**:
- Auto-refresh: 10 seconds
- Time range: Last 1 hour (configurable)
- Prometheus + Loki datasources
- Dark theme
- Responsive layout

### 6. Network Configuration

**Firewall Rules Required**:

On **Monitoring Server** (monitoring.plugged.in):
```bash
# Allow Loki push from pluggedin-app server
ufw allow from <PLUGGEDIN_APP_IP> to any port 3100 proto tcp
```

On **Pluggedin-App Server** (plugged.in):
```bash
# Allow Prometheus scraping from monitoring server
ufw allow from 185.96.168.253 to any port 12005 proto tcp
```

**Note**: Monitoring server IP already in pluggedin-app's `METRICS_ALLOWED_IPS` environment variable.

## Deployment Checklist

### On Production Server (plugged.in)

- [ ] Install Promtail v2.9.3
- [ ] Create `/etc/promtail/promtail-config.yml` with correct Loki URL
- [ ] Create systemd service for Promtail
- [ ] Configure log rotation for `/var/log/pluggedin/pluggedin_app.log`
- [ ] Start Promtail: `systemctl start promtail`
- [ ] Verify logs shipping: Check Promtail metrics at `localhost:9080/metrics`
- [ ] Configure firewall rules (if needed)
- [ ] Test Promtail connectivity to Loki

### On Monitoring Server (monitoring.plugged.in)

- [ ] Verify Prometheus scrapes pluggedin-app metrics
- [ ] Check targets page: http://monitoring.plugged.in/prometheus/targets
- [ ] Reload Prometheus: `docker-compose restart prometheus`
- [ ] Verify alert rules loaded: Check Prometheus UI
- [ ] Import Grafana dashboard: `pluggedin-app.json`
- [ ] Test Loki receiving logs: Query `{service="pluggedin-app"}`
- [ ] Configure firewall rules (if needed)

### On Development Machine

- [ ] Pull latest code with middleware updates
- [ ] Rebuild application: `pnpm build`
- [ ] Deploy to production server
- [ ] Restart application: `systemctl restart pluggedin`
- [ ] Verify metrics endpoint: `curl https://plugged.in/api/metrics`
- [ ] Verify health endpoint: `curl https://plugged.in/api/health`

## Testing & Validation

### 1. Verify Metrics Collection

```bash
# On production server
curl http://localhost:12005/api/metrics | head -20

# Expected: Prometheus format metrics including pluggedin_* metrics
```

### 2. Verify Log Shipping

```bash
# On production server
systemctl status promtail
journalctl -u promtail -f

# Expected: No errors, successful log shipping messages
```

### 3. Verify in Grafana

1. Navigate to https://monitoring.plugged.in
2. Go to Explore → Loki
3. Query: `{service="pluggedin-app"}` → See recent logs
4. Go to Explore → Prometheus
5. Query: `up{job="pluggedin-app"}` → Should return 1
6. Open "Pluggedin App Dashboard" → See all panels populated

### 4. Test Alert Rules

```bash
# On monitoring server
docker-compose exec prometheus promtool check rules /etc/prometheus/rules/pluggedin-app-alerts.yml

# Expected: All rules valid, no syntax errors
```

### 5. Generate Test Traffic

```bash
# Generate requests to trigger metrics
curl https://plugged.in/
curl https://plugged.in/api/health
curl https://plugged.in/analytics

# Check metrics updated
curl http://localhost:12005/api/metrics | grep http_requests_total
```

## Useful Queries

### PromQL (Prometheus)

```promql
# Request rate
rate(pluggedin_http_requests_total{job="pluggedin-app"}[5m])

# Error percentage
100 * sum(rate(pluggedin_http_errors_total{job="pluggedin-app"}[5m])) / sum(rate(pluggedin_http_requests_total{job="pluggedin-app"}[5m]))

# P95 latency
histogram_quantile(0.95, rate(pluggedin_http_request_duration_seconds_bucket{job="pluggedin-app"}[5m]))

# Memory usage percentage
100 * (pluggedin_nodejs_heap_size_used_bytes / pluggedin_nodejs_heap_size_total_bytes)

# Active users (last 5 minutes)
count(sum by (userId) (rate(pluggedin_http_requests_total{user_type="authenticated"}[5m])))
```

### LogQL (Loki)

```logql
# All logs
{service="pluggedin-app"}

# Error logs only
{service="pluggedin-app", level="error"}

# Logs with trace ID
{service="pluggedin-app"} | json | trace_id != ""

# Authentication events
{service="pluggedin-app", event="auth"}

# Slow requests (>1s)
{service="pluggedin-app"} | json | duration_ms > 1000

# Recent errors (rate)
sum(rate({service="pluggedin-app", level="error"}[5m]))
```

## Troubleshooting

### Metrics Not Appearing in Prometheus

1. **Check app is running**: `systemctl status pluggedin`
2. **Test metrics endpoint**: `curl http://localhost:12005/api/metrics`
3. **Check Prometheus targets**: https://monitoring.plugged.in/prometheus/targets
4. **Verify IP whitelisting**: Check `METRICS_ALLOWED_IPS` environment variable
5. **Check network connectivity**: From monitoring server, `curl https://plugged.in/api/metrics`
6. **Review Prometheus logs**: `docker-compose logs prometheus`

### Logs Not Appearing in Loki

1. **Check Promtail status**: `systemctl status promtail`
2. **View Promtail logs**: `journalctl -u promtail -n 100`
3. **Test Loki connectivity**: `curl http://<MONITORING_SERVER_IP>:3100/ready`
4. **Check log file exists**: `ls -lh /var/log/pluggedin/pluggedin_app.log`
5. **Verify log format is JSON**: `tail /var/log/pluggedin/pluggedin_app.log`
6. **Check firewall**: `ufw status | grep 3100`
7. **Review Loki logs**: `docker-compose logs loki`

### High Memory Usage

1. **Check heap usage**: Query `pluggedin_nodejs_heap_size_used_bytes`
2. **Review event loop lag**: Query `pluggedin_nodejs_eventloop_lag_seconds`
3. **Check for memory leaks**: Use Node.js heap profiler
4. **Restart if critical**: `systemctl restart pluggedin`
5. **Review recent code changes**: Check for unclosed connections

### Alerts Not Firing

1. **Verify alert rules loaded**: https://monitoring.plugged.in/prometheus/rules
2. **Check Prometheus config**: `docker-compose exec prometheus promtool check rules /etc/prometheus/rules/pluggedin-app-alerts.yml`
3. **Manually query alert condition**: Test PromQL in Prometheus UI
4. **Check Alertmanager configured**: Uncomment in `prometheus.yml`
5. **Review alert thresholds**: May need adjustment based on baseline

## Maintenance

### Weekly Tasks
- Review Grafana dashboards for anomalies
- Check alert notifications (false positives/negatives)
- Verify log shipping continues working
- Review disk space on both servers

### Monthly Tasks
- Review and optimize slow queries (database alerts)
- Analyze authentication failure patterns
- Review error rates and common error types
- Update alert thresholds based on trends

### Quarterly Tasks
- Review alert rules effectiveness
- Update dashboard panels based on usage
- Test disaster recovery (restore from backups)
- Audit log retention policies

## References

- **Production Setup Guide**: `PRODUCTION_SETUP.md` (step-by-step manual installation)
- **Prometheus Config**: `prometheus/prometheus.yml`
- **Alert Rules**: `prometheus/rules/pluggedin-app-alerts.yml`
- **Grafana Dashboard**: `grafana/dashboards/pluggedin-app.json`
- **Main Observability Docs**: `README.md`

## Change Log

**2025-11-10 - Initial Integration**
- Added request/response logging middleware with trace IDs
- Created HTTP metrics module with 13+ custom metrics
- Implemented health check endpoint (`/api/health`)
- Created 40+ alert rules across 10 categories
- Built comprehensive Grafana dashboard (20+ panels)
- Documented production server setup procedure
