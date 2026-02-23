# Vocify dev shortcuts
# For Unipile webhook testing: run `make backend` in one terminal, `make ngrok` in another.
# Use the ngrok URL + /webhooks/unipile as your Unipile/n8n webhook target.

.PHONY: backend ngrok

# Backend on port 8000
backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Expose localhost:8000 via ngrok. Run `make backend` first in another terminal.
ngrok:
	ngrok http 8000
