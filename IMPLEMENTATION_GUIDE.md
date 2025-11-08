# Implementation Guide - Service by Service

This guide provides step-by-step instructions for implementing observability in each Plugged.in service.

## Overview

Each service needs:
1. **Metrics endpoint** (`/metrics`) for Prometheus scraping
2. **Structured JSON logging** for Loki aggregation
3. **Health check endpoint** (optional but recommended)

---

## 1. pluggedin-app (Next.js 15)

**Repository**: `pluggedin-app`
**Tech Stack**: Next.js 15, TypeScript, React 19
**Current Status**: ⏳ Needs instrumentation

### Steps

#### 1.1. Install Dependencies

```bash
cd pluggedin-app
pnpm add prom-client pino pino-pretty
```

#### 1.2. Copy Instrumentation Files

```bash
# Copy from observability repo
cp ../pluggedin-observability/instrumentation/nodejs-metrics.ts lib/metrics.ts
cp ../pluggedin-observability/instrumentation/nodejs-logging.ts lib/logging.ts
```

#### 1.3. Create Metrics Endpoint

**File**: `app/api/metrics/route.ts`

```typescript
import { register } from '@/lib/metrics';
import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const metrics = await register.metrics();
    return new NextResponse(metrics, {
      headers: {
        'Content-Type': register.contentType,
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: 'Failed to collect metrics' },
      { status: 500 }
    );
  }
}

// Allow public access for Prometheus scraping
export const dynamic = 'force-dynamic';
```

#### 1.4. Add Middleware for HTTP Metrics

**File**: `middleware.ts` (create or update)

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { httpRequestsTotal, httpRequestDuration } from '@/lib/metrics';

