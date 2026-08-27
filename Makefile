# Vocify dev shortcuts
# Webhooks live on the same port as the API (8000):
#   Unipile:  https://<ngrok>/webhooks/unipile
#   HubSpot:  https://<ngrok>/webhooks/hubspot  (GET returns JSON with curl examples)

.PHONY: backend ngrok ngrok-static ngrok-url test test-js vendor-twilio

# Backend on port 8000
backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Backend test suite (characterization/golden-master tests). Mocks all HTTP
# (respx) and Supabase - no network, no real credentials needed beyond the
# SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY placeholders app.config validates on
# import (backend/.env). Install dev deps first:
#   pip install -r backend/requirements.txt -r backend/requirements-dev.txt
test:
	cd backend && python -m pytest

# JS/TS unit tests (extension + dashboard helpers + desktop companion libs)
test-js:
	cd chrome-extension && node --test lib/*.test.js
	node --experimental-strip-types --test src/lib/*.test.ts
	cd desktop && node --test lib/*.test.js

vendor-twilio:
	./scripts/vendor-twilio-sdk.sh 2.18.3

# Expose localhost:8000 via ngrok. Run `make backend` first in another terminal.
ngrok:
	ngrok http 8000

# Stable hostname (reserve under https://dashboard.ngrok.com/domains).
# Usage: NGROK_DOMAIN=your-name.ngrok-free.app make ngrok-static
ngrok-static:
	@test -n "$(NGROK_DOMAIN)" || (echo 'Set NGROK_DOMAIN, e.g. NGROK_DOMAIN=myapp.ngrok-free.app make ngrok-static' >&2; exit 1)
	ngrok http 8000 --domain=$(NGROK_DOMAIN)

# Print https webhook base URL (requires ngrok running with local API on 4040).
ngrok-url:
	@python3 -c "import json, sys, urllib.request;\
r=urllib.request.urlopen('http://127.0.0.1:4040/api/tunnels');\
d=json.load(r);\
t=[x for x in d.get('tunnels',[]) if str(x.get('public_url','')).startswith('https')];\
print((t[0]['public_url'] + '/webhooks/hubspot') if t else '', end='');\
sys.exit(0 if t else 1)" || (echo 'Start ngrok first (make ngrok), then retry.' >&2; exit 1)
