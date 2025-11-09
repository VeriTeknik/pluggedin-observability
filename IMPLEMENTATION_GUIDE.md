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

#### 1.3. Create Metrics Endpoint with IP Whitelisting

**File**: `app/api/metrics/route.ts`

⚠️ **SECURITY CRITICAL**: The metrics endpoint exposes sensitive operational data including:
- Request rates and patterns
- Error rates and types
- System performance metrics
- Business metrics (user sessions, OAuth flows, etc.)
- Database query patterns

**NEVER** leave this endpoint publicly accessible. Always implement IP whitelisting.

```typescript
import { NextRequest, NextResponse } from 'next/server';
import { getMetrics } from '@/lib/metrics';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

/**
 * Check if an IP address is allowed to access metrics
 * Supports both exact IP matches and CIDR notation
 */
function isIpAllowed(clientIp: string | null): boolean {
  if (!clientIp) {
    console.warn('[Metrics] No client IP detected, denying access');
    return false;
  }

  // Get allowed IPs from environment variable
  // Default: localhost + common Docker networks
  const allowedIpsEnv = process.env.METRICS_ALLOWED_IPS || '127.0.0.1,::1,172.17.0.0/16,172.18.0.0/16,10.0.0.0/8';
  const allowedIps = allowedIpsEnv.split(',').map(ip => ip.trim());

  // Check exact IP match first
  if (allowedIps.includes(clientIp)) {
    return true;
  }

  // Check CIDR ranges
  for (const allowedIp of allowedIps) {
    if (allowedIp.includes('/')) {
      if (isIpInCidr(clientIp, allowedIp)) {
        return true;
      }
    }
  }

  return false;
}

/**
 * Check if an IP is within a CIDR range
 * Supports IPv4 only for simplicity
 */
function isIpInCidr(ip: string, cidr: string): boolean {
  try {
    const [range, bits] = cidr.split('/');
    const mask = ~(2 ** (32 - parseInt(bits)) - 1);

    const ipNum = ipToNumber(ip);
    const rangeNum = ipToNumber(range);

    return (ipNum & mask) === (rangeNum & mask);
  } catch (error) {
    console.error('[Metrics] Invalid CIDR range:', cidr, error);
    return false;
  }
}

/**
 * Convert IPv4 address to number
 */
function ipToNumber(ip: string): number {
  return ip.split('.').reduce((acc, octet) => (acc << 8) + parseInt(octet), 0) >>> 0;
}

/**
 * Extract client IP from request headers
 * Checks X-Forwarded-For, X-Real-IP, and connection
 */
function getClientIp(request: NextRequest): string | null {
  // Check X-Forwarded-For (proxy/load balancer)
  const forwardedFor = request.headers.get('x-forwarded-for');
  if (forwardedFor) {
    // Take the first IP (original client)
    return forwardedFor.split(',')[0].trim();
  }

  // Check X-Real-IP (nginx)
  const realIp = request.headers.get('x-real-ip');
  if (realIp) {
    return realIp.trim();
  }

  // Fallback to direct connection IP (not available in Next.js edge runtime)
  return null;
}

export async function GET(request: NextRequest) {
  try {
    // Security: IP whitelisting
    const clientIp = getClientIp(request);

    if (!isIpAllowed(clientIp)) {
      console.warn('[Metrics] Unauthorized access attempt from IP:', clientIp);
      return NextResponse.json(
        { error: 'Forbidden - IP not whitelisted' },
        { status: 403 }
      );
    }

    const metrics = await getMetrics();

    return new NextResponse(metrics, {
      headers: {
        'Content-Type': 'text/plain; version=0.0.4; charset=utf-8',
        'Cache-Control': 'no-store, no-cache, must-revalidate',
      },
    });
  } catch (error) {
    console.error('[Metrics] Error generating metrics:', error);
    return NextResponse.json(
      { error: 'Failed to generate metrics' },
      { status: 500 }
    );
  }
}
```

#### 1.3.1. Configure IP Whitelisting

Add to `.env`:

```bash
# Metrics Endpoint Security
# Comma-separated list of allowed IPs and CIDR ranges for Prometheus scraping
# Default: localhost and common Docker networks (Docker uses 172.17.0.0/16, 172.18.0.0/16, 10.0.0.0/8)
# Only these IPs can access /api/metrics endpoint - CRITICAL for privacy and security
# Example: METRICS_ALLOWED_IPS="127.0.0.1,::1,172.18.0.0/24,10.0.0.0/8,185.96.168.246"
METRICS_ALLOWED_IPS="127.0.0.1,::1,172.17.0.0/16,172.18.0.0/16,10.0.0.0/8"
```

