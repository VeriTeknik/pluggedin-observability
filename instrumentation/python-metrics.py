"""
Prometheus Metrics Instrumentation for FastAPI/Python Services

Installation:
pip install prometheus-client

Usage:
1. Import this module in your FastAPI app
2. Add the metrics endpoint
3. Use middleware for automatic HTTP metrics collection
"""

import os
import time
from functools import wraps
from typing import Callable, Optional

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CollectorRegistry,
    CONTENT_TYPE_LATEST,
    multiprocess,
    REGISTRY,
)

# Create registry
registry = CollectorRegistry()

# Add default labels
SERVICE_NAME = os.getenv("SERVICE_NAME", "pluggedin-service")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# ========================================
# Custom Metrics Definitions
# ========================================

# HTTP Request Counter
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code", "service"],
    registry=registry,
)

# HTTP Request Duration
http_request_duration = Histogram(
    "http_request_duration_seconds",
    "Duration of HTTP requests in seconds",
    ["method", "endpoint", "status_code", "service"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10],
    registry=registry,
)

# HTTP Request Size
http_request_size = Histogram(
    "http_request_size_bytes",
    "Size of HTTP requests in bytes",
    ["method", "endpoint", "service"],
    buckets=[100, 1000, 5000, 10000, 50000, 100000, 500000, 1000000],
    registry=registry,
)

# HTTP Response Size
http_response_size = Histogram(
    "http_response_size_bytes",
    "Size of HTTP responses in bytes",
    ["method", "endpoint", "status_code", "service"],
    buckets=[100, 1000, 5000, 10000, 50000, 100000, 500000, 1000000],
    registry=registry,
)

# Active Requests
active_requests = Gauge(
    "http_requests_active",
    "Number of active HTTP requests",
    ["service"],
    registry=registry,
)

# Database Query Duration
db_query_duration = Histogram(
    "db_query_duration_seconds",
    "Duration of database queries in seconds",
    ["operation", "table"],
    buckets=[0.001, 0.01, 0.05, 0.1, 0.5, 1, 2, 5],
    registry=registry,
)

# Database Connection Pool
db_connection_pool = Gauge(
    "db_connection_pool_size",
    "Current database connection pool size",
    ["database", "state"],
    registry=registry,
)

# Vector Search Metrics (Milvus)
vector_search_duration = Histogram(
    "vector_search_duration_seconds",
    "Duration of vector search operations",
    ["collection", "operation"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2, 5, 10],
    registry=registry,
)

vector_search_results = Histogram(
    "vector_search_results_count",
    "Number of results from vector search",
    ["collection"],
    buckets=[1, 5, 10, 20, 50, 100, 500],
    registry=registry,
)

# Document Processing Metrics
document_processing_duration = Histogram(
    "document_processing_duration_seconds",
    "Duration of document processing",
    ["document_type", "status"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30, 60],
    registry=registry,
)

document_chunks = Histogram(
    "document_chunks_count",
    "Number of chunks created from document",
    ["document_type"],
    buckets=[1, 5, 10, 20, 50, 100, 500, 1000],
    registry=registry,
)

# RAG Query Metrics
rag_query_duration = Histogram(
    "rag_query_duration_seconds",
    "Duration of RAG queries",
    ["status"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
    registry=registry,
)

rag_queries_total = Counter(
    "rag_queries_total",
    "Total number of RAG queries",
    ["status"],
    registry=registry,
)

# LLM API Metrics
llm_api_calls = Counter(
    "llm_api_calls_total",
    "Total number of LLM API calls",
    ["provider", "model", "status"],
    registry=registry,
)

llm_api_duration = Histogram(
    "llm_api_duration_seconds",
    "Duration of LLM API calls",
    ["provider", "model"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
    registry=registry,
)

llm_tokens_used = Counter(
    "llm_tokens_used_total",
    "Total number of tokens used",
    ["provider", "model", "type"],
    registry=registry,
)


# ========================================
# FastAPI Middleware
# ========================================

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware to automatically track HTTP metrics

    Usage:
    from fastapi import FastAPI
    from metrics import MetricsMiddleware

    app = FastAPI()
    app.add_middleware(MetricsMiddleware)
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Increment active requests
        active_requests.labels(service=SERVICE_NAME).inc()

        # Track request size
        request_size = int(request.headers.get("content-length", 0))
        if request_size > 0:
            http_request_size.labels(
                method=request.method,
                endpoint=request.url.path,
                service=SERVICE_NAME,
            ).observe(request_size)

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration = time.time() - start_time

        # Get response size
        response_size = int(response.headers.get("content-length", 0))

        # Record metrics
        http_requests_total.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
            service=SERVICE_NAME,
        ).inc()

        http_request_duration.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
            service=SERVICE_NAME,
        ).observe(duration)

        if response_size > 0:
            http_response_size.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code,
                service=SERVICE_NAME,
            ).observe(response_size)

        # Decrement active requests
        active_requests.labels(service=SERVICE_NAME).dec()

        return response


