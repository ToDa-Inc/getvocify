# Grafana Cloud Setup for Vocify

Step-by-step guide to get metrics and dashboards working with Grafana Cloud (Metrics Endpoint integration).

## Prerequisites

- Grafana Cloud account (free tier works)
- Vocify backend deployed (e.g. Railway) with `/metrics` exposed

## 1. Enable Metrics Auth (required by Grafana Cloud)

Grafana Cloud Metrics Endpoint **requires** authentication. Your endpoint must accept Bearer or Basic auth.

### 1.1 Generate a token

```bash
openssl rand -hex 32
```

Use this as `METRICS_TOKEN`.

### 1.2 Set in Railway

1. Project → Vocify service → Variables
2. Add: `METRICS_TOKEN` = `<your-generated-token>`
3. Redeploy

### 1.3 Verify locally

```bash
# Without token (should 401 when METRICS_TOKEN is set)
curl -s -o /dev/null -w "%{http_code}" https://api.getvocify.com/metrics
# → 401

# With token
curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer YOUR_TOKEN" https://api.getvocify.com/metrics
# → 200
```

## 2. Configure Grafana Cloud Metrics Endpoint

1. In Grafana Cloud: **Connections** (left menu) → **Add new connection**
2. Search for **Metrics Endpoint** → Open
3. **Create scrape job**:
   - **Scrape job name**: `vocify-production` (alphanumeric, dashes, underscores)
   - **Public URL**: `https://api.getvocify.com/metrics`
   - **Authentication**: Bearer Token
   - **Token**: Paste your `METRICS_TOKEN` (no "Bearer " prefix — Grafana adds it)
   - **Scrape interval**: 1 minute (default)
4. **Test the connection** — should succeed
5. **Save**

## 3. Import Vocify Dashboard

1. **Dashboards** (left menu) → **New** → **Import**
2. Upload `backend/grafana/vocify-dashboard.json` or paste its contents
3. Select your Prometheus data source (Grafana Cloud Metrics)
4. **Import**

## 4. What You Get

### Metrics Endpoint Overview (built-in)

Meta-dashboard for scrape health (samples received, scrape latency). Use this to confirm data is flowing.

### Vocify Backend (custom)

- **Row 1 — Pipeline health**: LLM requests/min, webhook throughput, pipeline errors
- **Row 2 — Latency**: Extraction p95, transcription p95, HubSpot sync p95
- **Row 3 — Errors**: Errors by domain, LLM failures
- **Row 4 — HTTP**: Request rate, 4xx/5xx, latency

## 5. Troubleshooting

### "No data" in dashboard

1. Check **Metrics Endpoint Overview** → "Samples Received". If 0, scrape is failing.
2. Verify `METRICS_TOKEN` matches in Railway and Grafana (Bearer, no prefix).
3. Ensure IP allowlist: [Grafana Cloud allowlist](https://grafana.com/docs/grafana-cloud/account-management/allow-list/#hosted-grafana).

### 401 on scrape

- Token mismatch. Regenerate in Railway, update Grafana scrape job, redeploy.

### Vocify metrics zero but HTTP metrics show

- Vocify metrics (`vocify_*`) only increase when your pipeline runs (transcription, extraction, webhooks). Generate traffic (send a voice memo) to populate.

## 6. Logs (Loki) — Optional Next Step

For searchable logs (not just metrics), see [OBSERVABILITY.md](./OBSERVABILITY.md) — Railway log drain to Loki.