export function middleware(request: NextRequest) {
  const start = Date.now();
  const path = request.nextUrl.pathname;
  const method = request.method;

  // Process request
  const response = NextResponse.next();

  // Track metrics after response
  const duration = (Date.now() - start) / 1000;
  const status = response.status.toString();

  httpRequestsTotal.inc({
    method,
    route: path,
    status_code: status,
    service: 'pluggedin-app',
  });

  httpRequestDuration.observe(
    {
      method,
      route: path,
      status_code: status,
      service: 'pluggedin-app',
    },
    duration
  );

  return response;
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
```

#### 1.5. Add Business Metrics to Server Actions

**Example**: Document upload tracking

```typescript
'use server';

import { documentUploads } from '@/lib/metrics';
import { logger } from '@/lib/logging';

export async function uploadDocument(formData: FormData) {
  const log = logger.child({ action: 'upload-document' });

  try {
    log.info('Starting document upload');

    // ... your upload logic ...

    documentUploads.inc({
      format: formData.get('format') as string,
      status: 'success',
    });

    log.info('Document uploaded successfully', { documentId: doc.id });
    return { success: true, data: doc };
  } catch (error) {
    documentUploads.inc({
      format: 'unknown',
      status: 'error',
    });

    log.error('Document upload failed', { error });
    throw error;
  }
}
```

#### 1.6. Add Logging to API Routes

**Example**: `app/api/users/route.ts`

```typescript
import { logger, generateTraceId } from '@/lib/logging';
import { NextRequest } from 'next/server';

export async function GET(request: NextRequest) {
  const traceId = request.headers.get('x-trace-id') || generateTraceId();
  const log = logger.child({ trace_id: traceId, endpoint: '/api/users' });

  try {
    log.info('Fetching users');
    const users = await db.query.users.findMany();
    log.info('Users fetched', { count: users.length });

    return Response.json(users);
  } catch (error) {
    log.error('Failed to fetch users', { error });
    return Response.json({ error: 'Internal error' }, { status: 500 });
  }
}
```

#### 1.7. Update Prometheus Configuration

Add to `prometheus/prometheus.yml` in observability repo:

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

#### 1.8. Test

```bash
# Start dev server
pnpm dev

# Check metrics endpoint
curl http://localhost:12005/api/metrics

# You should see Prometheus format output:
# http_requests_total{method="GET",route="/",status_code="200",service="pluggedin-app"} 1
```

### Checklist

- [ ] Install dependencies (`prom-client`, `pino`, `pino-pretty`)
- [ ] Copy metrics and logging files
- [ ] Create `/api/metrics` endpoint
- [ ] Add middleware for HTTP metrics
- [ ] Add business metrics to server actions
- [ ] Add structured logging to API routes
- [ ] Update Prometheus config
- [ ] Test metrics endpoint
- [ ] Verify logs are JSON format
- [ ] Deploy to production

---

## 2. registry-proxy (Node.js/Express)

**Repository**: `registry-proxy/proxy`
**Tech Stack**: Node.js, Express, TypeScript
**Current Status**: ⏳ Needs instrumentation

### Steps

#### 2.1. Install Dependencies

```bash
cd registry-proxy/proxy
npm install prom-client pino pino-pretty
```

#### 2.2. Copy Instrumentation Files

```bash
cp ../../pluggedin-observability/instrumentation/nodejs-metrics.ts src/metrics.ts
cp ../../pluggedin-observability/instrumentation/nodejs-logging.ts src/logging.ts
```

#### 2.3. Add to Express App

**File**: `src/index.ts` or `src/app.ts`

```typescript
import express from 'express';
import { register, metricsMiddleware } from './metrics';
import { logger, loggingMiddleware } from './logging';

const app = express();

// Add logging middleware (first)
app.use(loggingMiddleware);

// Add metrics middleware
app.use(metricsMiddleware);

// Metrics endpoint
app.get('/metrics', async (req, res) => {
  try {
    res.set('Content-Type', register.contentType);
    res.end(await register.metrics());
  } catch (error) {
    res.status(500).end(error);
  }
});

// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Your existing routes...
app.get('/registry', async (req, res) => {
  logger.info('Fetching registry data');
  // ... your logic ...
});

app.listen(port, () => {
  logger.info('Server started', { port, environment: process.env.NODE_ENV });
});
```

#### 2.4. Add Custom Metrics

**Example**: Track registry cache hits/misses

```typescript
import { Counter } from 'prom-client';
import { register } from './metrics';

const cacheHits = new Counter({
  name: 'registry_cache_hits_total',
  help: 'Total cache hits',
  labelNames: ['cache_type'],
  registers: [register],
});

const cacheMisses = new Counter({
  name: 'registry_cache_misses_total',
  help: 'Total cache misses',
  labelNames: ['cache_type'],
  registers: [register],
});

// Usage
function getFromCache(key: string) {
  const value = cache.get(key);
  if (value) {
    cacheHits.inc({ cache_type: 'memory' });
    return value;
  } else {
    cacheMisses.inc({ cache_type: 'memory' });
    return null;
  }
}
```

#### 2.5. Update Prometheus Configuration

```yaml
  - job_name: 'registry-proxy'
    metrics_path: '/metrics'
    scheme: 'https'
    static_configs:
      - targets: ['registry.plugged.in']
        labels:
          service: 'registry-proxy'
          environment: 'production'
    scrape_interval: 30s
```

#### 2.6. Test

```bash
# Start server
npm start

# Check metrics
curl http://localhost:3000/metrics

# Check health
curl http://localhost:3000/health
```

### Checklist

- [ ] Install dependencies
- [ ] Copy instrumentation files
- [ ] Add metrics middleware to Express
- [ ] Add logging middleware to Express
- [ ] Create `/metrics` endpoint
- [ ] Create `/health` endpoint
- [ ] Add custom business metrics (cache, registry fetches)
- [ ] Update Prometheus config
- [ ] Test locally
- [ ] Deploy to production

---

## 3. pluggedin-mcp (Node.js MCP Proxy)

**Repository**: `pluggedin-mcp`
**Tech Stack**: Node.js, TypeScript, Express
**Current Status**: ⏳ Not deployed yet (mcp.plugged.in)

### Steps

#### 3.1. Install Dependencies

```bash
cd pluggedin-mcp
npm install prom-client pino pino-pretty
```

#### 3.2. Copy Instrumentation Files

```bash
cp ../pluggedin-observability/instrumentation/nodejs-metrics.ts src/metrics.ts
cp ../pluggedin-observability/instrumentation/nodejs-logging.ts src/logging.ts
```

#### 3.3. Add to MCP Server

**File**: `src/index.ts`

```typescript
import { register, metricsMiddleware } from './metrics';
import { logger, loggingMiddleware } from './logging';
import { Gauge, Counter } from 'prom-client';

// MCP-specific metrics
const mcpConnections = new Gauge({
  name: 'mcp_connections_active',
  help: 'Active MCP server connections',
  labelNames: ['server_type', 'server_name'],
  registers: [register],
});

const mcpRequests = new Counter({
  name: 'mcp_requests_total',
  help: 'Total MCP requests',
  labelNames: ['server_name', 'method', 'status'],
  registers: [register],
});

// Add middleware if using Express
if (app) {
  app.use(loggingMiddleware);
  app.use(metricsMiddleware);

  app.get('/metrics', async (req, res) => {
    res.set('Content-Type', register.contentType);
    res.end(await register.metrics());
  });
}

// Track MCP connections
function handleConnection(serverName: string, serverType: string) {
  logger.info('MCP connection established', { serverName, serverType });
  mcpConnections.inc({ server_type: serverType, server_name: serverName });
}

function handleDisconnection(serverName: string, serverType: string) {
  logger.info('MCP connection closed', { serverName, serverType });
  mcpConnections.dec({ server_type: serverType, server_name: serverName });
}

// Track requests
function handleRequest(serverName: string, method: string, status: string) {
  mcpRequests.inc({ server_name: serverName, method, status });
}
```

#### 3.4. Update Prometheus Configuration

```yaml
  - job_name: 'mcp-proxy'
    metrics_path: '/metrics'
    scheme: 'https'
    static_configs:
      - targets: ['mcp.plugged.in']
        labels:
          service: 'mcp-proxy'
          environment: 'production'
    scrape_interval: 30s
```

### Checklist

- [ ] Install dependencies
- [ ] Copy instrumentation files
- [ ] Add MCP-specific metrics (connections, requests)
- [ ] Create `/metrics` endpoint
- [ ] Add logging for MCP events
- [ ] Update Prometheus config
- [ ] Test locally
- [ ] Deploy to mcp.plugged.in
- [ ] Verify metrics in Grafana

---

## 4. plugged_in_v3_server (FastAPI)

**Repository**: `plugged_in_v3_server`
**Tech Stack**: Python 3.11+, FastAPI
**Current Status**: ⏳ Needs instrumentation

### Steps

#### 4.1. Install Dependencies

```bash
cd plugged_in_v3_server
pip install prometheus-client python-json-logger
```

Update `requirements.txt`:
```txt
prometheus-client==0.19.0
python-json-logger==2.0.7
```

#### 4.2. Copy Instrumentation Files

```bash
cp ../pluggedin-observability/instrumentation/python-metrics.py app/metrics.py
cp ../pluggedin-observability/instrumentation/python-logging.py app/logging_config.py
```

#### 4.3. Add to FastAPI App

**File**: `app/main.py`

```python
from fastapi import FastAPI, Response
from app.metrics import MetricsMiddleware, get_metrics
from app.logging_config import LoggingMiddleware, logger

app = FastAPI(title="Plugged.in v3 RAG Server")

# Add middleware
app.add_middleware(LoggingMiddleware)
app.add_middleware(MetricsMiddleware)

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting", extra={"version": "3.0.0"})

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down")

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    data, content_type = get_metrics()
    return Response(content=data, media_type=content_type)

# Health check
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }
```

#### 4.4. Add RAG-Specific Metrics

**Example**: Track document processing

```python
from app.metrics import (
    document_processing_duration,
    document_chunks,
    vector_search_duration,
    rag_query_duration,
    rag_queries_total,
)
from app.logging_config import logger, log_execution
import time

