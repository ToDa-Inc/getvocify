# Vocify Logs in Grafana (Loki)

The Vocify dashboard includes **Logs** panels (Errors & exceptions, Pipeline logs by domain, All logs). These require logs to be shipped to Grafana Cloud Loki.

## 1. Enable JSON logs

Set `LOG_JSON=true` in Railway (Variables). Redeploy. Logs will be emitted as one JSON object per line with fields: `level`, `logger`, `message`, `domain`, `phase`, `correlation_id`, etc.

## 2. Ship logs to Loki

You need a log drain that forwards Railway stdout to Grafana Cloud Loki. Options:

### Option A: Grafana Alloy (recommended)

Run Alloy as a separate Railway service that receives logs and pushes to Loki.

1. **Add a new service** in your Railway project: deploy Grafana Alloy.
   - Use the [Grafana Alloy Docker image](https://grafana.com/docs/alloy/latest/get-started/install-alloy/)
   - Or the [Railway Alloy template](https://railway.com/template) if available.

2. **Alloy config** — use `backend/grafana/alloy-logs.river` as a starting point. Replace `REMOTE_WRITE_URL`, `USER`, and `PASSWORD` with your Grafana Cloud Logs credentials (Stack → Logs → Send data → Alloy).

   Alloy exposes:
   - `POST /loki/api/v1/push` — Loki push API (if your drain sends this format)
   - `POST /loki/api/v1/raw` — Newline-delimited log lines (NDJSON)

   If Railway/Locomotive sends a different format, you may need a `loki.process` stage to transform it. See [Grafana Alloy logs tutorial](https://grafana.com/docs/grafana-cloud/send-data/alloy/tutorials/processing-logs).

3. **Railway Log Drain** — in Railway: Project → Vocify service → Settings → Log Drains. Add HTTP drain pointing to `https://your-alloy-service.railway.app/loki/api/v1/raw` (for NDJSON) or `/loki/api/v1/push`. Alloy listens on port 8080 by default; expose it in Railway.

4. **Grafana Cloud credentials** — from Grafana Cloud: Stack → Details → Logs → Send data → “Grafana Alloy” or “Loki API”. Copy the push URL, instance ID, and API key.

### Option B: Log drain adapter (custom)

A small service that receives Railway log drain HTTP POSTs, parses the payload, converts to Loki push format, and POSTs to Grafana Cloud Loki. Deploy as a separate Railway service.

- Input: Railway/Locomotive log drain format (JSON array of log objects).
- Output: Loki `/loki/api/v1/push` with `job="vocify-backend"`.

This requires a small codebase (e.g. FastAPI + httpx) that you host and maintain.

### Option C: Third-party (Logtail, Better Stack, etc.)

If you use a log aggregation service (Logtail, Better Stack, Axiom) that supports Railway log drains and can forward to Loki or export to Grafana, configure it to ship logs with a `job` label that you can use in the dashboard (e.g. `job="vocify-backend"`).

## 3. Configure dashboard datasources

On first load, the Vocify dashboard will prompt for:

- **datasource** — Prometheus (Grafana Cloud Prometheus)
- **datasource_loki** — Loki (Grafana Cloud Logs)
- **job** — `vocify-backend` (must match the label used when pushing to Loki)
- **domain** — filter by domain (extraction, llm, hubspot, etc.)

## 4. Verify

1. Trigger some backend activity (e.g. send a voice memo).
2. In Grafana: **Explore** → select Loki → run `{job="vocify-backend"}`.
3. If logs appear, the Logs panels on the Vocify dashboard will populate.
