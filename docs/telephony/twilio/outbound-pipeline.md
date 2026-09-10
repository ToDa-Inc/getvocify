# Pipeline de llamadas outbound (Twilio)

Cómo se construyó el dialer de Vocify y cómo encajan **teléfono del prospecto**, **caller ID del comercial**, **outbound_calls**, grabación, screening y HubSpot.

El default de producción sigue siendo Twilio (`CALLING_PROVIDER=twilio`). Telnyx es un swap opcional del mismo flujo; no cambia el modelo de datos.

---

## 1. Qué problema resolvíamos

Antes, el audio de una llamada comercial llegaba (o no) vía Aircall / grabaciones de HubSpot. Vocify transcribía *después*, como consumidor.

El objetivo del dialer:

1. El comercial pulsa **Llamar** en la extensión (ficha HubSpot) o en el dialer flotante del dashboard.
2. La llamada sale con **su propio número verificado** como caller ID.
3. Vocify **graba, guarda y transcribe** el audio.
4. HubSpot recibe una activity de llamada y, si hay grabación, pide el WAV a Vocify.

Vocify es el dueño del audio. HubSpot es el consumidor.

---

## 2. Cómo se construyó (el proceso)

No se empezó por “conectar Twilio y listo”. El orden fue:

1. **Identidad del comercial, no un número alquilado.** Twilio Voice JS en el navegador. El `From` de la pierna WebRTC es `client:<user_id>`. El `From` PSTN (lo que ve el prospecto) lo decide el backend, nunca el cliente.
2. **Caller ID = número que el usuario verifica.** Twilio llama a ese móvil/fijo, el usuario teclea un código. Eso escribe `user_caller_ids`. Sin fila `verified` no hay botón de llamar útil.
3. **TwiML App como cerebro.** La extensión no marca PSTN. Pide un JWT, abre un Device, y Twilio pega a `POST /webhooks/twilio/voice`. Ahí se autoriza el caller ID y se devuelve `<Dial>`.
4. **Correlación por CallSid.** El webhook de voz crea `outbound_calls` con el CallSid de la pierna del navegador. Minutos después llega la grabación con el *mismo* CallSid. Ese es el hilo.
5. **Reutilizar el pipeline de memos.** WAV → Deepgram → sanitize → extracción LLM → review. `memos.source = vocify_call` para no mezclarlo con `hubspot_call`.
6. **Luego se afinó el outcome.** No todo lo contestado merece extracción. Dial status (busy / no-answer) y screening post-transcript (connected / voicemail / no_response). Todas las dispositions se loguean en HubSpot.

Decisiones de carrier, ley española de CLI y Telnyx están en [`../DECISION.md`](../DECISION.md). Este documento es solo el flujo que está en código.

---

## 3. Dos números distintos (no confundirlos)

| Número | Quién es | Dónde vive | Para qué |
|---|---|---|---|
| **Caller ID (`from_number`)** | El comercial | `user_caller_ids.phone_number` | Lo que ve el prospecto en la pantalla |
| **Destino (`to_number`)** | El contacto de HubSpot | `phone` / `mobilephone` del CRM, o lo que se teclea en el dialer | A quién se llama |

### Caller ID

- Settings → Caller ID. Twilio llama al número (en inglés) y pide un código.
- El callback `POST /webhooks/twilio/caller-id-status` marca `verified` o `failed` usando el `CallSid` de esa verificación, **nunca** el `To`. Matching por teléfono cruzaría tenants.
- `resolve_caller_id()` en el webhook de voz: el browser puede mandar una preferencia; el servidor solo acepta un número `verified` de ese `user_id`. Si no hay, cuelga.
- El cliente **no elige el From PSTN**. Si lo inventa, se rechaza.

### Teléfono del prospecto

- En la extensión: `GET /crm/hubspot/contacts|deals|companies/{id}/context` rellena `context.contactPhone`.
- El botón **“Llamar a X”** solo aparece si hay teléfono + calling `enabled` + al menos un caller ID verificado + no hay llamada en curso.
- Si HubSpot tiene `--` en el teléfono, `contactPhone` es `null` y el botón no existe. No es un bug del dialer.
- En el dashboard, el comercial busca el contacto o pega un E.164. `normalizeDialTarget` añade `+34` a nacionales ambiguos y rechaza basura.

---

## 4. Piezas en runtime

```
Comercial (extensión / dashboard)
        │  JWT (identity = user_id)
        ▼
Twilio Device (offscreen / browser)
        │  pierna WebRTC  From=client:<user_id>
        ▼
POST /webhooks/twilio/voice     ← TwiML App (manual en consola Twilio)
        │  resuelve caller ID
        │  inserta outbound_calls
        ▼
<Dial callerId=CLI record=record-from-answer-dual>
        │
        ├─ contestada ──► grabación dual WAV
        │                      │
        │                      ▼
        │              POST /webhooks/twilio/recording
        │                      │
        │                      ▼
        │              download → bucket privado → memo vocify_call
        │                      │
        │                      ▼
        │              STT → screening → (extract o no) → HubSpot activity
        │
        └─ busy / no-answer / failed / canceled
               POST /webhooks/twilio/dial-status
               log HubSpot, sin memo
```

Webhooks de Twilio (firma validada con `TWILIO_AUTH_TOKEN` + URL reconstruida desde `BACKEND_PUBLIC_URL`):

| Endpoint | Quién lo dispara | Qué hace |
|---|---|---|
| `/webhooks/twilio/voice` | TwiML App | Autoriza CLI, crea `outbound_calls`, devuelve `<Dial>` |
| `/webhooks/twilio/whisper` | `<Number url>` | Aviso de grabación solo al prospecto |
| `/webhooks/twilio/dial-status` | `action` de `<Dial>` | Missed-call → HubSpot. **Debe devolver TwiML** (`<Response/>`), no 204 |
| `/webhooks/twilio/recording` | Recording callback | Baja WAV, sube storage, lanza el pipeline |
| `/webhooks/twilio/caller-id-status` | Verificación de CLI | `user_caller_ids` → verified / failed |

