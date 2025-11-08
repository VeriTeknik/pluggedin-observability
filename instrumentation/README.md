# Service Instrumentation Guide

This directory contains instrumentation examples for adding metrics and logging to your services.

## Overview

Proper instrumentation enables:
- **Metrics**: Quantitative measurements (request rate, latency, errors)
- **Logs**: Detailed event records with context
- **Traces**: Request flow across services (future: distributed tracing)

## Quick Start

### Node.js Services

**1. Install dependencies:**
```bash
npm install prom-client pino pino-pretty
```

**2. Add metrics:**
```typescript
// lib/metrics.ts
import { register, metricsMiddleware } from './instrumentation/nodejs-metrics';

// In your app
app.use(metricsMiddleware);

// Metrics endpoint (Express)
app.get('/metrics', async (req, res) => {
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
});

// Metrics endpoint (Next.js API route)
// app/api/metrics/route.ts
import { register } from '@/lib/metrics';

export async function GET() {
  const metrics = await register.metrics();
  return new Response(metrics, {
    headers: { 'Content-Type': register.contentType },
  });
}
```

**3. Add logging:**
```typescript
// lib/logging.ts
import { logger, loggingMiddleware } from './instrumentation/nodejs-logging';

// In your app
app.use(loggingMiddleware);

// Use logger
logger.info('Application started');
logger.error('Error occurred', { error: err });
```

### Python Services

**1. Install dependencies:**
```bash
pip install prometheus-client python-json-logger
```

**2. Add metrics:**
```python
# metrics.py
from instrumentation.python_metrics import MetricsMiddleware, get_metrics
from fastapi import FastAPI, Response

app = FastAPI()
app.add_middleware(MetricsMiddleware)

@app.get("/metrics")
async def metrics():
    data, content_type = get_metrics()
    return Response(content=data, media_type=content_type)
```

**3. Add logging:**
```python
# logging_config.py
from instrumentation.python_logging import LoggingMiddleware, logger

app.add_middleware(LoggingMiddleware)

# Use logger
logger.info("Application started")
logger.error("Error occurred", extra={"error": str(err)}, exc_info=True)
```

## Available Metrics

### Common HTTP Metrics (All Services)

- `http_requests_total` - Total request count
- `http_request_duration_seconds` - Request latency histogram
- `http_request_size_bytes` - Request size histogram
- `http_response_size_bytes` - Response size histogram
- `http_requests_active` - Active requests gauge

### Node.js Specific Metrics

- `nodejs_eventloop_lag_seconds` - Event loop lag
- `nodejs_heap_size_total_bytes` - Heap size
- `nodejs_heap_size_used_bytes` - Heap usage
- `nodejs_gc_duration_seconds` - GC duration

### Database Metrics

- `db_query_duration_seconds` - Query execution time
- `db_connection_pool_size` - Connection pool stats
- `pg_up` - PostgreSQL availability (from postgres-exporter)

### RAG/AI Specific Metrics (Python)

- `vector_search_duration_seconds` - Milvus search latency
- `vector_search_results_count` - Search results count
- `document_processing_duration_seconds` - Document processing time
- `document_chunks_count` - Chunks per document
- `rag_query_duration_seconds` - RAG query latency
- `rag_queries_total` - RAG query counter
- `llm_api_calls_total` - LLM API call counter
- `llm_api_duration_seconds` - LLM API latency
- `llm_tokens_used_total` - Token usage counter

### Business Metrics

- `user_signups_total` - User signup counter
- `document_uploads_total` - Document upload counter
- `mcp_server_connections_active` - Active MCP connections

## Custom Metrics Examples

### Node.js

```typescript
import { Counter, Histogram } from 'prom-client';

// Define custom metric
const customCounter = new Counter({
  name: 'custom_events_total',
  help: 'Total custom events',
  labelNames: ['event_type', 'status'],
  registers: [register],
});

// Use it
customCounter.inc({ event_type: 'payment', status: 'success' });
```

### Python

```python
from prometheus_client import Counter

# Define custom metric
custom_counter = Counter(
    'custom_events_total',
    'Total custom events',
    ['event_type', 'status'],
    registry=registry
)

# Use it
custom_counter.labels(event_type='payment', status='success').inc()
```

