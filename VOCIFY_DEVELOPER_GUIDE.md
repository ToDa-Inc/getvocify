# Explicación del funcionamiento completo de Vocify

Guía para nuevos desarrolladores que se unen al equipo.

---

## 1. ARQUITECTURA GENERAL

### Stack tecnológico

| Capa | Tecnología |
|------|------------|
| **Frontend** | React 18, TypeScript, Vite 5, Tailwind CSS, shadcn/ui, TanStack Query |
| **Backend** | Python 3.9+, FastAPI, Uvicorn |
| **Base de datos** | Supabase (PostgreSQL) con Row Level Security |
| **Storage** | Supabase Storage (bucket `voice-memos`) |
| **Auth** | Supabase Auth (JWT) |

### APIs externas

| Servicio | Uso | Config |
|----------|-----|--------|
| **Deepgram** | Transcripción de audio (modelo Nova-2) | `DEEPGRAM_API_KEY` |
| **Speechmatics** | Transcripción en tiempo real (WebSocket) | `SPEECHMATICS_API_KEY` |
| **OpenRouter** | LLM para extracción (modelo configurable) | `OPENROUTER_API_KEY`, `EXTRACTION_MODEL` (default: `x-ai/grok-4.1-fast`) |
| **HubSpot** | CRM: deals, contacts, companies | OAuth / Private App token |

### Estructura de directorios

```
getvocify/
├── backend/                    # API FastAPI
│   ├── app/
│   │   ├── api/               # Routers (memos, crm, transcription, auth, glossary)
│   │   ├── models/            # Pydantic models
│   │   ├── services/          # Lógica de negocio
│   │   │   ├── hubspot/       # Cliente HubSpot, sync, preview, deals, etc.
│   │   │   ├── extraction.py  # LLM extraction
│   │   │   ├── transcription.py
│   │   │   └── ...
│   │   ├── config.py
│   │   ├── deps.py
│   │   └── main.py
│   ├── migrations/
│   └── requirements.txt
├── src/                        # Frontend React
│   ├── components/
│   ├── features/
│   │   ├── memos/             # API memos, hooks, types
│   │   ├── recording/         # useMediaRecorder, useAudioUpload
│   │   └── auth/
│   ├── lib/
│   ├── pages/
│   └── shared/
├── package.json
└── start.js                    # Arranca backend + frontend
```

---

## 2. FLUJO COMPLETO DEL USUARIO (End-to-End)

### Paso 1: Usuario graba audio

**Qué hace el usuario:** Graba con el micrófono o sube un archivo de audio.

**Archivos frontend:**
- `src/pages/dashboard/RecordPage.tsx` – Página de grabación
- `src/features/recording/hooks/useMediaRecorder.ts` – MediaRecorder API
- `src/features/recording/hooks/useAudioUpload.ts` – Subida
- `src/features/memos/api.ts` – `uploadWithProgress()`

**Endpoint llamado:** `POST /api/v1/memos/upload`

**Datos enviados:**
- `FormData`: `audio` (Blob/File), opcionalmente `transcript` (string si hay transcripción en tiempo real)

**Backend:** `backend/app/api/memos.py` → `upload_memo()`
1. Valida tipo y tamaño (máx 10MB)
2. Sube audio a Supabase Storage (`StorageService.upload_audio`)
3. Obtiene config del usuario (`allowed_deal_fields`)
4. Obtiene `field_specs` vía `HubSpotSchemaService.get_curated_field_specs("deals", allowed_fields)`
5. Crea registro en `memos` con `status: "uploading"` o `"extracting"` (si hay transcript)
6. Lanza tarea en background: `process_memo_async` o `extract_memo_async`

**Qué se guarda en DB:**
- Tabla `memos`: `id`, `user_id`, `audio_url`, `audio_duration`, `status`, `transcript` (si existe)
- Storage: archivo en `voice-memos/{user_id}/{uuid}.webm`

---

### Paso 2: Transcripción del audio

**Servicio:** Deepgram Nova-2 (no Whisper ni Google Speech-to-Text).

**Archivo:** `backend/app/services/transcription.py` → `TranscriptionService.transcribe()`

**Flujo:**
1. `process_memo_async` descarga el audio de Storage
2. Llama a `transcription_service.transcribe(audio_bytes)`
3. Deepgram devuelve `transcript`, `confidence`, `duration`
4. Actualiza `memos`: `transcript`, `transcript_confidence`, `status: "extracting"`

**Dónde se guarda:** Columna `memos.transcript` (TEXT).

---

### Paso 3: Extracción de campos con LLM

**LLM:** OpenRouter (modelo configurable, por defecto `x-ai/grok-4.1-fast`).

