# Vocify Backend

FastAPI backend for voice memo processing and CRM integration.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy `.env` from project root or create one:
```bash
cp ../.env .env
```

3. Run development server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API Endpoints

- `GET /health` - Health check
- `POST /api/v1/memos/upload` - Upload audio and start processing
- `GET /api/v1/memos/{id}` - Get memo by ID
- `GET /api/v1/memos` - List user's memos

## Environment Variables

See `.env.example` for required variables.

## Railway Deployment

The backend is configured for Railway via `railway.json`. Deploy from the **backend** directory only.

### Setup

1. **Create a Railway service** and connect your GitHub repo.

2. **Set Root Directory** to `backend`:
   - Service → Settings → Build → Root Directory: `backend`
   - This is critical: the repo root has a Node frontend; Railway must build from `backend/` to detect Python.

3. **Add environment variables** (Settings → Variables):
   - `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
   - `DEEPGRAM_API_KEY`, `OPENROUTER_API_KEY`, `EXTRACTION_MODEL`
   - `HUBSPOT_CLIENT_ID`, `HUBSPOT_CLIENT_SECRET`, `JWT_SECRET`
   - `FRONTEND_URL` = your Vercel frontend URL (e.g. `https://your-app.vercel.app`)
   - `HUBSPOT_REDIRECT_URI` = `https://<your-railway-domain>/api/v1/crm/hubspot/callback`
   - `ENVIRONMENT` = `production`

4. **Generate domain** (Settings → Networking → Generate Domain).

5. **Update frontend** `VITE_API_URL` to your Railway URL: `https://your-service.up.railway.app/api/v1`

### HubSpot public app (OAuth)

For OAuth (public app) instead of Private App tokens, create the app in HubSpot 2025.2 and add the callback route. See `hubspot-app/README.md` for full setup.

### Build / Start (auto via railway.json)

- **Build**: Nixpacks detects Python, installs from `requirements.txt`
- **Start**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

