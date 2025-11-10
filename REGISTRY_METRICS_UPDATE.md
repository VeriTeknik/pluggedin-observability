# Registry Proxy Metrics - Configuration Update

**Date**: 2025-11-10
**Action Required**: Update Prometheus configuration on monitoring server

---

## Summary

The registry proxy metrics endpoint has been secured and is no longer accessible via public HTTPS. Prometheus must now scrape from the direct port.

## Changes

### OLD Configuration (Insecure)
```yaml
- job_name: 'registry-proxy'
  metrics_path: '/metrics'
  scheme: 'https'
  static_configs:
    - targets: ['registry.plugged.in']  # ❌ Public HTTPS - insecure
```

**Problem**: Anyone could access `https://registry.plugged.in/metrics` and view sensitive application metrics.

### NEW Configuration (Secure)
```yaml
- job_name: 'registry-proxy'
  metrics_path: '/metrics'
  scheme: 'http'
  static_configs:
    - targets: ['185.96.168.251:8090']  # ✅ Direct port - secure
```

**Security**:
- Public HTTPS access blocked (returns 404)
- Port 8090 has IP filtering (only monitoring server 185.96.168.253 allowed)

## Deployment Steps on Monitoring Server

### 1. Update Prometheus Configuration

File: `/path/to/pluggedin-observability/prometheus/prometheus.yml`

Change lines 68-80 from:
```yaml
  # Registry Proxy (Node.js)
  - job_name: 'registry-proxy'
    metrics_path: '/metrics'
    scheme: 'https'
    static_configs:
      - targets: ['registry.plugged.in']
        labels:
          service: 'registry-proxy'
          component: 'api'
          environment: 'production'
    scrape_interval: 30s
    scrape_timeout: 10s
```

To:
```yaml
  # Registry Proxy (Go) - Direct port access (not via HTTPS)
  # Metrics endpoint is blocked from public HTTPS for security
  - job_name: 'registry-proxy'
    metrics_path: '/metrics'
    scheme: 'http'
    static_configs:
      - targets: ['185.96.168.251:8090']
        labels:
          service: 'registry-proxy'
          component: 'api'
          environment: 'production'
    scrape_interval: 30s
    scrape_timeout: 10s
```

### 2. Reload Prometheus Configuration

```bash
# Option 1: Reload via API
curl -X POST http://localhost:9090/-/reload

# Option 2: Restart Prometheus container
docker-compose restart prometheus
```

### 3. Verify Configuration

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.service=="registry-proxy")'

# Expected output:
# {
#   "discoveredLabels": {...},
#   "labels": {
#     "service": "registry-proxy",
#     "component": "api",
#     "environment": "production",
#     ...
#   },
#   "scrapeUrl": "http://185.96.168.251:8090/metrics",
#   "lastError": "",
#   "health": "up"
# }
```

### 4. Test Scraping Manually

```bash
# From monitoring server (185.96.168.253)
curl http://185.96.168.251:8090/metrics

# Should return Prometheus metrics:
# HELP registry_proxy_http_requests_total Total number of HTTP requests
# TYPE registry_proxy_http_requests_total counter
# registry_proxy_http_requests_total{...} 1234
# ...
```

## Verification

### ✅ Expected Behavior After Update

1. **Prometheus target shows UP**
   - Navigate to `http://monitoring-server:9090/targets`
   - Search for "registry-proxy"
   - Status should be "UP" (green)
   - Last scrape should show recent timestamp

2. **Metrics are available in Prometheus**
   ```promql
   # Query in Prometheus
   registry_proxy_http_requests_total

   # Should return data
   ```

3. **Grafana dashboards work**
   - Navigate to Registry Proxy dashboard
   - All panels should display data
   - No "No data" errors

### ❌ Troubleshooting

**Problem**: Target shows DOWN