## Logging Best Practices

### 1. Use Structured Logging

**✅ Good:**
```typescript
logger.info('User logged in', {
  userId: user.id,
  email: user.email,
  loginMethod: 'oauth',
});
```

**❌ Bad:**
```typescript
logger.info(`User ${user.email} logged in via oauth`);
```

### 2. Include Context

Always include:
- `trace_id` - For request correlation
- `user_id` - For user-specific issues
- `operation` - What was being done
- `duration_ms` - Performance tracking

### 3. Choose Appropriate Log Levels

- `debug` - Detailed debugging (disabled in production)
- `info` - Important events (startup, successful operations)
- `warn` - Recoverable issues (retries, fallbacks)
- `error` - Errors that need attention
- `fatal` - Critical errors requiring immediate action

### 4. Log Errors with Stack Traces

**Node.js:**
```typescript
try {
  await riskyOperation();
} catch (error) {
  logger.error('Operation failed', {
    error: error instanceof Error ? error.message : String(error),
    stack: error instanceof Error ? error.stack : undefined,
    operation: 'riskyOperation',
  });
}
```

**Python:**
```python
try:
    risky_operation()
except Exception as e:
    logger.error(
        "Operation failed",
        extra={"operation": "risky_operation"},
        exc_info=True
    )
```

## Performance Considerations

### Metrics

1. **Cardinality**: Keep label combinations low
   - ✅ Good: `{method="GET", status="200"}`
   - ❌ Bad: `{user_id="12345", session_id="abc..."}` (too many unique values)

2. **Histogram Buckets**: Choose appropriate buckets
   - Latency: `[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10]` seconds
   - Size: `[100, 1000, 10000, 100000, 1000000]` bytes

3. **Sample Rate**: Use sampling for high-volume metrics if needed

### Logging

1. **Log Level**: Use appropriate levels (avoid `debug` in production)
2. **Sensitive Data**: Never log passwords, API keys, tokens
3. **Volume**: Avoid logging in tight loops
4. **Async**: Use async logging in high-traffic services

## Testing Instrumentation

### 1. Verify Metrics Endpoint

```bash
# Node.js
curl http://localhost:3000/metrics

# Python
curl http://localhost:8000/metrics
```

### 2. Check Prometheus Scraping

```bash
# Check if service is discovered
curl http://localhost:9090/api/v1/targets

# Query metrics
curl 'http://localhost:9090/api/v1/query?query=up{service="pluggedin-app"}'
```

### 3. Verify Logs in Loki

```bash
# Via Grafana Explore
# Or using LogCLI
logcli query '{service="pluggedin-app"}' --limit=10
```

## Troubleshooting

### Metrics Not Appearing

1. Check endpoint is accessible: `curl http://service/metrics`
2. Verify Prometheus configuration in `prometheus/prometheus.yml`
3. Check Prometheus targets: http://localhost:9090/targets
4. Look for scrape errors in Prometheus logs

### Logs Not Appearing

1. Check log format is JSON (required for Promtail parsing)
2. Verify Promtail configuration in `promtail/promtail-config.yml`
3. Check Promtail logs for parsing errors
4. Query Loki directly: http://localhost:3100/loki/api/v1/labels

### High Cardinality Issues

If Prometheus is slow:
1. Check metric cardinality: http://localhost:9090/tsdb-status
2. Remove high-cardinality labels (user IDs, session IDs, etc.)
3. Use aggregation or sampling

## Next Steps

1. **Add instrumentation** to your service using examples above
2. **Deploy service** with metrics endpoint enabled
3. **Verify in Grafana** that metrics are appearing
4. **Create custom dashboards** for your specific use cases
5. **Set up alerts** for critical metrics

## Resources

- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [Grafana Loki Documentation](https://grafana.com/docs/loki/latest/)
- [Node.js prom-client](https://github.com/siimon/prom-client)
- [Python prometheus-client](https://github.com/prometheus/client_python)
- [Pino Logging](https://getpino.io/)
- [Python JSON Logger](https://github.com/madzak/python-json-logger)
