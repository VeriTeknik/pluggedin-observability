/**
 * Prometheus Metrics Instrumentation for Node.js/Next.js Services
 *
 * Installation:
 * npm install prom-client
 *
 * Usage:
 * 1. Import this module in your app initialization
 * 2. Add the metrics endpoint to your API routes
 * 3. Use middleware for automatic HTTP metrics collection
 */

import { Registry, Counter, Histogram, Gauge, collectDefaultMetrics } from 'prom-client';
import type { Request, Response, NextFunction } from 'express';

// Create a Registry to register metrics
export const register = new Registry();

// Add a default label which is added to all metrics
register.setDefaultLabels({
  app: process.env.APP_NAME || 'pluggedin-service',
  environment: process.env.NODE_ENV || 'development',
});

// Enable collection of default metrics (CPU, memory, event loop, etc.)
collectDefaultMetrics({
  register,
  prefix: 'nodejs_',
  gcDurationBuckets: [0.001, 0.01, 0.1, 1, 2, 5],
  eventLoopMonitoringPrecision: 10,
});

// ========================================
// Custom Metrics Definitions
// ========================================

// HTTP Request Counter
export const httpRequestsTotal = new Counter({
  name: 'http_requests_total',
  help: 'Total number of HTTP requests',
  labelNames: ['method', 'route', 'status_code', 'service'],
  registers: [register],
});

// HTTP Request Duration Histogram
export const httpRequestDuration = new Histogram({
  name: 'http_request_duration_seconds',
  help: 'Duration of HTTP requests in seconds',
  labelNames: ['method', 'route', 'status_code', 'service'],
  buckets: [0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10],
  registers: [register],
});

// HTTP Request Size
export const httpRequestSize = new Histogram({
  name: 'http_request_size_bytes',
  help: 'Size of HTTP requests in bytes',
  labelNames: ['method', 'route', 'service'],
  buckets: [100, 1000, 5000, 10000, 50000, 100000, 500000, 1000000],
  registers: [register],
});

// HTTP Response Size
export const httpResponseSize = new Histogram({
  name: 'http_response_size_bytes',
  help: 'Size of HTTP responses in bytes',
  labelNames: ['method', 'route', 'status_code', 'service'],
  buckets: [100, 1000, 5000, 10000, 50000, 100000, 500000, 1000000],
  registers: [register],
});

// Active Requests Gauge
export const activeRequests = new Gauge({
  name: 'http_requests_active',
  help: 'Number of active HTTP requests',
  labelNames: ['service'],
  registers: [register],
});

// Database Connection Pool
export const dbConnectionPool = new Gauge({
  name: 'db_connection_pool_size',
  help: 'Current database connection pool size',
  labelNames: ['database', 'state'],
  registers: [register],
});

// Database Query Duration
export const dbQueryDuration = new Histogram({
  name: 'db_query_duration_seconds',
  help: 'Duration of database queries in seconds',
  labelNames: ['operation', 'table'],
  buckets: [0.001, 0.01, 0.05, 0.1, 0.5, 1, 2, 5],
  registers: [register],
});

// Custom Business Metrics Examples
export const userSignups = new Counter({
  name: 'user_signups_total',
  help: 'Total number of user signups',
  labelNames: ['source'],
  registers: [register],
});

export const documentUploads = new Counter({
  name: 'document_uploads_total',
  help: 'Total number of document uploads',
  labelNames: ['format', 'status'],
  registers: [register],
});

export const ragQueries = new Counter({
  name: 'rag_queries_total',
  help: 'Total number of RAG queries',
  labelNames: ['status'],
  registers: [register],
});

export const mcpServerConnections = new Gauge({
  name: 'mcp_server_connections_active',
  help: 'Number of active MCP server connections',
  labelNames: ['server_type'],
  registers: [register],
});

// ========================================
// Express Middleware
// ========================================

/**
 * Express middleware to automatically track HTTP metrics
 *
 * Usage:
 * import { metricsMiddleware } from './metrics';
 * app.use(metricsMiddleware);
 */
