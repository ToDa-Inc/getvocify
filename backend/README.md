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


