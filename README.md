# Vocify

AI-powered sales conversation capture — record calls, transcribe, extract CRM updates, and sync to HubSpot or Salesforce.

## Repository layout

| Path | Purpose |
|------|---------|
| `src/` | React web app (Vite + TypeScript) |
| `backend/` | FastAPI API (deployed on Railway) |
| `chrome-extension/` | Browser extension for in-CRM recording |
| `hubspot-app/` | HubSpot OAuth app definition |
| `remotion/` | Product demo video (local render) |
| `docs/` | Product documentation |
| `scripts/` | Product ops scripts (HubSpot property setup) |

GTM data, cold-email pipeline, lead CSVs, pitch decks, and internal notes live in **[ToDa-Inc/vocify-workspace](https://github.com/ToDa-Inc/vocify-workspace)** (sibling repo).

## Local development

### Prerequisites

- Node.js 18+
- Python 3.11+
- `.env` at repo root (copy from `.env.example`)

### Quick start

```bash
# Install frontend deps
npm install

# Start both frontend and backend
npm run start
# Frontend: http://localhost:5173
# Backend:  http://localhost:8888

# Or run separately:
make backend          # API on :8000
npm run dev           # Frontend on :8080
```

### Backend only

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Deployment

| Service | Platform | Config |
|---------|----------|--------|
| Web app | Vercel | `vercel.json` — builds `src/` via `npm run build` |
| API | Railway | `backend/railway.json` |
| Chrome extension | Manual | Load `chrome-extension/` unpacked, or zip for store |
| HubSpot app | HubSpot CLI | `hubspot-app/` — `hs project upload` |

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Developer guide](docs/VOCIFY_DEVELOPER_GUIDE.md)
- [Product overview](docs/PRODUCT_OVERVIEW.md)
- [PRD](docs/PRD.md)
- [Backend README](backend/README.md)

## Environment

Copy `.env.example` to `.env` and fill in API keys for Speechmatics, OpenRouter, Supabase, and CRM integrations. The `start.js` script syncs root `.env` to `backend/.env` automatically.