**Archivo:** `backend/app/services/extraction.py` → `ExtractionService.extract()`

**Construcción del prompt (`_build_prompt`):**
1. Si hay `field_specs`: se añade sección "### CRM FIELDS TO EXTRACT" con nombre, label, tipo, opciones (enums)
2. Siempre: `summary`, `painPoints`, `nextSteps`, `competitors`, `objections`, `decisionMakers`
3. Glosario del usuario (si existe) para corrección fonética
4. Reglas: extracción conservadora, mapeo de enums, formato JSON

**Origen de `allowed_deal_fields`:**
- Tabla `crm_configurations` (por `connection_id` del usuario)
- `CRMConfigurationService.get_configuration(user_id)` → `config.allowed_deal_fields`
- Se pasa a `get_curated_field_specs("deals", allowed_fields)` para obtener metadata de HubSpot

**Respuesta del LLM:** JSON con los campos de `field_specs` + campos estándar + `confidence`.

**Mapeo a MemoExtraction:**
- `dealname` → `companyName`
- `amount` → `dealAmount`
- `closedate` → `closeDate`
- `summary` → `summary`
- Todo el JSON original → `raw_extraction`

**Dónde se guarda:** `memos.extraction` (JSONB). Incluye `raw_extraction` con la respuesta completa del LLM.

---

### Paso 4: Preview (cambios propuestos)

**Endpoint:** `GET /api/v1/memos/{memo_id}/preview?deal_id=...`

**Archivo:** `backend/app/api/memos.py` → `get_approval_preview()`, `backend/app/services/hubspot/preview.py` → `HubSpotPreviewService.build_preview()`

**Datos que lee de DB:**
- `memos`: `extraction`, `transcript`
- `crm_connections`: `access_token`
- `crm_configurations`: `allowed_deal_fields`, `default_pipeline_id`

**Generación de `proposed_updates`:**
1. Llama a `deal_service.map_extraction_to_properties(extraction)` (misma lógica que sync)
2. Filtra por `allowed_fields`
3. Obtiene labels con `schema_service.get_curated_field_specs("deals", ...)`
4. Para cada campo con valor: crea `ProposedUpdate` con `field_name`, `field_label`, `current_value`, `new_value`, `extraction_confidence`
5. Si `deal_id` existe: compara con deal actual en HubSpot

**Uso de `map_extraction_to_properties`:** Sí. Está en `backend/app/services/hubspot/deals.py` → `HubSpotDealService.map_extraction_to_properties()`.

---

### Paso 5: Sync a HubSpot

**Endpoint:** `POST /api/v1/memos/{memo_id}/approve`

**Archivo:** `backend/app/api/memos.py` → `approve_memo()`, `backend/app/services/hubspot/sync.py` → `HubSpotSyncService.sync_memo()`

**Conexión con HubSpot:** `HubSpotClient(access_token)` desde `crm_connections.access_token`.

**Datos enviados:**
1. `map_extraction_to_properties_with_stage(extraction)` → propiedades del deal
2. `_filter_properties(properties, allowed_fields)` → solo campos permitidos
3. Creación/actualización de company, contact, deal y asociaciones

**Manejo de errores:**
- Registros en `crm_updates` (pending → success/failed)
- Reutiliza company/contact en reintentos para evitar duplicados
- `SyncResult` con `success`, `error`, IDs creados

---

## 3. MODELOS DE DATOS

### Tabla: memos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | UUID | PK |
| user_id | UUID | FK auth.users |
| status | TEXT | uploading, transcribing, extracting, pending_review, approved, rejected, failed |
| audio_url | TEXT | URL en Supabase Storage |
| audio_duration | REAL | Segundos |
| transcript | TEXT | Texto transcrito |
| transcript_confidence | REAL | 0-1 |
| extraction | JSONB | MemoExtraction serializado |
| matched_deal_id | TEXT | Deal de HubSpot seleccionado |
| matched_deal_name | TEXT | Nombre del deal |
| is_new_deal | BOOLEAN | true = crear nuevo |
| error_message | TEXT | Si falla |
| created_at, processed_at, approved_at | TIMESTAMPTZ | |
| processing_started_at | TIMESTAMPTZ | Para recovery de memos atascados |

**Relaciones:** `user_id` → auth.users.

**Ejemplo:**
```json
{
  "id": "b38c19ac-cab7-4b40-9665-e300bff6e001",
  "user_id": "025bba1b-7d9b-49c2-85b9-fd595b345a25",
  "status": "pending_review",
  "extraction": {
    "companyName": "Cobee",
    "dealAmount": 100000,
    "summary": "...",
    "raw_extraction": { "dealname": "Cobee", "amount": 100000, "description": "...", ... }
  }
}
```