@log_execution("process_document", document_type="pdf")
async def process_document(file_path: str, doc_type: str):
    start = time.time()

    try:
        # Process document
        chunks = await chunk_document(file_path)

        # Track metrics
        document_chunks.labels(document_type=doc_type).observe(len(chunks))

        duration = time.time() - start
        document_processing_duration.labels(
            document_type=doc_type,
            status="success"
        ).observe(duration)

        logger.info(
            "Document processed",
            extra={"chunks": len(chunks), "duration_ms": duration * 1000}
        )

        return chunks

    except Exception as e:
        duration = time.time() - start
        document_processing_duration.labels(
            document_type=doc_type,
            status="error"
        ).observe(duration)

        logger.error(
            "Document processing failed",
            extra={"error": str(e)},
            exc_info=True
        )
        raise

@log_execution("rag_query")
async def query_rag(question: str):
    start = time.time()

    try:
        # Search vectors
        with Timer(vector_search_duration, {"collection": "documents", "operation": "search"}):
            results = await milvus_client.search(...)

        # Generate answer
        answer = await generate_answer(question, results)

        # Track metrics
        duration = time.time() - start
        rag_queries_total.labels(status="success").inc()
        rag_query_duration.labels(status="success").observe(duration)

        logger.info(
            "RAG query completed",
            extra={
                "question_length": len(question),
                "answer_length": len(answer),
                "duration_ms": duration * 1000
            }
        )

        return answer

    except Exception as e:
        duration = time.time() - start
        rag_queries_total.labels(status="error").inc()
        rag_query_duration.labels(status="error").observe(duration)

        logger.error("RAG query failed", extra={"error": str(e)}, exc_info=True)
        raise
