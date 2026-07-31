"""OpenTelemetry 初始化：Django / Celery / Redis / MySQL → Jaeger (OTLP)。"""

from __future__ import annotations

import os

_initialized = False


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def current_trace_id() -> str:
    """返回当前 span 的 trace_id（32 位 hex），无有效 span 时返回空串。"""
    if not _env_bool("OTEL_ENABLED"):
        return ""

    from opentelemetry import trace

    ctx = trace.get_current_span().get_span_context()
    if ctx.is_valid:
        return format(ctx.trace_id, "032x")
    return ""


def setup_telemetry(*, service_name: str | None = None) -> None:
    """初始化 TracerProvider 并自动 instrument 各组件。

    通过 ``OTEL_ENABLED=true`` 开启；默认关闭，避免本地测试依赖 Jaeger。
    """
    global _initialized
    if _initialized or not _env_bool("OTEL_ENABLED"):
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.dbapi import trace_integration
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    name = service_name or os.environ.get("OTEL_SERVICE_NAME", "appointly-api")
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    provider = TracerProvider(resource=Resource.create({"service.name": name}))
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint, insecure=True),
        )
    )
    trace.set_tracer_provider(provider)

    DjangoInstrumentor().instrument()
    CeleryInstrumentor().instrument()
    RedisInstrumentor().instrument()

    try:
        import MySQLdb

        trace_integration(MySQLdb, "connect", "mysql")
    except ImportError:
        pass

    _initialized = True
