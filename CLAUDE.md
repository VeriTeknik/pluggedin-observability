# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the **Plugged.in Observability Stack** - a complete monitoring solution for the Plugged.in ecosystem using Prometheus (metrics), Grafana (dashboards), Loki (logs), and Traefik (reverse proxy). It monitors 10+ distributed services across the platform.

**Monitoring Domain**: `monitoring.plugged.in`

## Architecture

The stack follows a centralized observability pattern:
- **Metrics Collection**: Prometheus scrapes `/metrics` endpoints from instrumented services
- **Log Aggregation**: Promtail collects logs and ships to Loki (requires JSON format)
- **Visualization**: Grafana provides unified dashboards with Prometheus & Loki datasources
- **Reverse Proxy**: Traefik handles HTTPS, Let's Encrypt certificates, and routing
- **Exporters**: postgres-exporter, node-exporter, and cadvisor provide infrastructure metrics

## Key Commands

### Development & Testing

```bash
# Start the entire stack
docker-compose up -d

# View logs for specific service
docker-compose logs -f <service>  # grafana, prometheus, loki, etc.

# Check all services status
docker-compose ps

# Restart a service after config changes
docker-compose restart <service>

# Stop the stack
docker-compose down

# Stop and remove volumes (DESTRUCTIVE - deletes all data)
docker-compose down -v
```

### Prometheus Operations

```bash
# Reload Prometheus config (after editing prometheus.yml)
curl -X POST http://localhost:9090/-/reload
# OR
docker-compose restart prometheus

# Validate Prometheus config
docker-compose exec prometheus promtool check config /etc/prometheus/prometheus.yml

# Check alert rules
docker-compose exec prometheus promtool check rules /etc/prometheus/rules/alerts.yml

# Query Prometheus targets status
curl http://localhost:9090/api/v1/targets

# Query specific metric
curl 'http://localhost:9090/api/v1/query?query=up{service="pluggedin-app"}'
```

### Testing Metrics Endpoints

```bash
# Test metrics endpoint is accessible
curl http://localhost:9187/metrics  # postgres-exporter
curl https://plugged.in/api/metrics  # pluggedin-app (Next.js)
curl https://registry.plugged.in/metrics  # registry-proxy

# Check if service is being scraped
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.service=="your-service")'
```

## Configuration Files

### Critical Configuration Files

- `docker-compose.yml` - Service definitions and networking
- `prometheus/prometheus.yml` - Metrics scraping configuration
- `prometheus/rules/alerts.yml` - Alert rules
- `loki/loki-config.yml` - Log aggregation configuration
- `grafana/provisioning/datasources/datasources.yml` - Grafana datasources
- `.env` - Environment variables (domain, passwords, etc.)

### Adding a New Service to Monitor

1. **Instrument the service** (see `instrumentation/` directory):
   - Node.js: Copy `nodejs-metrics.ts` and `nodejs-logging.ts`
   - Python: Copy `python-metrics.py` and `python-logging.py`
   - Add `/metrics` endpoint that returns Prometheus format
   - Configure JSON structured logging

2. **Add scrape config** to `prometheus/prometheus.yml`:
   ```yaml
   - job_name: 'my-service'
     metrics_path: '/metrics'
     scheme: 'https'  # or 'http'
     static_configs:
       - targets: ['service.plugged.in']
         labels:
           service: 'my-service'
           environment: 'production'
     scrape_interval: 30s
     scrape_timeout: 10s
   ```

3. **Reload Prometheus**: `docker-compose restart prometheus`

4. **Verify in Grafana**: Query `up{service="my-service"}` should return 1

## Service-Specific Notes

### Monitored Services

The stack monitors these services (see `prometheus/prometheus.yml` for complete list):
- **pluggedin-app**: Next.js app at `plugged.in` (metrics at `/api/metrics`)
- **registry-proxy**: Node.js proxy at `registry.plugged.in` (metrics at `/metrics`)
- **mcp-proxy**: MCP server at `mcp.plugged.in` (metrics at `/metrics`)
- **api.plugged.in**: FastAPI RAG backend (metrics at `/metrics`) - ✅ fully instrumented
- **PostgreSQL**: Via postgres-exporter (requires `POSTGRES_EXPORTER_DSN` in `.env`)
- **System metrics**: Via node-exporter (CPU, memory, disk)
- **Container metrics**: Via cadvisor (Docker container stats)

### Instrumentation Files

Located in `instrumentation/` directory:
- `nodejs-metrics.ts` - Prometheus client for Node.js with HTTP metrics, histograms, counters
- `nodejs-logging.ts` - Pino-based structured JSON logging
- `python-metrics.py` - Prometheus client for Python/FastAPI with middleware
- `python-logging.py` - Python JSON logger configuration
- `README.md` - Comprehensive instrumentation guide with examples

