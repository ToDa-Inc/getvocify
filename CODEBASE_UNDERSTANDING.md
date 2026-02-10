# Vocify Codebase Deep Understanding

> **Generated:** Comprehensive analysis of the Vocify codebase architecture, integrations, routes, features, and processes.

---

## Table of Contents

1. [Product Overview](#product-overview)
2. [Architecture Summary](#architecture-summary)
3. [Backend Routes & API](#backend-routes--api)
4. [Integrations](#integrations)
5. [Data Models & Database](#data-models--database)
6. [Frontend Structure](#frontend-structure)
7. [Processing Pipeline](#processing-pipeline)
8. [Key Features](#key-features)
9. [Technology Stack](#technology-stack)

---

## Product Overview

**Vocify** is a voice-to-CRM SaaS that converts voice memos into structured CRM updates in 60 seconds. The target is sales reps who spend 5+ hours/week on manual CRM data entry.

**Core Flow:**
1. User records 30-120 second voice memo
2. System transcribes audio → text (Deepgram)
3. System extracts structured CRM data (GPT-5-mini)
4. User reviews and approves extraction
5. System syncs to HubSpot CRM (deals, contacts, companies)

---

## Architecture Summary

### Backend (Python FastAPI)
- **Framework:** FastAPI (async)
- **Database:** Supabase (PostgreSQL) with Row Level Security
- **Storage:** Supabase Storage (voice-memos bucket)
- **Authentication:** Supabase Auth (JWT tokens)

### Frontend (React + TypeScript)
- **Framework:** React 18 + Vite
- **Routing:** React Router 6
- **State:** TanStack Query (server state) + React Context (auth)
- **UI:** shadcn/ui + Tailwind CSS
- **Language:** TypeScript (strict mode)

### Architecture Principles
- **Feature-based organization** (features/memos, features/integrations, etc.)
- **YAGNI** (You Aren't Gonna Need It)
- **Type safety** (TypeScript + Pydantic)
- **Explicit over implicit**
- **Composition over inheritance**

---

## Backend Routes & API

### Base URL: `/api/v1`

#### Authentication (`/api/v1/auth`)
- `POST /signup` - Create new user account
- `POST /login` - Authenticate user
- `GET /me` - Get current user profile

#### Voice Memos (`/api/v1/memos`)
- `POST /upload` - Upload audio file, start processing pipeline
  - Supports optional `transcript` parameter (skip Deepgram if provided)
  - Returns memo ID and status URL for polling
- `GET /{memo_id}` - Get single memo by ID
- `GET ""` - List user's memos (paginated)
- `POST /{memo_id}/approve` - Approve memo and sync to CRM
  - Accepts optional `ApproveMemoRequest` with edited extraction
  - Syncs to HubSpot if connection exists
- `GET /{memo_id}/crm-updates` - Get all CRM updates for a memo
- `POST /{memo_id}/match` - Find matching HubSpot deals
- `GET /{memo_id}/preview` - Get approval preview (what will be updated)

#### CRM Integration (`/api/v1/crm`)
- `POST /hubspot/connect` - Connect HubSpot Private App (stores access token)
- `POST /hubspot/test` - Test HubSpot connection validity
- `GET /hubspot/connection` - Get user's HubSpot connection details
- `DELETE /hubspot/disconnect` - Disconnect HubSpot
- `GET /hubspot/schema` - Get deal schema (properties + pipelines) [cached]
- `GET /hubspot/pipelines` - Get all pipelines for onboarding
- `GET /hubspot/search/deals` - Search deals by name
- `GET /hubspot/configuration` - Get user's CRM configuration
- `POST /hubspot/configure` - Save CRM configuration (pipeline, stage, allowed fields)
- `PUT /hubspot/configure` - Update CRM configuration
- `GET /connections` - List all CRM connections for user
- `POST /hubspot/deals` - Create test deal (for testing)
- `PATCH /hubspot/deals/{deal_id}` - Update test deal

#### Transcription (`/api/v1/transcription`)
- `WebSocket /live` - Real-time transcription WebSocket
  - Dual streaming: Deepgram + Speechmatics
  - Supports language parameter (`?language=multi` or `es`)
  - Proxies audio stream to both providers simultaneously

#### Health (`/health`)
- `GET /health` - Health check endpoint

---

## Integrations

### Currently Implemented

#### HubSpot CRM (MVP - Fully Implemented)
**Connection Method:** Private App Access Token (not OAuth)
- User provides Private App access token
- Token is validated against HubSpot API
- Token stored in `crm_connections` table

**Services:**
- `HubSpotClient` - HTTP client wrapper
- `HubSpotValidationService` - Token validation
- `HubSpotSchemaService` - Schema discovery & caching
- `HubSpotSearchService` - Search API wrapper
- `HubSpotContactService` - Contact CRUD operations
- `HubSpotCompanyService` - Company CRUD operations
- `HubSpotDealService` - Deal CRUD operations
- `HubSpotAssociationService` - Object associations
- `HubSpotMatchingService` - Intelligent deal matching
- `HubSpotPreviewService` - Preview what will be updated
- `HubSpotSyncService` - Orchestration service (syncs memo → HubSpot)

**Sync Flow:**
1. Find or create company (if `companyName` exists)
2. Find or create contact (if `contactEmail` or `contactName` exists)
3. Associate contact → company
4. Create or update deal (always)
5. Associate deal → contact, deal → company
6. Track each step in `crm_updates` table

**Configuration:**
- Users configure default pipeline & stage
- Field whitelisting (allowed_deal_fields, allowed_contact_fields, allowed_company_fields)
- Auto-create contacts/companies settings

**Schema Caching:**
- Deal properties and pipelines cached in `crm_schemas` table
- Reduces API calls
- Refreshed on configuration save

### Planned (Not Implemented)
- Salesforce (planned for V2)
- Pipedrive (planned for V3)

---

## Data Models & Database

### Core Tables

#### `user_profiles`
- Extends Supabase `auth.users`
- Fields: `id` (FK to auth.users), `full_name`, `company_name`, `avatar_url`
- RLS: Users can only access their own profile

#### `crm_connections`
- Stores CRM OAuth tokens and metadata
- Fields: `id`, `user_id`, `provider` (hubspot/salesforce/pipedrive), `status`, `access_token`, `refresh_token`, `token_expires_at`, `metadata` (JSONB)
- Unique constraint: `(user_id, provider)`
- RLS: Users can only manage their own connections

#### `crm_configurations`
- User's CRM preferences (pipeline, stage, field whitelisting)
- Fields: `id`, `connection_id`, `user_id`, `default_pipeline_id`, `default_pipeline_name`, `default_stage_id`, `default_stage_name`, `allowed_deal_fields[]`, `allowed_contact_fields[]`, `allowed_company_fields[]`, `auto_create_contacts`, `auto_create_companies`
- Unique constraint: `(connection_id)`
- RLS: Users can only manage their own configurations

#### `crm_schemas`
- Cached CRM schemas (properties, pipelines)
- Fields: `id`, `connection_id`, `object_type` (deals/contacts/companies), `properties` (JSONB), `pipelines` (JSONB), `fetched_at`
- Unique constraint: `(connection_id, object_type)`
- RLS: Users can only view schemas for their connections

#### `memos`
- Core voice memo entity
- Fields:
  - `id`, `user_id`, `status` (uploading/transcribing/extracting/pending_review/approved/rejected/failed)
  - `audio_url`, `audio_duration`
  - `transcript`, `transcript_confidence`
  - `extraction` (JSONB - MemoExtraction)
  - `matched_deal_id`, `matched_deal_name`, `is_new_deal` (for deal matching)
  - `error_message`
  - `created_at`, `processed_at`, `approved_at`
- Indexes: `(user_id, status)`, `(user_id, created_at DESC)`
- RLS: Users can only manage their own memos

#### `crm_updates` (Referenced in code, schema needs verification)
- Audit trail of CRM operations
- Tracks each create/update/associate operation
- Fields: `id`, `memo_id`, `user_id`, `crm_connection_id`, `action_type`, `resource_type`, `resource_id`, `data` (JSONB), `status`, `response` (JSONB), `error_message`, `retry_count`, `created_at`, `completed_at`

### Data Flow

**Memo Lifecycle:**
1. `uploading` → Audio uploaded to storage
2. `transcribing` → Deepgram processing
3. `extracting` → LLM extracting structured data
4. `pending_review` → Waiting for user approval
5. `approved` → User approved, CRM synced
6. `rejected` → User rejected
7. `failed` → Processing error

**MemoExtraction Model:**
```typescript
{
  // Deal Information
  companyName?: string
  dealAmount?: number
  dealCurrency: string (default: "EUR")
  dealStage?: string
  closeDate?: string (ISO YYYY-MM-DD)
  
  // Contact Information
  contactName?: string
  contactRole?: string
  contactEmail?: string
  contactPhone?: string
  
  // Meeting Intelligence
  summary: string
  painPoints: string[]
  nextSteps: string[]
  competitors: string[]
  objections: string[]
  decisionMakers: string[]
  
  // Confidence
  confidence: { overall: number, fields: Record<string, number> }
  
  // Raw extraction (for dynamic fields)
  raw_extraction?: dict
}
```

---

## Frontend Structure

### Routes (`src/pages/`)
- `/` - Landing page (Index.tsx)
- `/es` - Landing page (Spanish)
- `/login` - Login page
- `/signup` - Signup page
- `/dashboard` - Dashboard layout (protected)
  - `/dashboard` - Dashboard home (DashboardHome.tsx)
  - `/dashboard/record` - Record voice memo (RecordPage.tsx)
  - `/dashboard/memos` - Memos list (MemosPage.tsx)
  - `/dashboard/memos/:id` - Memo detail & approval (MemoDetail.tsx)
  - `/dashboard/integrations` - CRM connections (IntegrationsPage.tsx)
  - `/dashboard/settings` - User settings (SettingsPage.tsx)
  - `/dashboard/usage` - Usage analytics (UsagePage.tsx)

### Features (`src/features/`)
- `auth/` - Authentication (signup, login, context, API)
- `memos/` - Memos management (list, detail, hooks, API)
- `recording/` - Voice recording (components, hooks, real-time transcription)
- `integrations/` - CRM integrations (API, hooks, types)

### Components (`src/components/`)
- `dashboard/` - Dashboard layout & navigation
- `landing/` - Landing page sections (Hero, Features, Pricing, etc.)
- `ui/` - shadcn/ui component library

### Shared (`src/shared/`)
- `lib/` - Utilities, API client, constants
- `types/` - Common TypeScript types
- `components/` - Shared UI components

---

## Processing Pipeline

### 1. Audio Upload (`POST /api/v1/memos/upload`)
- Validates audio file (type, size ≤10MB)
- Uploads to Supabase Storage (`voice-memos` bucket)
- Creates memo record with status `uploading`
- Starts background processing task

### 2. Transcription (Background Task)
- Status → `transcribing`
- Downloads audio from storage
- Calls Deepgram API (Nova-3 model)
- Updates memo: `transcript`, `transcript_confidence`, status → `extracting`

### 3. Extraction (Background Task)
- Calls OpenRouter API (GPT-5-mini)
- Uses field specs from CRM configuration (if available)
- Extracts structured data (MemoExtraction)
- Updates memo: `extraction` (JSONB), status → `pending_review`

### 4. Approval (User Action)
- User reviews extraction in MemoDetail page
- Can edit fields before approving
- Can match to existing deal or create new
- Calls `POST /api/v1/memos/{id}/approve`
- If HubSpot connected:
  - Sync service orchestrates: company → contact → deal → associations
  - Each operation tracked in `crm_updates` table
  - Status → `approved`

### 5. Real-time Transcription (Alternative Flow)
- User can use WebSocket (`/api/v1/transcription/live`) during recording
- Dual streaming: Deepgram + Speechmatics
- Provides live transcript to user
- Can upload audio with transcript (skips Deepgram step)

---

## Key Features

### ✅ Implemented
1. **Authentication** - Supabase Auth (signup, login, JWT)
2. **Voice Recording** - MediaRecorder API, audio upload
3. **Real-time Transcription** - WebSocket proxy (Deepgram + Speechmatics)
4. **Transcription Service** - Deepgram batch transcription
5. **Extraction Service** - OpenRouter/GPT-5-mini structured extraction
6. **HubSpot Integration** - Full sync (contacts, companies, deals, associations)
7. **Deal Matching** - Intelligent matching algorithm
8. **Approval Preview** - Shows what will be updated before sync
9. **Field Whitelisting** - Users control which fields AI can update
10. **Schema Caching** - Reduces API calls
11. **CRM Updates Audit Trail** - Tracks all CRM operations

### 🚧 Partially Implemented
- Landing page (UI complete, needs content polish)
- Dashboard pages (structure exists, some pages may need refinement)

### ❌ Not Implemented (Planned)
- Salesforce integration
- Pipedrive integration
- Usage analytics (backend may exist, frontend needs implementation)
- Multi-language extraction (currently English-focused)

---

## Technology Stack

### Backend
- **Python 3.11+** - Language
- **FastAPI** - Web framework
- **Pydantic** - Data validation
- **Supabase** - Database + Auth + Storage
- **Deepgram SDK** - Speech-to-text
- **OpenRouter** - LLM API (GPT-5-mini)
- **Speechmatics** - Alternative transcription provider (WebSocket only)
- **httpx** - HTTP client (async)

### Frontend
- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool
- **React Router 6** - Routing
- **TanStack Query** - Server state management
- **Tailwind CSS** - Styling
- **shadcn/ui** - UI components
- **Zod** - Schema validation (if used)

### Infrastructure
- **Supabase** - Database (PostgreSQL), Auth, Storage
- **Vercel/Render** - Deployment (per PRD)

---

## Key Design Decisions

### 1. Deal-First Approach
- Current implementation focuses on deals as primary CRM object
- Matching, preview, and sync services are deal-centric
- Rationale: Deals are the core value proposition

### 2. Separate Columns for Critical Fields
- `matched_deal_id`, `matched_deal_name`, `is_new_deal` stored as separate columns
- Configuration stored in dedicated table with typed columns
- Rationale: Type safety, queryability, foreign key constraints

### 3. Field Whitelisting
- Users configure `allowed_deal_fields`, `allowed_contact_fields`, `allowed_company_fields`
- Only whitelisted fields can be updated by AI
- Rationale: Trust and safety - users control what AI can touch

### 4. Private App vs OAuth
- HubSpot uses Private App tokens (not OAuth)
- Simpler for MVP, but less flexible (tokens don't expire)
- Rationale: Faster implementation, easier user onboarding

### 5. Dual Transcription Providers
- WebSocket endpoint streams to both Deepgram and Speechmatics
- User sees transcripts from both providers
- Rationale: Comparison, redundancy, user choice

---

## Future Architecture Improvements (Per ARCHITECTURE_NOTES.md)

### Multi-Object Support
- Refactor to generic `CRMObjectMatcher`, `CRMUpdatePreview`, `CRMSyncOrchestrator`
- Currently deal-specific, hard to extend to contacts/companies
- Should be implemented when adding contacts/companies matching

### JSONB vs Separate Columns
- Consider hybrid approach: critical fields as columns, metadata as JSONB
- Migration planned when adding multi-object support

---

## Environment Variables

### Backend
- `DEEPGRAM_API_KEY` - Deepgram API key
- `SPEECHMATICS_API_KEY` - Speechmatics API key (optional)
- `OPENROUTER_API_KEY` - OpenRouter API key
- `EXTRACTION_MODEL` - Model name (default: "openai/gpt-5-mini")
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_SERVICE_ROLE_KEY` - Supabase service role key
- `ENVIRONMENT` - Environment (development/production)
- `FRONTEND_URL` - Frontend URL for CORS

---

## Summary

Vocify is a well-architected MVP with:
- ✅ Complete HubSpot integration
- ✅ Full voice memo processing pipeline
- ✅ Real-time transcription support
- ✅ Intelligent deal matching
- ✅ Approval workflow with preview
- ✅ Field-level access control
- ✅ Audit trail for CRM operations

The codebase follows clean architecture principles with feature-based organization, type safety, and clear separation of concerns. The backend is async-first (FastAPI), and the frontend uses modern React patterns with TanStack Query for server state.

**Current Status:** MVP complete, production-ready for HubSpot users.
