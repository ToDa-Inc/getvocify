# Vercel

Hosts `app.getvocify.com` (Vite frontend). API outages look like a broken
dashboard but `/health` on `api.getvocify.com` is the truth.

`VITE_API_URL` is baked at build time. A 200 HTML page + failed XHR is Railway,
not Vercel. Check Vercel only for frontend deploy/build errors.
