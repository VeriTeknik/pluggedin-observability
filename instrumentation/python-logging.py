"""
Structured Logging for FastAPI/Python Services

Installation:
pip install python-json-logger

Features:
- JSON structured logs for production
- Automatic trace ID generation
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Integration with Loki via Promtail
- FastAPI request logging middleware
"""

import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Optional

from pythonjsonlogger import jsonlogger

# Context variable for trace ID
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

# ========================================
# Logger Configuration
# ========================================

# Get configuration from environment
SERVICE_NAME = os.getenv("SERVICE_NAME", "pluggedin-service")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

# Create logger
logger = logging.getLogger(SERVICE_NAME)
logger.setLevel(LOG_LEVEL)

# Remove existing handlers
logger.handlers.clear()


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter that adds service metadata
    """

    def add_fields(self, log_record: dict, record: logging.LogRecord, message_dict: dict):
        super().add_fields(log_record, record, message_dict)

        # Add timestamp
        log_record["timestamp"] = self.formatTime(record, self.datefmt)

        # Add service metadata
        log_record["service"] = SERVICE_NAME
        log_record["environment"] = ENVIRONMENT
        log_record["version"] = APP_VERSION

        # Add trace ID from context
        trace_id = trace_id_var.get()
        if trace_id:
            log_record["trace_id"] = trace_id

        # Add log level
        log_record["level"] = record.levelname

        # Add source location
        log_record["logger"] = record.name
        log_record["file"] = record.filename
        log_record["line"] = record.lineno
        log_record["function"] = record.funcName


# Create console handler
console_handler = logging.StreamHandler(sys.stdout)

# Use JSON formatter for production, simple formatter for development
if ENVIRONMENT == "development":
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
else:
    formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(service)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S.%fZ",
    )

console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Prevent propagation to root logger
logger.propagate = False


# ========================================
# Helper Functions
# ========================================

def generate_trace_id() -> str:
    """Generate a unique trace ID"""
    return str(uuid.uuid4())


def set_trace_id(trace_id: str):
    """Set trace ID in context"""
    trace_id_var.set(trace_id)


def get_trace_id() -> Optional[str]:
    """Get trace ID from context"""
    return trace_id_var.get()


def create_logger(name: str, **context) -> logging.LoggerAdapter:
    """
    Create a logger with additional context

    Usage:
    request_logger = create_logger("api", user_id=user.id, request_id=req_id)
    request_logger.info("Processing request")
    """
    return logging.LoggerAdapter(logger, context)


# ========================================
# FastAPI Middleware
# ========================================

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware to add request logging

    Usage:
    from fastapi import FastAPI
    from logging_config import LoggingMiddleware

    app = FastAPI()
    app.add_middleware(LoggingMiddleware)
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Generate or extract trace ID
        trace_id = request.headers.get("x-trace-id") or generate_trace_id()
        set_trace_id(trace_id)

        start_time = time.time()

        # Log incoming request
        logger.info(
            "Incoming request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            },
        )

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Determine log level based on status code
        if response.status_code >= 500:
            log_level = logging.ERROR
        elif response.status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        # Log response
        logger.log(
            log_level,
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

        # Add trace ID to response headers
        response.headers["X-Trace-ID"] = trace_id

        return response


# ========================================
# Decorators
# ========================================

def log_execution(operation: str, **default_context):
    """
    Decorator to log function execution with timing

    Usage:
    @log_execution("database_query", table="users")
    async def get_users():
        return await db.query("SELECT * FROM users")
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            context = {**default_context, "operation": operation}

            logger.debug(f"Starting {operation}", extra=context)

            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start) * 1000

                logger.info(
                    f"Completed {operation}",
                    extra={**context, "duration_ms": round(duration_ms, 2), "status": "success"},
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start) * 1000

                logger.error(
                    f"Failed {operation}",
                    extra={
                        **context,
                        "duration_ms": round(duration_ms, 2),
                        "status": "error",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )

                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            context = {**default_context, "operation": operation}

            logger.debug(f"Starting {operation}", extra=context)

            try:
                result = func(*args, **kwargs)
                duration_ms = (time.time() - start) * 1000

                logger.info(
                    f"Completed {operation}",
                    extra={**context, "duration_ms": round(duration_ms, 2), "status": "success"},
                )

                return result

            except Exception as e:
                duration_ms = (time.time() - start) * 1000

                logger.error(
                    f"Failed {operation}",
                    extra={
                        **context,
                        "duration_ms": round(duration_ms, 2),
                        "status": "error",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )

                raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ========================================
# Context Manager
# ========================================

class Timer:
    """
    Context manager for timing operations with logging

    Usage:
    with Timer("database_query", table="users"):
        await db.execute("SELECT * FROM users")
    """

    def __init__(self, operation: str, **context):
        self.operation = operation
        self.context = context
        self.start = None

    def __enter__(self):
        self.start = time.time()
        logger.debug(f"Starting {self.operation}", extra=self.context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start) * 1000

        if exc_type is None:
            logger.info(
                f"Completed {self.operation}",
                extra={
                    **self.context,
                    "duration_ms": round(duration_ms, 2),
                    "status": "success",
                },
            )
        else:
            logger.error(
                f"Failed {self.operation}",
                extra={
                    **self.context,
                    "duration_ms": round(duration_ms, 2),
                    "status": "error",
                    "error": str(exc_val),
                    "error_type": exc_type.__name__,
                },
                exc_info=True,
            )


# ========================================
# Example Usage
# ========================================

"""
# Example 1: Basic logging
from logging_config import logger

logger.info("Application started")
logger.debug("Debug information", extra={"detail": "value"})
logger.warning("Warning message", extra={"code": "WARN_001"})
logger.error("Error occurred", extra={"error": str(err)}, exc_info=True)


# Example 2: FastAPI app with logging middleware
from fastapi import FastAPI
from logging_config import LoggingMiddleware, logger

app = FastAPI()
app.add_middleware(LoggingMiddleware)

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting", extra={"version": "1.0.0"})


# Example 3: API endpoint with logging
from fastapi import Request
from logging_config import logger, create_logger

@app.get("/api/users")
async def get_users(request: Request):
    log = create_logger("api.users", endpoint="/api/users")

    try:
        log.info("Fetching users")
        users = await db.query.users.findMany()
        log.info("Users fetched", extra={"count": len(users)})

        return {"users": users}

    except Exception as e:
        log.error("Failed to fetch users", exc_info=True)
        raise


# Example 4: Using decorator for automatic logging
from logging_config import log_execution

@log_execution("process_document", document_type="pdf")
async def process_document(file_path: str):
    # ... processing logic ...
    return chunks


# Example 5: Using Timer context manager
from logging_config import Timer

async def search_vectors(query_vector):
    with Timer("vector_search", collection="documents", top_k=10):
        results = await milvus_client.search(
            collection_name="documents",
            data=[query_vector],
            limit=10
        )
    return results


# Example 6: RAG query with comprehensive logging
from logging_config import logger, log_execution, Timer

@log_execution("rag_query")
async def rag_query(question: str):
    logger.info("Processing RAG query", extra={"question_length": len(question)})

    # Embed question
    with Timer("embed_question"):
        embedding = await embed_text(question)

    # Search vectors
    with Timer("vector_search", top_k=5):
        results = await milvus_client.search(
            collection_name="documents",
            data=[embedding],
            limit=5
        )

    logger.info("Vector search completed", extra={"results_count": len(results[0])})

    # Generate answer
    with Timer("llm_generation", model="gpt-4"):
        answer = await generate_answer(question, results)

    logger.info(
        "RAG query completed",
        extra={
            "answer_length": len(answer),
            "sources_used": len(results[0]),
        }
    )

    return answer


# Example 7: Error handling with detailed logging
from logging_config import logger

async def upload_document(file_path: str):
    try:
        logger.info("Starting document upload", extra={"file": file_path})

        # Validate file
        if not os.path.exists(file_path):
            logger.warning("File not found", extra={"file": file_path})
            raise FileNotFoundError(f"File not found: {file_path}")

        # Process document
        chunks = await process_document(file_path)
        logger.info("Document processed", extra={"chunks": len(chunks)})

        # Store in database
        doc_id = await store_document(chunks)
        logger.info("Document stored", extra={"document_id": doc_id})

        return doc_id

    except FileNotFoundError as e:
        logger.error("File not found error", extra={"file": file_path}, exc_info=True)
        raise

    except Exception as e:
        logger.error(
            "Unexpected error during document upload",
            extra={
                "file": file_path,
                "error_type": type(e).__name__,
                "error": str(e),
            },
            exc_info=True,
        )
        raise
"""