**Possible causes**:
1. Port 8090 not accessible from monitoring server
2. Firewall blocking port 8090
3. IP filter blocking monitoring server IP

**Solutions**:
```bash
# 1. Test network connectivity
telnet 185.96.168.251 8090

# 2. Test HTTP request
curl -v http://185.96.168.251:8090/metrics

# 3. Check registry server logs
ssh registry-server
docker logs registry-proxy | grep "Metrics access denied"

# 4. Verify monitoring server IP is allowed
# Should see: "Allowed metrics access from CIDR: 185.96.168.253/32"
docker logs registry-proxy | grep "Allowed metrics access"
```

---

**Problem**: "Connection refused"

**Cause**: Port 8090 not exposed or firewall blocking

**Solutions**:
```bash
# On registry server, check port is listening
ss -tlnp | grep 8090

# Check Docker port mapping
docker ps | grep registry-proxy
# Should show: 0.0.0.0:8090->8090/tcp

# Check firewall (if applicable)
sudo ufw status | grep 8090
# If blocked, allow it:
sudo ufw allow from 185.96.168.253 to any port 8090
```

---

**Problem**: "403 Forbidden"

**Cause**: Monitoring server IP not in allowed list

**Solution**:
```bash
# On registry server, check allowed IPs
docker logs registry-proxy | grep "Allowed metrics access"

# Should include:
# "Allowed metrics access from CIDR: 185.96.168.253/32"

# If not, add to /home/pluggedin/registry/proxy/.env:
METRICS_ALLOWED_IPS=127.0.0.1,::1,...,185.96.168.253/32

# Restart proxy
docker-compose restart registry-proxy
```

## Security Benefits

### Before (Insecure)
- ❌ Public HTTPS access allowed
- ❌ Anyone could scrape metrics: `https://registry.plugged.in/metrics`
- ❌ Exposed sensitive application data:
  - Request rates and patterns
  - Error rates
  - Database query performance
  - Cache hit rates
  - Server counts

### After (Secure)
- ✅ Public HTTPS access blocked (404)
- ✅ Only port 8090 accessible
- ✅ IP filtering blocks unauthorized access
- ✅ Only monitoring server (185.96.168.253) can scrape
- ✅ Two-layer security: Traefik + IP filter

## New Error Metrics Available

Once Prometheus starts scraping, these new metrics will appear:

```promql
# Database query errors
registry_proxy_database_query_errors_total{operation="enhanced_servers"}

# Specific error types (e.g., array parameter bug)
registry_proxy_database_errors_total{error_type="array_parameter"}

# Filter parameter errors
registry_proxy_filter_errors_total{endpoint="/v0/enhanced/servers", filter_type="registry_types"}

# Error log count
registry_proxy_error_logs_total{level="error"}
```

**Alert Rules** (already configured):
- `DatabaseQueryErrors` - Critical when rate > 0.1 errors/sec
- `ArrayParameterErrors` - Critical when rate > 0 (should never fire after fix)
- `FilterParameterErrors` - Warning when rate > 0.1 errors/sec
- `HighErrorLogCount` - Warning when rate > 2 errors/sec

## Updated Dashboards

The Registry Proxy Grafana dashboard now includes:
1. Error Logs by Endpoint (bar chart)
2. Recent Error Logs (live viewer)
3. 5xx Errors by Endpoint (time series)
4. Error Details Table
5. Total Errors (stat panel)
6. Enhanced Endpoint Errors (specific tracking)
7. Error Distribution by Endpoint (pie chart)
8. Database Query Errors (filtered logs)

## Contact

For issues or questions:
- **Registry Server**: 185.96.168.251
- **Monitoring Server**: 185.96.168.253
- **Registry Service**: `registry-proxy` container on registry server
- **Logs**: `docker logs registry-proxy` on registry server

---

**Deployment Status**: Ready for deployment
**Breaking Change**: Yes - requires Prometheus config update
**Downtime Required**: No - zero downtime update