# ========================================
# Metrics Endpoint
# ========================================

def get_metrics() -> tuple[bytes, str]:
    """
    Get Prometheus metrics

    Usage in FastAPI:
    from fastapi import Response
    from metrics import get_metrics

    @app.get("/metrics")
    async def metrics():
        data, content_type = get_metrics()
        return Response(content=data, media_type=content_type)
    """
    data = generate_latest(registry)
    return data, CONTENT_TYPE_LATEST


# ========================================
# Helper Functions & Decorators
# ========================================

def track_time(metric: Histogram, labels: dict):
    """
    Decorator to track execution time

    Usage:
    @track_time(db_query_duration, {"operation": "SELECT", "table": "users"})
    async def get_users():
        return await db.query("SELECT * FROM users")
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                metric.labels(**labels).observe(duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                metric.labels(**labels).observe(duration)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class Timer:
    """
    Context manager for timing operations

    Usage:
    with Timer(db_query_duration, {"operation": "INSERT", "table": "docs"}):
        await db.execute("INSERT INTO docs ...")
    """

    def __init__(self, metric: Histogram, labels: dict):
        self.metric = metric
        self.labels = labels
        self.start = None

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start
        self.metric.labels(**self.labels).observe(duration)


def update_db_connection_pool(database: str, total: int, idle: int, active: int):
    """
    Update database connection pool metrics

    Usage:
    update_db_connection_pool("main", total=20, idle=5, active=15)
    """
    db_connection_pool.labels(database=database, state="total").set(total)
    db_connection_pool.labels(database=database, state="idle").set(idle)
    db_connection_pool.labels(database=database, state="active").set(active)


# ========================================
# Example Usage
# ========================================

"""
# Example 1: FastAPI app with metrics
from fastapi import FastAPI, Response
from metrics import MetricsMiddleware, get_metrics

app = FastAPI()
app.add_middleware(MetricsMiddleware)

@app.get("/metrics")
async def metrics():
    data, content_type = get_metrics()
    return Response(content=data, media_type=content_type)


# Example 2: Track database queries
from metrics import track_time, db_query_duration

@track_time(db_query_duration, {"operation": "SELECT", "table": "users"})
async def get_users():
    return await db.query("SELECT * FROM users")


# Example 3: Track vector search
from metrics import vector_search_duration, vector_search_results

async def search_vectors(query_vector, top_k=10):
    with Timer(vector_search_duration, {"collection": "documents", "operation": "search"}):
        results = await milvus_client.search(
            collection_name="documents",
            data=[query_vector],
            limit=top_k
        )

    vector_search_results.labels(collection="documents").observe(len(results[0]))
    return results


# Example 4: Track document processing
from metrics import document_processing_duration, document_chunks

async def process_document(file_path: str, doc_type: str):
    start = time.time()

    try:
        chunks = await chunk_document(file_path)
        document_chunks.labels(document_type=doc_type).observe(len(chunks))

        duration = time.time() - start
        document_processing_duration.labels(
            document_type=doc_type,
            status="success"
        ).observe(duration)

        return chunks
    except Exception as e:
        duration = time.time() - start
        document_processing_duration.labels(
            document_type=doc_type,
            status="error"
        ).observe(duration)
        raise


# Example 5: Track RAG queries
from metrics import rag_query_duration, rag_queries_total

async def rag_query(question: str):
    start = time.time()

    try:
        answer = await generate_answer(question)
        duration = time.time() - start

        rag_queries_total.labels(status="success").inc()
        rag_query_duration.labels(status="success").observe(duration)

        return answer
    except Exception as e:
        duration = time.time() - start

        rag_queries_total.labels(status="error").inc()
        rag_query_duration.labels(status="error").observe(duration)

        raise


# Example 6: Track LLM API calls
from metrics import llm_api_calls, llm_api_duration, llm_tokens_used

async def call_openai(prompt: str, model: str = "gpt-4"):
    start = time.time()

    try:
        response = await openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )

        duration = time.time() - start

        llm_api_calls.labels(
            provider="openai",
            model=model,
            status="success"
        ).inc()

        llm_api_duration.labels(
            provider="openai",
            model=model
        ).observe(duration)

        llm_tokens_used.labels(
            provider="openai",
            model=model,
            type="prompt"
        ).inc(response.usage.prompt_tokens)

        llm_tokens_used.labels(
            provider="openai",
            model=model,
            type="completion"
        ).inc(response.usage.completion_tokens)

        return response.choices[0].message.content

    except Exception as e:
        duration = time.time() - start

        llm_api_calls.labels(
            provider="openai",
            model=model,
            status="error"
        ).inc()

        raise
"""