```

#### 4.5. Update Prometheus Configuration

```yaml
  - job_name: 'v3-server'
    metrics_path: '/metrics'
    scheme: 'http'
    static_configs:
      - targets: ['v3-server:8000']  # or your actual host
        labels:
          service: 'rag-backend'
          environment: 'production'
    scrape_interval: 30s
```

#### 4.6. Test

```bash
# Start server
uvicorn app.main:app --reload

# Check metrics
curl http://localhost:8000/metrics

# Check health
curl http://localhost:8000/health

# Trigger some requests and check metrics again
curl http://localhost:8000/api/rag/query -X POST -d '{"query": "test"}'
curl http://localhost:8000/metrics | grep rag_queries_total
```

### Checklist

- [ ] Install dependencies (`prometheus-client`, `python-json-logger`)
- [ ] Update `requirements.txt`
- [ ] Copy instrumentation files
- [ ] Add middleware to FastAPI app
- [ ] Create `/metrics` endpoint
- [ ] Create `/health` endpoint
- [ ] Add RAG-specific metrics (document processing, vector search, queries)
- [ ] Add LLM API call tracking
- [ ] Add structured logging to endpoints
- [ ] Update Prometheus config
- [ ] Test locally
- [ ] Deploy to production

---

## 5. PostgreSQL Monitoring

**Current Status**: ✅ Ready (just needs configuration)

### Steps

#### 5.1. Get Database Connection String

You need the PostgreSQL connection string in this format:
```
postgresql://USERNAME:PASSWORD@HOSTNAME:PORT/DATABASE
```

**Example**:
```
postgresql://postgres:YOUR_SECURE_PASSWORD@your-host.example.com:5432/your_database
```

#### 5.2. Update .env File

In `pluggedin-observability/.env`:

```bash
POSTGRES_EXPORTER_DSN=postgresql://postgres:YOUR_PASSWORD@your-host:5432/pluggedin
```

#### 5.3. Restart Postgres Exporter

```bash
cd pluggedin-observability
docker-compose restart postgres-exporter
```

#### 5.4. Verify

```bash
# Check exporter is running
docker-compose logs postgres-exporter

# Check metrics
curl http://localhost:9187/metrics | grep pg_up

# Should return: pg_up 1
```

### Checklist

- [ ] Get PostgreSQL connection string
- [ ] Update `POSTGRES_EXPORTER_DSN` in `.env`
- [ ] Restart postgres-exporter
- [ ] Verify `pg_up` metric is 1
- [ ] Import PostgreSQL dashboard in Grafana (ID: 9628)

---

## 6. Milvus Monitoring

**Current Status**: 📋 Manual setup required

See detailed instructions in [observability_readme.md](./observability_readme.md#milvus-monitoring)

### Quick Steps

#### 6.1. Enable Milvus Metrics

Edit Milvus config (`milvus.yaml`):

```yaml
metrics:
  enable: true
  port: 9091
  path: /metrics
```

#### 6.2. Restart Milvus

```bash
docker-compose restart milvus-standalone
# or
systemctl restart milvus
```

#### 6.3. Update Prometheus Config

Add to `prometheus/prometheus.yml`:

```yaml
  - job_name: 'milvus'
    static_configs:
      - targets: ['milvus-host:9091']
        labels:
          service: 'milvus'
          instance: 'standalone'
    scrape_interval: 30s
