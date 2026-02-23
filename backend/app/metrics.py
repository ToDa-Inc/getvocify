"""
Prometheus metrics for full backend visibility.
All metric calls are wrapped to never break the main flow.
"""

from prometheus_client import Counter, Histogram

# Histograms for latency
transcription_duration = Histogram(
    "vocify_transcription_duration_seconds",
    "Transcription duration in seconds",
    ["source"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 180.0),
)
extraction_duration = Histogram(
    "vocify_extraction_duration_seconds",
    "LLM extraction duration in seconds",
    buckets=(0.5, 2.0, 5.0, 10.0, 20.0, 45.0),
)
sync_duration = Histogram(
    "vocify_sync_duration_seconds",
    "HubSpot sync duration in seconds",
    ["result"],
    buckets=(1.0, 3.0, 5.0, 10.0, 20.0, 60.0),
)

# Counters for errors and throughput
pipeline_errors = Counter(
    "vocify_pipeline_errors_total",
    "Pipeline errors by domain and phase",
    ["domain", "phase"],
)
llm_requests = Counter(
    "vocify_llm_requests_total",
    "LLM API requests",
    ["status", "model"],
)
webhook_messages = Counter(
    "vocify_webhook_messages_total",
    "Webhook messages processed",
    ["provider", "outcome"],
)
unipile_api_calls = Counter(
    "vocify_unipile_api_calls_total",
    "Unipile API calls",
    ["operation", "status"],
)


def _safe(fn, *args, **kwargs) -> None:
    """Run metric operation; swallow any error."""
    try:
        fn(*args, **kwargs)
    except Exception:
        pass


def record_transcription_duration(seconds: float, source: str) -> None:
    _safe(transcription_duration.labels(source=source).observe, seconds)


def record_extraction_duration(seconds: float) -> None:
    _safe(extraction_duration.observe, seconds)


def record_sync_duration(seconds: float, result: str) -> None:
    _safe(sync_duration.labels(result=result).observe, seconds)


def inc_pipeline_error(domain: str, phase: str) -> None:
    _safe(pipeline_errors.labels(domain=domain, phase=phase).inc)


def inc_llm_request(status: str, model: str) -> None:
    _safe(llm_requests.labels(status=status, model=model).inc)


def inc_webhook_message(provider: str, outcome: str) -> None:
    _safe(webhook_messages.labels(provider=provider, outcome=outcome).inc)


def inc_unipile_api_call(operation: str, status: str) -> None:
    _safe(unipile_api_calls.labels(operation=operation, status=status).inc)