**Configuration Examples**:

1. **Local development** (default):
   ```bash
   METRICS_ALLOWED_IPS="127.0.0.1,::1"
   ```

2. **Docker Compose** (Prometheus in same Docker network):
   ```bash
   METRICS_ALLOWED_IPS="127.0.0.1,::1,172.17.0.0/16,172.18.0.0/16"
   ```

3. **Production** (Prometheus on specific server):
   ```bash
   METRICS_ALLOWED_IPS="127.0.0.1,::1,185.96.168.246"
   ```

4. **Production with Docker** (Prometheus server + Docker networks):
   ```bash
   METRICS_ALLOWED_IPS="127.0.0.1,::1,172.17.0.0/16,185.96.168.246"
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

# Test 1: Security - Verify IP whitelisting works
# From localhost (should succeed - 200 OK)
curl http://localhost:12005/api/metrics

# Test 2: From unauthorized IP (should fail - 403 Forbidden)
# Use a proxy or different machine to test
curl http://your-domain.com/api/metrics
# Expected: {"error":"Forbidden - IP not whitelisted"}

# Test 3: Verify Prometheus format output
curl http://localhost:12005/api/metrics | head -20

# You should see Prometheus format output:
# http_requests_total{method="GET",route="/",status_code="200",service="pluggedin-app"} 1
# mcp_sessions_active{transport="sse",server_type="stdio"} 5
# ...

# Test 4: Check security logs
# Check application logs for security events
# Should see: "[Metrics] Unauthorized access attempt from IP: x.x.x.x" for blocked requests

# Test 5: Verify from Docker network (if using Docker)
docker exec prometheus wget -O- http://pluggedin-app:12005/api/metrics
# Should succeed if Docker network CIDR is in METRICS_ALLOWED_IPS
```

**Security Testing Checklist**:
- ✅ Localhost access works (127.0.0.1, ::1)
- ✅ Docker network access works (if applicable)
- ✅ External unauthorized access is blocked (403)
- ✅ Prometheus server can scrape successfully
- ✅ Security violations are logged

### Checklist

- [ ] Install dependencies (`prom-client`, `pino`, `pino-pretty`)
- [ ] Copy metrics and logging files
- [ ] Create `/api/metrics` endpoint **with IP whitelisting** (CRITICAL)
- [ ] Configure `METRICS_ALLOWED_IPS` in `.env` file (REQUIRED)
- [ ] Add middleware for HTTP metrics
- [ ] Add business metrics to server actions
- [ ] Add structured logging to API routes
- [ ] Update Prometheus config
- [ ] **Test metrics endpoint security** (verify 403 for unauthorized IPs)
- [ ] Test metrics endpoint (verify 200 for allowed IPs)
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
**URL**: https://api.plugged.in
**Current Status**: ✅ Instrumented

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
  - job_name: 'api-server'
    metrics_path: '/metrics'
    scheme: 'https'
    static_configs:
      - targets: ['api.plugged.in']
        labels:
          service: 'api.plugged.in'
          component: 'rag-backend'
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

- [x] Install dependencies (`prometheus-client`, `python-json-logger`)
- [x] Update `requirements.txt`
- [x] Copy instrumentation files
- [x] Add middleware to FastAPI app
- [x] Create `/metrics` endpoint
- [x] Create `/health` endpoint
- [x] Add RAG-specific metrics (document processing, vector search, queries)
- [x] Add LLM API call tracking
- [x] Add structured logging to endpoints
- [x] Update Prometheus config
- [x] Test locally
- [x] Deploy to production

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
   up{job=~"pluggedin-app|registry-proxy|api-server|postgres"}
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
   - [x] plugged_in_v3_server (api.plugged.in) - COMPLETED
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

### Issue: Metrics endpoint returns 403 Forbidden

**Cause**: IP whitelisting is blocking the request

**Solution 1**: Add the Prometheus server IP to `METRICS_ALLOWED_IPS`
```bash
# Check what IP Prometheus is using
docker-compose exec prometheus ip addr

# Add to .env
METRICS_ALLOWED_IPS="127.0.0.1,::1,172.17.0.0/16,YOUR_PROMETHEUS_IP"
```