```

#### 6.4. Reload Prometheus

```bash
cd pluggedin-observability
docker-compose restart prometheus
```

### Checklist

- [ ] Enable metrics in Milvus config
- [ ] Restart Milvus
- [ ] Update Prometheus config
- [ ] Reload Prometheus
- [ ] Verify metrics: `curl http://milvus-host:9091/metrics`
- [ ] Create Milvus dashboard in Grafana

---

## Testing Checklist

### Per-Service Testing

For each service:

1. **Metrics Endpoint**
   ```bash
   curl http://service-host/metrics
   # Should return Prometheus format
   ```

2. **Logs Format**
   ```bash
   # Check logs are JSON
   docker logs service-name --tail 10
   # Or check application logs
   ```

3. **Prometheus Scraping**
   ```bash
   # Check targets
   curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.service=="your-service")'
   ```

4. **Query in Grafana**
   - Go to Explore → Prometheus
   - Query: `up{service="your-service"}`
   - Should return value: 1

### Full Stack Testing

1. **All Services Up**
   ```promql
   up{job=~"pluggedin-app|registry-proxy|v3-server|postgres"}
   ```
   All should return 1

2. **Request Metrics**
   ```promql
   rate(http_requests_total[5m])
   ```
   Should show request rates

3. **Logs Appearing**
   - Go to Explore → Loki
   - Query: `{service="pluggedin-app"}`
   - Should show logs

---

## Deployment Order

Recommended order for implementation:

1. **Week 1**: Setup observability stack
   - [ ] Deploy pluggedin-observability to server
   - [ ] Configure DNS (monitoring.plugged.in)
   - [ ] Start stack and verify Grafana access
   - [ ] Configure PostgreSQL exporter

2. **Week 2**: Instrument first service
   - [ ] pluggedin-app (highest priority)
   - [ ] Verify metrics in Grafana
   - [ ] Create custom dashboard

3. **Week 3**: Add remaining services
   - [ ] registry-proxy
   - [ ] plugged_in_v3_server
   - [ ] Configure Milvus monitoring

4. **Week 4**: MCP proxy
   - [ ] Deploy pluggedin-mcp to mcp.plugged.in
   - [ ] Add instrumentation
   - [ ] Verify all services monitored

5. **Week 5**: Fine-tuning
   - [ ] Optimize alert rules
   - [ ] Add notification channels (Slack, email)
   - [ ] Create team dashboards
   - [ ] Document runbooks

---

## Common Issues & Solutions

### Issue: Metrics endpoint returns 404

**Solution**: Verify the endpoint path matches Prometheus config
```yaml
# If endpoint is /api/metrics
metrics_path: '/api/metrics'

# If endpoint is /metrics
metrics_path: '/metrics'
```

### Issue: Logs not in JSON format

**Solution**: Ensure logger is configured for JSON output
```typescript
// Node.js
const logger = pino({
  // ... config must output JSON
});

// Python
formatter = CustomJsonFormatter()
```

### Issue: Prometheus shows "context deadline exceeded"

**Solution**: Increase scrape timeout
```yaml
scrape_timeout: 10s  # Increase if needed
```

### Issue: High cardinality warning

**Solution**: Reduce label values
```typescript
// ❌ Bad - too many unique values
metric.inc({ user_id: user.id });

// ✅ Good - limited values
metric.inc({ user_type: user.type });
```

---

## Support

- **Documentation**: See main [README.md](./README.md)
- **Instrumentation**: See [instrumentation/README.md](./instrumentation/README.md)
- **Database Monitoring**: See [observability_readme.md](./observability_readme.md)
- **Issues**: Open issue in pluggedin-observability repo

---

## Summary

| Service | Priority | Status | ETA |
|---------|----------|--------|-----|
| pluggedin-app | High | ⏳ Pending | Week 2 |
| registry-proxy | High | ⏳ Pending | Week 3 |
| plugged_in_v3_server | High | ⏳ Pending | Week 3 |
| pluggedin-mcp | Medium | ⏳ Pending | Week 4 |
| PostgreSQL | High | ✅ Ready | Week 1 |
| Milvus | Medium | 📋 Manual | Week 3 |

**Estimated Total Time**: 4-5 weeks for full implementation
