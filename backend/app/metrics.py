"""
Prometheus metrics for full backend visibility.
All metric calls are wrapped to never break the main flow.
"""

from prometheus_client import Counter, Gauge, Histogram

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
download_duration = Histogram(
    "vocify_download_duration_seconds",
    "Twilio recording download duration in seconds",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
)
hubspot_log_duration = Histogram(
    "vocify_hubspot_log_duration_seconds",
    "HubSpot call activity logging duration in seconds",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 60.0),
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
    ["status", "provider", "model"],
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

# Gauge, not Counter: point-in-time count of crm_updates rows stuck in
# 'pending' past their TTL (see CRM_UPDATES_PENDING_TTL_MINUTES in
# app.services.crm_updates). Refreshed periodically by a background task
# (see app.main's startup event), not on every request - a stale-pending row
# doesn't map to a single request/response cycle the way the counters above
# do. A sustained non-zero value means track() reservations are dying
# between reserve and confirm (crashes, hangs) faster than they're being
# resolved - worth alerting on, not just graphing.
crm_updates_stale_pending = Gauge(
    "vocify_crm_updates_stale_pending",
    "crm_updates rows still 'pending' past their TTL - reserved but never confirmed",
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


def record_download_duration(seconds: float) -> None:
    _safe(download_duration.observe, seconds)


def record_hubspot_log_duration(seconds: float) -> None:
    _safe(hubspot_log_duration.observe, seconds)


def inc_pipeline_error(domain: str, phase: str) -> None:
    _safe(pipeline_errors.labels(domain=domain, phase=phase).inc)


def inc_llm_request(status: str, provider: str, model: str) -> None:
    _safe(llm_requests.labels(status=status, provider=provider, model=model).inc)


def inc_webhook_message(provider: str, outcome: str) -> None:
    _safe(webhook_messages.labels(provider=provider, outcome=outcome).inc)


def inc_unipile_api_call(operation: str, status: str) -> None:
    _safe(unipile_api_calls.labels(operation=operation, status=status).inc)


def set_crm_updates_stale_pending(count: int) -> None:
    _safe(crm_updates_stale_pending.set, count)