**Solution 2**: For Docker deployments, allow the Docker network CIDR
```bash
# Find Docker network subnet
docker network inspect pluggedin-observability_monitoring | grep Subnet

# Add the subnet to METRICS_ALLOWED_IPS
METRICS_ALLOWED_IPS="127.0.0.1,::1,172.17.0.0/16,172.18.0.0/16"
```

**Solution 3**: Check if IP is being detected correctly
```typescript
// Add temporary logging in app/api/metrics/route.ts
console.log('[Metrics] Client IP detected:', clientIp);
console.log('[Metrics] X-Forwarded-For:', request.headers.get('x-forwarded-for'));
console.log('[Metrics] X-Real-IP:', request.headers.get('x-real-ip'));
```

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

## Security Best Practices

### 🔒 Metrics Endpoint Security

⚠️ **CRITICAL**: Metrics endpoints expose sensitive operational data. **ALWAYS** implement IP whitelisting for ALL services.

#### What Data Is Exposed?

Metrics endpoints reveal:
- **Performance Data**: Request rates, latencies, error rates
- **System Resources**: Memory usage, CPU usage, disk I/O
- **Business Metrics**: User sessions, OAuth flows, API usage patterns
- **Database Patterns**: Query counts, connection pool usage
- **Infrastructure Details**: Service versions, deployment topology

#### Why This Is a Privacy Issue

Without IP whitelisting:
- ❌ Competitors can analyze your traffic patterns
- ❌ Attackers can identify performance bottlenecks for DoS attacks
- ❌ Users' behavioral patterns become visible through aggregated metrics
- ❌ Business metrics (growth rates, feature usage) are exposed
- ❌ System weaknesses are revealed for targeted attacks

#### Implementation Requirements

**All services MUST**:
1. ✅ Implement IP whitelisting on `/metrics` endpoint
2. ✅ Support CIDR notation for Docker networks
3. ✅ Extract client IP from proxy headers (X-Forwarded-For, X-Real-IP)
4. ✅ Return 403 Forbidden for unauthorized access
5. ✅ Log unauthorized access attempts for security monitoring
6. ✅ Use environment variables for IP configuration (never hardcode)

**Default Allowed IPs** (minimum):
```bash
METRICS_ALLOWED_IPS="127.0.0.1,::1,172.17.0.0/16,172.18.0.0/16,10.0.0.0/8"
```

**Production Configuration**:
```bash
# Only allow Prometheus server IP + localhost
METRICS_ALLOWED_IPS="127.0.0.1,::1,YOUR_PROMETHEUS_SERVER_IP"
```

#### Per-Service Implementation

- **Next.js** (pluggedin-app): See section 1.3 for full implementation
- **Node.js/Express**: Add IP whitelisting middleware before metrics endpoint
- **Python/FastAPI**: Use dependency injection for IP validation
- **Docker**: Ensure Docker network CIDRs are in whitelist

#### Testing Security

Before deploying to production:

```bash
# 1. Test from localhost (should succeed)
curl http://localhost:PORT/metrics

# 2. Test from external IP (should fail with 403)
curl http://your-domain.com/metrics

# 3. Verify Prometheus can scrape (should succeed)
curl http://prometheus-server-ip:9090/targets

# 4. Check security logs for violations
grep "Unauthorized access attempt" logs/*.log
```

---

## Support

- **Documentation**: See main [README.md](./README.md)
- **Instrumentation**: See [instrumentation/README.md](./instrumentation/README.md)
- **Database Monitoring**: See [observability_readme.md](./observability_readme.md)
- **Security**: See **Security Best Practices** section above
- **Issues**: Open issue in pluggedin-observability repo

---

## Summary

| Service | Priority | Status | ETA |
|---------|----------|--------|-----|
| pluggedin-app | High | ⏳ Pending | Week 2 |
| registry-proxy | High | ⏳ Pending | Week 3 |
| plugged_in_v3_server (api.plugged.in) | High | ✅ Complete | Done |
| pluggedin-mcp | Medium | ⏳ Pending | Week 4 |
| PostgreSQL | High | ✅ Ready | Week 1 |
| Milvus | Medium | 📋 Manual | Week 3 |

**Estimated Total Time**: 4-5 weeks for full implementation
