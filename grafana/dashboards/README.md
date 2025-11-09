# Grafana Dashboards

This directory contains pre-configured Grafana dashboards for the Plugged.in observability stack.

## Available Dashboards

### 1. System Overview (`overview.json`)

**Purpose**: High-level view of all services in the ecosystem

**Panels**:
- Service health status (up/down)
- Request rates across all services
- Error rates
- System resource usage (CPU, memory, disk)

**Use Case**: First dashboard to check for overall system health

---

### 2. RAG API Dashboard (`rag-api.json`) ⭐

**Purpose**: Comprehensive monitoring for api.plugged.in (FastAPI RAG backend)

**Dashboard Sections**:

#### 🎯 Service Health & Overview
- **API Status**: Up/Down indicator with color coding
- **Request Rate**: Real-time HTTP requests/second
- **Error Rate (5xx)**: Gauge showing server error percentage
- **P95 Latency**: 95th percentile response time

#### 🤖 RAG Query Metrics
- **Query Rate by Status**: Success vs Error rates over time
- **Duration Percentiles**: P50, P95, P99 query latency
- **Error Rate Gauge**: Real-time RAG query error percentage
- **Query Counters**: Total queries (last hour, 24h, failures)

#### 📄 Document Processing
- **Processing Duration**: Time to process documents by type (PDF, DOCX, etc.)
- **Average Chunks**: Document chunking statistics
- **Error Rate**: Document upload failure percentage
- **Counters**: Documents processed, chunks created, failed uploads

#### 🔍 Vector Search Performance
- **Search Latency**: P50, P95, P99 vector search duration
- **Average Results**: Search result counts over time
- **Search Rate**: Vector searches per second
- **Total Searches**: Hourly and daily counters

#### 🧠 LLM API Metrics (OpenAI)
- **API Call Rate**: Requests by model and status
- **API Latency**: P50/P95 duration by model
- **Error Rate**: OpenAI API failure percentage
- **Token Usage**: Total tokens consumed (24h)
- **Call Counters**: API calls per hour/day

#### 📊 HTTP Traffic Details
- **Request Rate by Endpoint**: Traffic distribution across API endpoints
- **Request Rate by Status**: 2xx, 4xx, 5xx status code distribution
- **Duration by Endpoint**: P50/P95 latency per endpoint
- **Active Requests**: Current concurrent requests
- **Request Counters**: Total HTTP requests (hour/day)

**Key Metrics to Watch**:
- Error rates should be < 5%
- P95 latency should be < 2s for HTTP, < 10s for RAG queries
- Vector search P95 should be < 5s
- OpenAI API error rate should be < 10%

**Alerts**:
This dashboard integrates with the alert rules defined in `prometheus/rules/alerts.yml`

---

## Dashboard Configuration

### Auto-Refresh
All dashboards are configured with **30-second auto-refresh** by default. You can change this in the top-right corner of Grafana.

### Time Range
Default time range is **Last 6 hours**. Adjust as needed:
- Last 5 minutes - for real-time debugging
- Last 1 hour - for recent trends
- Last 24 hours - for daily patterns
- Last 7 days - for weekly analysis

### Variables
Some dashboards support variables for filtering:
- **Service**: Filter by specific service
- **Environment**: production/staging/development
- **Instance**: Specific service instance

## Using the Dashboards

### 1. Access Grafana
```
URL: https://monitoring.plugged.in
Username: admin
Password: (from .env file)
```

### 2. Navigate to Dashboards
- Click "Dashboards" (📊 icon) in the left sidebar
- Browse or search for dashboards
- Star your favorites for quick access

### 3. Explore Data
- **Zoom**: Click and drag on any graph
- **Time Range**: Use the time picker (top-right)
- **Refresh**: Click refresh icon or enable auto-refresh
- **Inspect**: Click panel title → "Inspect" for raw data

### 4. Create Alerts
- Click panel title → "Edit"
- Go to "Alert" tab
- Configure alert conditions
- Set notification channels

## Importing Dashboards

### From This Repository
Dashboards are automatically provisioned from this directory when the stack starts.

To manually import:
1. Go to Grafana → Dashboards → Import
2. Upload JSON file from this directory
3. Select Prometheus datasource
4. Click "Import"

### From Grafana.com
Import community dashboards:
```
1. Go to Dashboards → Import
2. Enter dashboard ID:
   - PostgreSQL: 9628
   - Node Exporter: 1860
   - Docker: 893
   - Traefik: 12250
3. Select datasource
4. Import
```

## Creating Custom Dashboards

### Quick Start
1. Go to Dashboards → New → New Dashboard
2. Add Panel
3. Select Visualization (Time series, Gauge, Stat, etc.)
4. Write PromQL query
5. Configure display options
6. Save dashboard

### Example PromQL Queries

#### Request Rate
```promql
sum(rate(http_requests_total{service="api.plugged.in"}[5m]))
```

#### Error Rate Percentage
```promql
100 * sum(rate(http_requests_total{status=~"5.."}[5m])) /
sum(rate(http_requests_total[5m]))
```

#### P95 Latency
```promql
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

#### RAG Query Success Rate
```promql
sum(rate(rag_queries_total{status="success"}[5m]))
```

#### OpenAI API Calls by Model
```promql
sum(rate(llm_api_calls_total{provider="openai"}[5m])) by (model)
```

## Best Practices

### Dashboard Design
- **Group related metrics**: Use rows to organize panels
- **Use appropriate visualizations**:
  - Time series for trends
  - Gauges for thresholds
  - Stats for counters
- **Set meaningful thresholds**: Green/Yellow/Red color coding
- **Add descriptions**: Panel descriptions help team understanding

### Performance
- **Limit time range**: Shorter ranges = faster queries
- **Use recording rules**: For complex/frequent queries
- **Set reasonable refresh rates**: 30s is usually sufficient
- **Use variables wisely**: Too many slows down loading

### Maintenance
- **Document custom dashboards**: Add descriptions and annotations
- **Version control**: Export JSON and commit to git
- **Test after changes**: Verify panels load correctly
- **Share with team**: Star important dashboards

## Troubleshooting

### Dashboard Not Loading
1. Check Prometheus is running: `docker-compose ps prometheus`
2. Verify datasource: Grafana → Configuration → Data Sources
3. Test query in Explore tab first
4. Check browser console for errors

### No Data Showing
1. Verify time range includes data
2. Check service is being scraped: http://localhost:9090/targets
3. Test query in Prometheus: http://localhost:9090/graph
4. Verify metric names match (case-sensitive)

### Slow Dashboard
1. Reduce time range
2. Increase auto-refresh interval
3. Simplify complex queries
4. Use recording rules for expensive queries

## Support

- **PromQL Documentation**: https://prometheus.io/docs/prometheus/latest/querying/basics/
- **Grafana Documentation**: https://grafana.com/docs/grafana/latest/
- **Dashboard Examples**: https://grafana.com/grafana/dashboards/

For issues or questions, open an issue in the pluggedin-observability repository.