export function metricsMiddleware(req: Request, res: Response, next: NextFunction) {
  const start = Date.now();
  const serviceName = process.env.SERVICE_NAME || 'unknown';

  // Increment active requests
  activeRequests.inc({ service: serviceName });

  // Track request size if available
  const requestSize = parseInt(req.get('content-length') || '0', 10);
  if (requestSize > 0) {
    httpRequestSize.observe(
      {
        method: req.method,
        route: req.route?.path || req.path,
        service: serviceName
      },
      requestSize
    );
  }

  // Capture response
  const originalSend = res.send;
  res.send = function(data: any) {
    const duration = (Date.now() - start) / 1000;
    const route = req.route?.path || req.path;
    const statusCode = res.statusCode.toString();

    // Record metrics
    httpRequestsTotal.inc({
      method: req.method,
      route,
      status_code: statusCode,
      service: serviceName,
    });

    httpRequestDuration.observe(
      {
        method: req.method,
        route,
        status_code: statusCode,
        service: serviceName,
      },
      duration
    );

    // Track response size
    const responseSize = Buffer.byteLength(data || '', 'utf8');
    httpResponseSize.observe(
      {
        method: req.method,
        route,
        status_code: statusCode,
        service: serviceName,
      },
      responseSize
    );

    // Decrement active requests
    activeRequests.dec({ service: serviceName });

    return originalSend.call(this, data);
  };

  next();
}

// ========================================
// Next.js API Route Handler
// ========================================

/**
 * Next.js API route to expose metrics
 *
 * Create file: app/api/metrics/route.ts
 *
 * import { register } from '@/lib/metrics';
 *
 * export async function GET() {
 *   const metrics = await register.metrics();
 *   return new Response(metrics, {
 *     headers: { 'Content-Type': register.contentType },
 *   });
 * }
 */

// ========================================
// Helper Functions
// ========================================

/**
 * Track database query performance
 *
 * Usage:
 * const end = trackDbQuery('SELECT', 'users');
 * await db.query('SELECT * FROM users');
 * end();
 */
export function trackDbQuery(operation: string, table: string) {
  const start = Date.now();
  return () => {
    const duration = (Date.now() - start) / 1000;
    dbQueryDuration.observe({ operation, table }, duration);
  };
}

/**
 * Update database connection pool metrics
 *
 * Usage (with Drizzle/pg):
 * updateDbConnectionPool('main', pool.totalCount, pool.idleCount);
 */
export function updateDbConnectionPool(
  database: string,
  total: number,
  idle: number
) {
  dbConnectionPool.set({ database, state: 'active' }, total - idle);
  dbConnectionPool.set({ database, state: 'idle' }, idle);
  dbConnectionPool.set({ database, state: 'total' }, total);
}

/**
 * Get all metrics as string (for debugging)
 */
export async function getMetrics(): Promise<string> {
  return register.metrics();
}

/**
 * Reset all metrics (useful for testing)
 */
export function resetMetrics(): void {
  register.resetMetrics();
}

// ========================================
// Example Usage in Next.js Server Actions
// ========================================

/*
// Example: Track document upload in server action
'use server';

import { documentUploads } from '@/lib/metrics';

export async function uploadDocument(formData: FormData) {
  try {
    // ... upload logic ...

    documentUploads.inc({
      format: formData.get('format') as string,
      status: 'success'
    });

    return { success: true };
  } catch (error) {
    documentUploads.inc({
      format: 'unknown',
      status: 'error'
    });

    throw error;
  }
}

// Example: Track RAG query
import { ragQueries } from '@/lib/metrics';

export async function queryRAG(query: string) {
  try {
    const result = await rag.query(query);
    ragQueries.inc({ status: 'success' });
    return result;
  } catch (error) {
    ragQueries.inc({ status: 'error' });
    throw error;
  }
}

// Example: Track MCP connections
import { mcpServerConnections } from '@/lib/metrics';

function updateMcpMetrics() {
  mcpServerConnections.set(
    { server_type: 'stdio' },
    getActiveStdioConnections()
  );
  mcpServerConnections.set(
    { server_type: 'sse' },
    getActiveSseConnections()
  );
}
*/

export default register;
