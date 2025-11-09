# Plugged.in Observability Stack

Full-stack observability solution for the Plugged.in ecosystem using Prometheus, Grafana, Loki, and Traefik.

## 🎯 Overview

This repository provides a complete observability stack for monitoring 10 distributed services in the Plugged.in ecosystem:

- **Metrics**: Prometheus for time-series metrics collection
- **Visualization**: Grafana for dashboards and analytics
- **Logs**: Loki for log aggregation and querying
- **Reverse Proxy**: Traefik for HTTPS and load balancing
- **Exporters**: PostgreSQL, Node, cAdvisor for infrastructure metrics

**Monitoring Domain**: `monitoring.plugged.in`

## 📊 Architecture

```
┌─────────────────────────────────────────────────┐
│          Grafana (monitoring.plugged.in)        │
│     Unified Dashboards & Visualization          │
└─────────────────────────────────────────────────┘
         ↓              ↓              ↓
    Prometheus       Loki           Traefik
    (Metrics)       (Logs)      (Reverse Proxy)
         ↓              ↓              ↓
┌──────────────────────────────────────────────────┐
│  Monitored Services:                             │
│  • pluggedin-app (Next.js)                       │
│  • registry-proxy (Node.js)                      │
│  • pluggedin-mcp (Node.js) - mcp.plugged.in      │
│  • api.plugged.in (FastAPI RAG backend)          │
│  • PostgreSQL (database)                         │
│  • Milvus (vector database)                      │
└──────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Domain: `monitoring.plugged.in` pointing to your server
- Ports: 80, 443, 8080 available

### Installation

1. **Clone the repository**:
   ```bash
   cd /path/to/your/workspace
   git clone <repo-url> pluggedin-observability
   cd pluggedin-observability
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   nano .env
   ```

   Update the following:
   ```bash
   DOMAIN=monitoring.plugged.in
   EMAIL=admin@plugged.in
   GRAFANA_ADMIN_PASSWORD=your-secure-password
   POSTGRES_EXPORTER_DSN=postgresql://user:pass@host:5432/db
   ```

3. **Start the stack**:
   ```bash
   docker-compose up -d
   ```

4. **Verify deployment**:
   ```bash
   # Check all services are running
   docker-compose ps

   # View logs
   docker-compose logs -f grafana
   ```

5. **Access Grafana**:
   - URL: https://monitoring.plugged.in
   - Username: `admin`
   - Password: (from `.env` file)

6. **Instrument your services**:
   - See **[IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md)** for step-by-step instructions
   - Start with high-priority services (pluggedin-app, api.plugged.in)

## 📦 Services

| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| Grafana | 3000 | https://monitoring.plugged.in | Dashboards & visualization |
| Prometheus | 9090 | https://monitoring.plugged.in/prometheus | Metrics storage & querying |
| Loki | 3100 | https://monitoring.plugged.in/loki | Log aggregation |
| Traefik | 8080 | https://monitoring.plugged.in/traefik | Reverse proxy dashboard |
| Postgres Exporter | 9187 | Internal | PostgreSQL metrics |
| Node Exporter | 9100 | Internal | System metrics |
| cAdvisor | 8080 | Internal | Container metrics |
| Promtail | 9080 | Internal | Log shipper |

## 🔧 Configuration

### Add a New Service to Monitor

1. **Instrument your service** (see [Instrumentation Guide](./instrumentation/README.md))

2. **Add to Prometheus scrape config** (`prometheus/prometheus.yml`):
   ```yaml
   scrape_configs:
     - job_name: 'my-service'
       metrics_path: '/metrics'
       static_configs:
         - targets: ['my-service:3000']
           labels:
             service: 'my-service'
             environment: 'production'
   ```

3. **Reload Prometheus**:
   ```bash
   curl -X POST http://localhost:9090/-/reload
   # or restart
   docker-compose restart prometheus
   ```

4. **Verify in Grafana**:
   - Go to Explore → Prometheus
   - Query: `up{job="my-service"}`

### Configure Alerts

1. **Add alert rules** to `prometheus/rules/alerts.yml`:
   ```yaml
   groups:
     - name: my-service
       rules:
         - alert: MyServiceDown
           expr: up{job="my-service"} == 0
           for: 2m
           labels:
             severity: critical
           annotations:
             summary: "My service is down"
   ```

2. **Reload Prometheus**:
   ```bash
   docker-compose restart prometheus
   ```

3. **View alerts**: http://localhost:9090/alerts

## 📈 Dashboards

### Pre-configured Dashboards

1. **System Overview** (`pluggedin-overview`)
   - All services health status
   - Request rates
   - Error rates

2. **RAG API Dashboard** (`rag-api-dashboard`) ⭐ **NEW**
   - **Service Health**: API status, request rate, error rate, P95 latency
   - **RAG Query Metrics**: Query rate by status, duration percentiles, error rates, total queries
   - **Document Processing**: Processing duration by type, chunk counts, upload success/failure rates
   - **Vector Search**: Search latency, results count, total searches
   - **LLM API Metrics**: OpenAI API calls by model, latency, error rates, token usage
   - **HTTP Traffic**: Request rate by endpoint/status, duration by endpoint, active requests

3. **Node.js Services** (`pluggedin-nodejs`)
   - Memory usage
   - CPU usage
   - Event loop lag
   - Response time percentiles

### Import Additional Dashboards

1. Go to Grafana → Dashboards → Import
2. Use dashboard ID or upload JSON:
   - PostgreSQL: `9628`
   - Node Exporter: `1860`
   - Docker: `893`
   - Traefik: `12250`

### Create Custom Dashboard

1. Go to Grafana → Dashboards → New
2. Add panels with PromQL queries:
   ```promql
   # Request rate
   sum(rate(http_requests_total[5m])) by (service)

   # Error rate
   sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)

   # Latency (p95)
   histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))
   ```

## 📝 Logs

### Query Logs in Grafana

1. Go to Explore → Loki
2. Use LogQL queries:
   ```logql
   # All logs from a service
   {service="pluggedin-app"}

   # Error logs
   {service="pluggedin-app"} |= "error"

   # Filter by trace ID
   {service="pluggedin-app"} | json | trace_id="abc123"

   # Count errors
   sum(rate({service="pluggedin-app"} |= "error" [5m]))
   ```

### Log Retention

- Default: **15 days** (360 hours)
- Configure in `loki/loki-config.yml`:
  ```yaml
  limits_config:
    retention_period: 360h  # Change as needed
  ```

## 🔐 Security

### Basic Authentication

Prometheus endpoint is protected with basic auth. Generate password hash:

```bash
# Install htpasswd
apt-get install apache2-utils