### Tabla: extraction (dentro de memos.extraction)

No hay tabla `memo_extractions`. La extracción vive en `memos.extraction` (JSONB).

**`raw_extraction`:** Objeto con la respuesta completa del LLM (todos los campos solicitados + confidence). Es la fuente de verdad para campos dinámicos (p.ej. `price_per_fte_eur`, `ftes_fulltime_employees`).

**Ejemplo de raw_extraction:**
```json
{
  "dealname": "Cobee",
  "amount": 100000,
  "description": "Deal con Cobee, 500 empleados...",
  "price_per_fte_eur": 3,
  "ftes_fulltime_employees": 500,
  "competitors": [],
  "summary": "...",
  "confidence": { "overall": 0.8, "fields": { "amount": 0.9, "description": 0.85 } }
}
```

### Tabla: crm_configurations

| Campo | Descripción |
|-------|-------------|
| connection_id | FK crm_connections |
| user_id | FK auth.users |
| default_pipeline_id, default_stage_id | Pipeline y etapa por defecto |
| allowed_deal_fields | TEXT[] – campos que el usuario permite actualizar |
| allowed_contact_fields, allowed_company_fields | Idem para contact y company |
| auto_create_contacts, auto_create_companies | Boolean |

**`allowed_deal_fields`:** Lista de propiedades de HubSpot que el usuario quiere que el LLM extraiga y que se puedan actualizar (p.ej. `["dealname","amount","description","closedate","price_per_fte_eur","competitors"]`).

**Configuración:** En la UI, `src/components/dashboard/hubspot/HubSpotConfiguration.tsx`, que llama a `POST /api/v1/crm/hubspot/configure`.

### Otras tablas

- **crm_connections:** Tokens OAuth de HubSpot
- **crm_schemas:** Cache de propiedades y pipelines de HubSpot
- **crm_updates:** Registro de cada operación CRM (create_deal, update_deal, etc.)
- **user_profiles:** Perfil extendido del usuario

---

## 4. SERVICIOS CLAVE

### HubSpotPreviewService

**Ubicación:** `backend/app/services/hubspot/preview.py`

**Métodos principales:** `build_preview()`

**Generación de `proposed_updates`:** En `build_preview()`:
1. `map_extraction_to_properties(extraction)`
2. Filtra por `allowed_fields`
3. Obtiene labels con `get_curated_field_specs`
4. Construye `ProposedUpdate` por cada campo con valor

**Uso de config:** Recibe `allowed_fields` del endpoint (desde `crm_configurations.allowed_deal_fields`).

### HubSpotSyncService

**Ubicación:** `backend/app/services/hubspot/sync.py`

**Métodos principales:** `sync_memo()`, `_filter_properties()`

**Filtrado de campos:** `_filter_properties(properties, allowed_fields)` devuelve solo las claves que están en `allowed_fields`.

### ExtractionService

**Ubicación:** `backend/app/services/extraction.py`

**Llamada al LLM:** `httpx.post(OPENROUTER_API_URL, json={...})` con `model`, `messages`, `temperature: 0`, `response_format: { type: "json_object" }`.

**`get_curated_field_specs`:** En `backend/app/services/hubspot/schema.py` → `HubSpotSchemaService.get_curated_field_specs(object_type, field_names)`. Devuelve `{ name, label, type, description, options }` para cada campo que exista en el schema de HubSpot.

### map_extraction_to_properties

**Archivo:** `backend/app/services/hubspot/deals.py` → `HubSpotDealService.map_extraction_to_properties()`

**Función:**
1. Campos legacy: `dealname`, `amount`, `closedate`, `description` desde MemoExtraction
2. Campos dinámicos: itera `extraction.raw_extraction`, excluyendo `skip_fields` (summary, painPoints, etc.)
3. Convierte fechas a timestamp de HubSpot, números a string
4. Devuelve `dict[str, Any]` con propiedades listas para la API de HubSpot

**Uso de raw_extraction:** Todos los campos del LLM que no están en `skip_fields` se añaden a `properties`.

**Ejemplo:**
- Input: `MemoExtraction(companyName="Cobee", dealAmount=100000, raw_extraction={"price_per_fte_eur": 3, "ftes_fulltime_employees": 500, ...})`
- Output: `{"dealname": "Cobee Deal", "amount": "100000", "description": "...", "price_per_fte_eur": 3, "ftes_fulltime_employees": 500}`

---

## 5. CONFIGURACIÓN DEL USUARIO

**Dónde se configura `allowed_deal_fields`:** Settings → HubSpot Configuration (`src/components/dashboard/hubspot/HubSpotConfiguration.tsx`).

