# WhatsApp via Signalcore (Forwarded Webhook)

Vocify uses a **business-verified Meta app** whose webhook is already configured to hit Signalcore. To use Vocify for voice-to-CRM, Signalcore forwards incoming webhooks to Vocify.

## Architecture

```
User → WhatsApp → Meta → Signalcore (https://api.signalcore.ai/api/v1/webhook/meta_whatsapp)
                            ↓ forward POST
                      Vocify (https://YOUR_VOCIFY_API/api/v1/webhooks/whatsapp)
                            ↓ process + reply via Graph API
                      Meta Graph API → User
```

- **Verification (GET)**: Handled by Signalcore. Vocify does NOT receive verification requests.
- **Messages (POST)**: Signalcore receives from Meta, forwards the same JSON body to Vocify.
- **Replies**: Vocify calls Meta Graph API directly (needs `WHATSAPP_ACCESS_TOKEN`).

## Signalcore Changes

When Signalcore receives a WhatsApp webhook POST from Meta:

1. Optionally process it (e.g. for Signalcore-specific flows).
2. Forward the **same raw body** to Vocify:

```
POST https://YOUR_VOCIFY_HOST/api/v1/webhooks/whatsapp
Content-Type: application/json
Body: <exact JSON from Meta>
```

Vocify expects the standard Meta webhook payload (`object`, `entry`, `changes`, `value`, `messages`, etc.).

## Vocify Config (.env)

| Variable | Value | Notes |
|----------|-------|-------|
| WHATSAPP_ACCESS_TOKEN | Permanent token | From Meta App 928991246529776 → WhatsApp → API Setup → Generate token |
| WHATSAPP_PHONE_NUMBER_ID | 958372230700988 | From API Setup |

**App Secret** (8785cb28a07bd0ba7e188e7c55053466) is used for OAuth flows, not for the Graph API. You need an **Access Token** in the dashboard.

## Getting a Permanent Token

1. Go to [Meta for Developers](https://developers.facebook.com/apps) → App **928991246529776**.
2. **WhatsApp** → **API Setup**.
3. Under "Temporary access token" → **Generate** or use **System User** for permanent token.
4. Copy the token into `WHATSAPP_ACCESS_TOKEN`.

## Vocify Webhook Behavior

- **GET** `/api/v1/webhooks/whatsapp`: Returns 400 (verification is done at Signalcore).
- **POST** `/api/v1/webhooks/whatsapp`: Processes the forwarded payload, sends replies via Graph API.

If Vocify receives a GET (e.g. during setup), it will fail verification. That's expected—Meta verifies against Signalcore's URL.