# Generate hash
echo $(htpasswd -nb admin yourpassword) | sed -e s/\\$/\\$\\$/g

# Add to traefik/dynamic/monitoring.yml
```

### HTTPS/TLS

Traefik automatically provisions Let's Encrypt certificates for `monitoring.plugged.in`.

Verify:
```bash
docker-compose logs traefik | grep certificate
```

## 📊 Metrics Reference

### Common Metrics

| Metric | Description | Type |
|--------|-------------|------|
| `up` | Service availability (1=up, 0=down) | Gauge |
| `http_requests_total` | Total HTTP requests | Counter |
| `http_request_duration_seconds` | Request latency | Histogram |
| `http_requests_active` | Active requests | Gauge |
| `process_resident_memory_bytes` | Memory usage | Gauge |
| `process_cpu_seconds_total` | CPU usage | Counter |

### PromQL Examples

```promql
# Request rate (requests/second)
rate(http_requests_total[5m])

# Error rate percentage
100 * sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))

# 95th percentile latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Memory usage in GB
process_resident_memory_bytes / (1024^3)

# CPU usage percentage
100 * rate(process_cpu_seconds_total[5m])
```

## 🚨 Alerting

### Alert Levels

- **Critical**: Immediate action required (service down, critical errors)
- **Warning**: Investigation needed (high latency, resource usage)
- **Info**: Informational (traffic spike, deployment)

### Pre-configured Alerts

See `prometheus/rules/alerts.yml`:

- Service down (any service)
- High error rate (>5%)
- High latency (p95 >2s)
- High memory usage (>80%)
- High CPU usage (>80%)
- PostgreSQL connection pool exhausted
- Slow database queries

### Alert Notifications

Configure in `.env`:

```bash
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
ALERT_EMAIL=ops@plugged.in
PAGERDUTY_KEY=your-key
```

## 📖 Guides

- **[Implementation Guide](./IMPLEMENTATION_GUIDE.md)** - **Step-by-step instructions for each service**
- [Service Instrumentation Guide](./instrumentation/README.md) - Add metrics to your services
- [PostgreSQL & Milvus Monitoring](./observability_readme.md) - Database-specific setup
- [Node.js Instrumentation](./instrumentation/nodejs-metrics.ts) - Node.js metrics example
- [Python Instrumentation](./instrumentation/python-metrics.py) - Python/FastAPI metrics example

## 🐛 Troubleshooting

### Grafana shows "No data"

1. Check Prometheus is scraping:
   ```bash
   curl http://localhost:9090/api/v1/targets
   ```

2. Check service metrics endpoint:
   ```bash
   curl http://your-service:port/metrics
   ```

3. Verify Prometheus config:
   ```bash
   docker-compose exec prometheus promtool check config /etc/prometheus/prometheus.yml
   ```

### Prometheus not scraping service

1. Check network connectivity:
   ```bash
   docker-compose exec prometheus wget -O- http://service:port/metrics
   ```

2. Check Prometheus logs:
   ```bash
   docker-compose logs prometheus | grep ERROR
   ```

3. Verify service is in same network:
   ```bash
   docker network inspect pluggedin-observability_monitoring
   ```

### Loki logs not appearing

1. Check Promtail is running:
   ```bash
   docker-compose logs promtail
   ```

2. Verify log format is JSON:
   ```bash
   docker-compose logs your-service | head -1
   ```

3. Query Loki directly:
   ```bash
   curl http://localhost:3100/loki/api/v1/labels
   ```

### High memory usage

1. Check retention settings in `prometheus.yml` and `loki-config.yml`
2. Reduce scrape interval for less critical services
3. Limit log ingestion rate in Loki config
4. Check for high cardinality metrics (too many label combinations)

### SSL/TLS certificate issues

1. Check Traefik logs:
   ```bash
   docker-compose logs traefik | grep acme
   ```

2. Verify DNS is pointing correctly:
   ```bash
   dig monitoring.plugged.in
   ```

3. Check Let's Encrypt rate limits (max 5 failures per hour)

## 🔄 Maintenance

### Backup

```bash
# Backup Prometheus data
docker-compose exec prometheus tar -czf /backup/prometheus-$(date +%Y%m%d).tar.gz /prometheus

