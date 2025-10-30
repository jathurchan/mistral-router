"""
Observability module: Configures structured JSON logging and Prometheus metrics.

This module provides:
1.  Structured JSON logging setup with request ID correlation.
2.  Prometheus metrics definitions for requests, latency, cost, and tokens.
3.  A context manager for tracking active requests.
4.  A utility function to record metrics from a RequestMetadata object.
"""

import logging
import sys
import time
import json
from typing import Optional
from contextvars import ContextVar
from prometheus_client import (
    Counter, Histogram, Gauge, CollectorRegistry, generate_latest
)

from core.models import RequestMetadata
from app.config import settings

request_id_ctx: ContextVar[Optional[str]] = ContextVar('request_id', default=None) # for correlation across async calls

metrics_registry = CollectorRegistry()

router_requests_total = Counter(
    'router_requests_total',
    'Total number of requests processed',
    ['model', 'status_code', 'fallback'],
    registry=metrics_registry
)

router_request_latency_ms = Histogram(
    'router_request_latency_ms',
    'Request latency in milliseconds',
    ['model'],
    buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
    registry=metrics_registry
)

router_cost_usd = Histogram(
    'router_cost_usd',
    'Request cost in USD',
    ['model'],
    buckets=[0.00001, 0.00005, 0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1],
    registry=metrics_registry
)

router_tokens_total = Counter(
    'router_tokens_total',
    'Total tokens processed',
    ['model', 'type'],  # type: 'input' or 'output'
    registry=metrics_registry
)

router_active_requests = Gauge(
    'router_active_requests',
    'Number of requests currently being processed',
    registry=metrics_registry
)

class RequestIdFilter(logging.Filter):
    """Injects the request_id from the context variable into log records."""
    def filter(self, record):
        record.request_id = request_id_ctx.get() or "none"
        return True

class JsonFormatter(logging.Formatter):
    """Formats log records as a single-line JSON string."""
    
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "none"),
            "message": record.getMessage(),
        }

        extra = {
            k: v for k, v in record.__dict__.items() 
            if k not in log_data and k not in (
                'args', 'asctime', 'created', 'exc_info', 'exc_text', 
                'filename', 'funcName', 'levelname', 'levelno', 'lineno', 
                'module', 'msecs', 'message', 'msg', 'name', 'pathname', 
                'process', 'processName', 'relativeCreated', 'stack_info', 
                'thread', 'threadName'
            )
        }
        log_data.update(extra)

        if record.exc_info:
            log_data['exc_info'] = self.formatException(record.exc_info)

        return json.dumps(log_data)

def setup_logging():
    """
    Configures the root logger for structured JSON logging.
    Removes existing handlers and adds a new one with the JsonFormatter.
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    for h in logger.handlers[:]:
        logger.removeHandler(h)

    # Create new stream handler with our filter and formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter())

    logger.addHandler(handler)

    # Silence overly verbose loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

def track_request_metrics(metadata: RequestMetadata, status_code: int):
    """
    Record Prometheus metrics for a completed request.
    
    Args:
        metadata: The metadata object for the completed request.
        status_code: The HTTP status code of the final response.
    """
    model_label = str(metadata.selected_model)
    fallback_label = str(metadata.fallback_occurred).lower()
    status_label = str(status_code)

    router_requests_total.labels(
        model=model_label,
        status_code=status_label,
        fallback=fallback_label
    ).inc()

    if metadata.latency_ms is not None:
        router_request_latency_ms.labels(model=model_label).observe(
            metadata.latency_ms
        )

    if metadata.is_successful:
        if metadata.cost_usd is not None:
            router_cost_usd.labels(model=model_label).observe(
                metadata.cost_usd
            )
        
        if metadata.tokens_input is not None:
            router_tokens_total.labels(
                model=model_label,
                type="input"
            ).inc(metadata.tokens_input)
        
        if metadata.tokens_output is not None:
            router_tokens_total.labels(
                model=model_label,
                type="output"
            ).inc(metadata.tokens_output)

def get_metrics() -> bytes:
    """
    Get Prometheus metrics in text format.
    
    Returns:
        Metrics in Prometheus exposition format
    """
    return generate_latest(metrics_registry)


class RequestTimer:
    """
    Context manager for timing requests and tracking active ones.
    
    Usage:
        with RequestTimer() as timer:
            # ... do work ...
        latency = timer.elapsed_ms()
    """
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.time()
        router_active_requests.inc()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        router_active_requests.dec()
    
    def elapsed_ms(self) -> float:
        """Get elapsed time in milliseconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        
        if self.start_time:
            return (time.time() - self.start_time) * 1000
            
        return 0.0