**Key Instrumentation Points**:
- All HTTP services must expose `/metrics` endpoint returning Prometheus format
- All logs must be JSON formatted for Loki/Promtail parsing
- Use structured logging with trace_id, user_id, operation fields
- Avoid high-cardinality labels (no user IDs, session IDs in metrics)

## Grafana Dashboards

Pre-configured dashboards in `grafana/dashboards/`:
- `overview.json` - System-wide overview (all services health, request rates, errors)
- `nodejs.json` - Node.js specific metrics (memory, CPU, event loop)

Import additional dashboards:
- PostgreSQL: Dashboard ID `9628`
- Node Exporter: Dashboard ID `1860`
- Docker: Dashboard ID `893`
- Traefik: Dashboard ID `12250`

## Alert Rules

Alerts defined in `prometheus/rules/alerts.yml`:

**Service Health**:
- ServiceDown: Service unreachable for 2+ minutes (critical)
- HighErrorRate: >5% error rate (warning)
- VeryHighErrorRate: >15% error rate (critical)

**Performance**:
- HighLatency: p95 >2s (warning)
- VeryHighLatency: p95 >5s (critical)

**Resources**:
- HighMemoryUsage: >80% memory (warning)
- HighCPUUsage: >80% CPU (warning)
- HighDiskUsage: >80% disk (warning)

**Database**:
- PostgreSQLDown: Database unreachable (critical)
- HighDatabaseConnections: >80% connection pool (warning)
- SlowQueries: Queries >60s (warning)

## Important Constraints

### Metrics Best Practices

1. **Cardinality**: Keep label combinations under control
   - ✅ Good: `{method="GET", status="200", service="app"}`
   - ❌ Bad: `{user_id="12345", session_id="abc"}` (unbounded cardinality)

2. **Histogram Buckets**: Pre-configured appropriate ranges
   - Latency: `[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10]` seconds
   - Sizes: `[100, 1000, 10000, 100000, 1000000]` bytes

3. **Retention**: Default 15 days for Prometheus and Loki (configurable in `.env`)

### Logging Best Practices

1. **Always use JSON format** - Promtail requires JSON for parsing
2. **Include trace_id** - For request correlation across services
3. **No sensitive data** - Never log passwords, API keys, tokens
4. **Appropriate log levels** - Use debug sparingly, error for actionable issues

## Common Workflows

### Debugging "Service Metrics Not Appearing"

1. Verify metrics endpoint works: `curl http://service:port/metrics`
2. Check Prometheus targets: http://localhost:9090/targets
3. Look for scrape errors in Prometheus logs: `docker-compose logs prometheus`
4. Verify service is in correct Docker network: `docker network inspect pluggedin-observability_monitoring`
5. Check if Prometheus config has correct scheme (http vs https)

### Debugging "Logs Not Appearing in Loki"

1. Verify logs are JSON: `docker logs service-name --tail 10`
2. Check Promtail logs: `docker-compose logs promtail`
3. Query Loki directly: `curl http://localhost:3100/loki/api/v1/labels`
4. Verify Promtail config has correct log paths in `promtail/promtail-config.yml`

### Adding Custom Metrics

Example for Node.js (see `instrumentation/nodejs-metrics.ts` for full template):
```typescript
import { Counter, Histogram } from 'prom-client';
import { register } from './metrics';

const myCounter = new Counter({
  name: 'custom_events_total',
  help: 'Total custom events',
  labelNames: ['event_type', 'status'],
  registers: [register],
});

// Use it
myCounter.inc({ event_type: 'payment', status: 'success' });
```

### Environment Variables

Key variables in `.env`:
- `DOMAIN`: Main monitoring domain (default: monitoring.plugged.in)
- `GRAFANA_ADMIN_PASSWORD`: Grafana admin password (MUST change from default)
- `POSTGRES_EXPORTER_DSN`: PostgreSQL connection string for metrics
- `PROMETHEUS_RETENTION`: Metrics retention period (default: 15d)
- `LOKI_RETENTION`: Logs retention period (default: 360h)

## PromQL Query Examples

```promql
# Service availability
up{service="pluggedin-app"}

# Request rate (requests per second)
rate(http_requests_total[5m])

# Error rate percentage
100 * sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))

# 95th percentile latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Memory usage in GB
process_resident_memory_bytes / (1024^3)

# Request count by service
sum by (service) (http_requests_total)
```

## LogQL Query Examples

```logql
# All logs from a service
{service="pluggedin-app"}

# Error logs only
{service="pluggedin-app"} |= "error"

# Filter by trace ID
{service="pluggedin-app"} | json | trace_id="abc123"

# Count errors per minute
sum(rate({service="pluggedin-app"} |= "error" [1m]))
```

## References

- **Main Documentation**: See `README.md` for comprehensive setup guide
- **Implementation Guide**: See `IMPLEMENTATION_GUIDE.md` for step-by-step service instrumentation
- **Instrumentation Examples**: See `instrumentation/README.md` for code examples
- **Database Monitoring**: See `observability_readme.md` for PostgreSQL and Milvus setup