# Backup Grafana dashboards
docker-compose exec grafana tar -czf /backup/grafana-$(date +%Y%m%d).tar.gz /var/lib/grafana

# Backup Loki data
docker-compose exec loki tar -czf /backup/loki-$(date +%Y%m%d).tar.gz /loki
```

### Update

```bash
# Pull latest images
docker-compose pull

# Restart services
docker-compose up -d

# View logs
docker-compose logs -f
```

### Clean Up Old Data

```bash
# Remove old Prometheus data (keeps last 15 days)
# Configured in docker-compose.yml: --storage.tsdb.retention.time=15d

# Remove old Loki data (keeps last 15 days)
# Configured in loki-config.yml: retention_period: 360h

# Clean up unused Docker resources
docker system prune -a --volumes
```

## 📊 Performance Tuning

### Prometheus

- **Scrape interval**: Default 15s, increase to 30s-60s for less critical services
- **Retention**: Default 15 days, reduce for lower storage
- **Sample limit**: Add `sample_limit` to scrape configs for high-cardinality services

### Loki

- **Ingestion rate**: Adjust `ingestion_rate_mb` and `ingestion_burst_size_mb`
- **Query limits**: Tune `max_entries_limit_per_query` and `max_query_length`
- **Compression**: Enable for lower storage (already configured)

### Grafana

- **Query caching**: Enable in datasource settings
- **Dashboard refresh**: Set to 30s or 1m instead of 5s
- **Parallel queries**: Enable for faster dashboard loading

## 🎓 Learning Resources

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Loki Documentation](https://grafana.com/docs/loki/)
- [PromQL Tutorial](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [LogQL Tutorial](https://grafana.com/docs/loki/latest/logql/)

## 📝 Monitored Services

- ✅ **pluggedin-app** - Next.js application (plugged.in)
- ✅ **registry-proxy** - MCP registry proxy (registry.plugged.in)
- ⏳ **pluggedin-mcp** - MCP proxy (mcp.plugged.in) - *deployment pending*
- ✅ **api.plugged.in** - FastAPI RAG backend - *fully instrumented*
- ✅ **PostgreSQL** - Main database (via postgres-exporter)
- 📋 **Milvus** - Vector database (see [observability_readme.md](./observability_readme.md))

## 🤝 Contributing

1. Add new dashboards to `grafana/dashboards/`
2. Add alert rules to `prometheus/rules/`
3. Update documentation
4. Test changes in development environment

## 📄 License

MIT

## 🙋 Support

For issues or questions:
1. Check [Troubleshooting](#troubleshooting) section
2. Review service logs: `docker-compose logs <service>`
3. Open an issue in the repository

---

**Stack Version**:
- Prometheus: v2.48.0
- Grafana: v10.2.2
- Loki: v2.9.3
- Traefik: v2.10

**Retention**: 15 days (configurable)

**Estimated Storage**: 10-15GB for 15 days retention with 4 services
