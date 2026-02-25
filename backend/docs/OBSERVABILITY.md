# Vocify Backend Observability

Full visibility for logic, AI processing, LLM, Speechmatics, extraction, and HubSpot sync.

## Grafana Setup

See [GRAFANA_SETUP.md](./GRAFANA_SETUP.md) for step-by-step Grafana Cloud setup (Metrics Endpoint, auth, dashboard import).

## Log Format

Set `LOG_JSON=true` in production for structured logs. One JSON object per line.

**Fields:** `timestamp`, `level`, `logger`, `message`, `domain`, `phase`, `correlation_id`, plus domain-specific fields (e.g. `memo_id`, `job_id`, `duration_ms`).

**Domains:** `transcription`, `extraction`, `llm`, `hubspot`, `whatsapp`, `webhook`, `memo`, `api`, `recovery`, `glossary`, `storage`, `unipile`.

## Railway to Loki

### Grafana Cloud

1. Create a Loki data source in Grafana Cloud.
2. Get the Loki push URL and API key.
3. In Railway: Project → your service → Settings → Log Drains.
4. Add a log drain with:
   - Type: HTTP/Syslog (or use a Vector/Fluentd sidecar to forward to Loki HTTP push).

### Self-Hosted

1. Run Loki (Docker or Kubernetes).
2. Expose an HTTP endpoint for log ingestion.
3. Use Railway log drain, Vector, or Fluentd to forward stdout to Loki.
4. Configure Promtail (if using Docker) to scrape container logs and push to Loki.

**Example Loki label extraction (Promtail pipeline):**

```yaml
pipeline_stages:
  - json:
      expressions:
        output: log
        domain: domain
        phase: phase
        correlation_id: correlation_id
  - labels:
      domain:
      phase:
```

## Prometheus Scrape

Railway exposes a public URL. Add to Prometheus or Grafana Cloud Agent:

```yaml
scrape_configs:
  - job_name: vocify-backend
    static_configs:
      - targets: ['https://your-app.railway.app']
    scheme: https
    metrics_path: /metrics
    scrape_interval: 30s
```

## LogQL Examples

```logql
# All hubspot sync failures
{domain="hubspot"} | json | phase="sync_failed"

# Trace a request by correlation_id
{correlation_id="wh_abc12345"}

# LLM errors
{domain="llm"} | json | level="ERROR"

# Extraction pipeline
{domain="extraction"} | json

# Unipile webhook flow
{domain="webhook"} | json | phase=~"unipile.*"
```

## Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `vocify_transcription_duration_seconds` | Histogram | source (whatsapp, upload) | Transcription latency |
| `vocify_extraction_duration_seconds` | Histogram | - | LLM extraction latency |
| `vocify_sync_duration_seconds` | Histogram | result (success, failure) | HubSpot sync latency |
| `vocify_pipeline_errors_total` | Counter | domain, phase | Errors by domain/phase |
| `vocify_llm_requests_total` | Counter | status, model | LLM requests |
| `vocify_webhook_messages_total` | Counter | provider, outcome | Webhook messages (processed, skipped, error) |
| `vocify_unipile_api_calls_total` | Counter | operation, status | Unipile API calls |

## Grafana Dashboard Panels

- **Error rate by domain:** `sum(rate(vocify_pipeline_errors_total[5m])) by (domain)`
- **Transcription latency (p95):** `histogram_quantile(0.95, rate(vocify_transcription_duration_seconds_bucket[5m]))`
- **Extraction latency (p95):** `histogram_quantile(0.95, rate(vocify_extraction_duration_seconds_bucket[5m]))`
- **Sync latency (p95):** `histogram_quantile(0.95, rate(vocify_sync_duration_seconds_bucket[5m]))`
- **Webhook throughput:** `sum(rate(vocify_webhook_messages_total[5m])) by (provider, outcome)`
- **LLM success rate:** `sum(rate(vocify_llm_requests_total{status="success"}[5m])) / sum(rate(vocify_llm_requests_total[5m]))`

## Alerting (Optional)

- High error rate: `sum(rate(vocify_pipeline_errors_total[5m])) > 0.1`
- Sync failures: `increase(vocify_sync_duration_seconds_count{result="failure"}[1h]) > 5`
- LLM failures: `increase(vocify_llm_requests_total{status="failure"}[1h]) > 3`