**Persistencia:** Tabla `crm_configurations` en Supabase.

**Propagación:**
1. Upload: `get_configuration(user_id)` → `field_specs` → extraction
2. Preview: `get_configuration(user_id)` → `allowed_fields` → `build_preview()`
3. Approve: `get_configuration(user_id)` → `allowed_fields` → `sync_memo()`
4. Re-extract: `get_configuration(user_id)` → `field_specs` → extraction

---

## 6. EJEMPLO CONCRETO

**Transcript:** "Acabo de hablar con Tony de Cobee. Son 500 empleados. Deal de 100k."

### 1. Envío al LLM

Prompt con `field_specs` (p.ej. dealname, amount, description, closedate, price_per_fte_eur, ftes_fulltime_employees) + transcript + reglas de extracción.

### 2. Respuesta del LLM (raw_extraction)

```json
{
  "dealname": "Cobee",
  "amount": 100000,
  "description": "Acabo de hablar con Tony de Cobee. Son 500 empleados. Deal de 100k.",
  "closedate": null,
  "price_per_fte_eur": null,
  "ftes_fulltime_employees": 500,
  "summary": "Llamada con Tony de Cobee. 500 empleados. Deal valorado en 100k.",
  "competitors": [],
  "confidence": { "overall": 0.85, "fields": { "amount": 0.9, "dealname": 0.95 } }
}
```

### 3. map_extraction_to_properties

```python
{
  "dealname": "Cobee Deal",
  "amount": "100000",
  "description": "Acabo de hablar con Tony de Cobee...",
  "ftes_fulltime_employees": 500
}
```

### 4. Preview (con allowed_fields = [dealname, amount, description, ftes_fulltime_employees])

```json
{
  "proposed_updates": [
    { "field_name": "dealname", "field_label": "Deal Name", "new_value": "Cobee Deal", "current_value": null },
    { "field_name": "amount", "field_label": "Amount", "new_value": "100000", "current_value": null },
    { "field_name": "description", "field_label": "Description", "new_value": "...", "current_value": null },
    { "field_name": "ftes_fulltime_employees", "field_label": "FTEs", "new_value": "500", "current_value": null }
  ]
}
```

### 5. Envío a HubSpot

`POST /crm/v3/objects/deals` con las propiedades filtradas por `allowed_fields`.

---

## 7. PROBLEMA ACTUAL (Preview vs Config)

**Situación:** Config con 10 campos en `allowed_deal_fields`, preview mostrando solo 2 (amount, description).

**Causas posibles:**
1. Memo procesado antes de que la config tuviera esos 10 campos → `field_specs` antiguos, el LLM no extrajo el resto.
2. `raw_extraction` no contiene esos campos → el LLM no los devolvió.
3. El preview (antes del fix) solo contemplaba 4 campos hardcodeados.

**Archivos a revisar:**
1. `backend/app/services/hubspot/preview.py` – ahora usa `map_extraction_to_properties` + `allowed_fields`.
2. `backend/app/services/extraction.py` – mapeo y `raw_extraction`.
3. `backend/app/services/hubspot/deals.py` – `map_extraction_to_properties` y `skip_fields`.

**Comprobar si `raw_extraction` tiene los 10 campos:**
```sql
SELECT extraction->'raw_extraction' FROM memos WHERE id = 'b38c19ac-cab7-4b40-9665-e300bff6e001';
```

**Reprocesar un memo con la nueva lógica:**
```
POST /api/v1/memos/{memo_id}/re-extract
```
- Requiere `status != 'approved'`
- Usa la config actual para `field_specs`
- Re-ejecuta la extracción y actualiza `memos.extraction`

---

## 8. PUNTOS DE DEBUGGING

### Extracción

- `backend/app/services/extraction.py` línea ~136: `prompt = self._build_prompt(...)` – log del prompt.
- Línea ~174: `extracted = json.loads(content)` – log del JSON del LLM.
- Línea ~201: `raw_extraction=extracted` – verificar que se guarda completo.

### Preview

- `backend/app/services/hubspot/preview.py` línea ~70: `properties = self.deals.map_extraction_to_properties(extraction)` – log de propiedades.
- Línea ~73: `filtered_properties = {...}` – log tras filtrar por `allowed_fields`.

### Queries útiles

```sql
-- Memo con extraction
SELECT id, status, extraction->'raw_extraction' as raw, extraction->'confidence' as conf 
FROM memos WHERE id = 'xxx';

-- Config del usuario
SELECT allowed_deal_fields FROM crm_configurations 
WHERE connection_id IN (SELECT id FROM crm_connections WHERE user_id = 'xxx');
```

---

*Documento generado para onboarding de desarrolladores. Última actualización: Feb 2025.*