La URL del TwiML App se configura **a mano** en la consola de Twilio. No la escribe el deploy. Si `BACKEND_PUBLIC_URL` no coincide con esa URL, Twilio recibe 403 y el comercial oye “application error”.

---

## 5. Tablas

### `user_caller_ids`

Un comercial, N números. Twilio prueba la titularidad; nosotros guardamos el resultado.

- `status`: `pending` → `verified` | `failed`
- `is_default`: el From si el cliente no pide uno concreto
- `twilio_validation_sid`: CallSid de la llamada de verificación

### `outbound_calls`

Una fila por intento, creada **al marcar**, no al colgar.

- Clave de correlación: CallSid de la pierna del navegador (`carrier_call_id` / históricamente `twilio_call_sid`)
- `from_number` / `to_number`
- IDs de HubSpot (contacto, deal, engagement)
- `recording_path` en el bucket privado `call-recordings`
- `memo_id` si hubo audio
- `status`: `dialing` → `recorded` → `logged` | `failed`
- `call_disposition`: resultado de negocio (abajo)

Un missed call **no** crea memo. Un contestado sí, aunque el screening omita la extracción LLM.

### `memos` (`source = vocify_call`)

Misma fila de review que un memo de voz. `screening_outcome` es la copia denormalizada (`connected` | `voicemail` | `no_response`) para badges en UI.

---

## 6. Después de colgar: dos caminos

### A. Nadie contestó (`DialCallStatus` ≠ `completed`)

`log_missed_call_activity`:

- Disposition: `busy` | `no_answer` | `failed` | `canceled`
- Activity en HubSpot (`hs_call_status` = `BUSY` / `NO_ANSWER` / …)
- Sin transcripción, sin memo
- Si no hay `hubspot_contact_id`, se intenta match por `to_number`

### B. Contestó (hay recording)

1. Download WAV (auth basic contra `api.twilio.com`). Si algún día la cuenta fuera IE1, el download reescribe el host a `api.{edge}.{region}.twilio.com`.
2. Upload al bucket privado.
3. Memo `transcribing`.
4. Deepgram + sanitize (formato real: `SPEAKER: S1\ntexto`).
5. `classify_call_outcome(transcript, duration)`:
   - 1 speaker o monólogo → `voicemail`
   - < 30s, o el segundo speaker casi no habla → `no_response`
   - conversación real de dos → `connected`
6. Solo `connected` corre extracción LLM. Los otros van a `pending_review` con un resumen fijo (“Buzón de voz…”) y badge en la lista.
7. `log_call_engagement` crea la call activity y avisa a HubSpot (`recordings/ready`). HubSpot pide el WAV a Vocify (signed URL + `Range` / 206).

Tiempos de `download`, `upload`, STT, `hubspot_log` y `total_pipeline` van a `memos.pipeline_meta` y a histogramas Prometheus.

---

## 7. Superficies de UI

| Superficie | Cómo marca |
|---|---|
| Extensión, ficha HubSpot | “Llamar a {nombre}” si hay `contactPhone` |
| Dashboard, dialer flotante | Busca contactos HubSpot o pega un número |
| Settings | Verificar / elegir caller ID default |

La extensión **no** es un teclado libre en la ficha. Sin teléfono en el CRM, no hay CTA.

---

## 8. Qué tiene que estar bien para que funcione

1. Env Twilio: `ACCOUNT_SID`, `AUTH_TOKEN`, `API_KEY_*`, `TWIML_APP_SID`. La cuenta que usamos es **US1**: deja `TWILIO_EDGE` y `TWILIO_REGION` vacíos. Solo rellénalos (`dublin` / `ie1`) si algún día la cuenta vive en Irlanda.
2. `BACKEND_PUBLIC_URL` = origen público que ve Twilio (p.ej. `https://api.getvocify.com`).
3. TwiML App → `POST {BACKEND_PUBLIC_URL}/webhooks/twilio/voice`.
4. Migraciones `025`–`027` aplicadas (`user_caller_ids`, `outbound_calls`, dispositions).
5. Caller ID `verified` para ese usuario.
6. Destino con teléfono E.164 (CRM o tecleado).
7. `HUBSPOT_APP_ID` si se quiere activity + playback en HubSpot.

---

## 9. Archivos (mapa corto)

| Capa | Dónde |
|---|---|
| Token + config + caller IDs | `backend/app/api/calls.py` |
| Webhooks Twilio | `backend/app/api/webhooks.py` |
| TwiML | `backend/app/services/telephony/twiml.py` |
| Autorización CLI | `backend/app/services/telephony/caller_id.py` |
| Download / memo / HubSpot | `backend/app/services/telephony/call_processor.py` |
| Screening | `backend/app/services/telephony/call_screening.py` |
| Activity HubSpot | `backend/app/services/hubspot/call_log.py` |
| Extensión: Device | `chrome-extension/offscreen.js` |
| Extensión: estado / start | `chrome-extension/background.js` |
| Extensión: CTA | `chrome-extension/lib/call-format.js` |
| Dashboard dialer | `src/components/dashboard/calling/` |
| Setup operativo | [`../../runbooks/twilio-setup.md`](../../runbooks/twilio-setup.md) |
| Plan original | [`../../superpowers/plans/2026-08-26-vocify-outbound-calling.md`](../../superpowers/plans/2026-08-26-vocify-outbound-calling.md) |
