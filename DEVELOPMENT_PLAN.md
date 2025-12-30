# Vocify Development Plan

> **Goal:** Voice to CRM in 60 seconds. Ship MVP in 2 weeks.

---

## Current State Analysis

### ✅ What's Done
- Landing page (complete, 15 sections)
- Dashboard layout with navigation
- Basic record page UI (fake, no real recording)
- Memo detail page UI (hardcoded data)
- Feature-based folder structure
- TypeScript types defined
- API client abstraction
- React Query hooks scaffolded

### ❌ What's Missing (For MVP)
1. **Real audio recording** - MediaRecorder integration
2. **Backend API** - FastAPI server
3. **Authentication** - Supabase Auth
4. **Transcription** - Deepgram integration
5. **Extraction** - GPT-5-mini integration
6. **HubSpot OAuth** - CRM connection
7. **Real data flow** - Connect frontend to backend

---

## Phase 1: Core Recording Flow (Week 1)

### Sprint 1.1: Audio Recording (Day 1-2)

**Goal:** User can record audio and see it working

| Task | File | Priority |
|------|------|----------|
| Wire up `useMediaRecorder` hook to RecordPage | `pages/dashboard/record.tsx` | P0 |
| Add real waveform visualization | `features/recording/components/` | P0 |
| Add audio playback preview | `features/recording/components/` | P1 |
| Add upload dropzone for files | `features/recording/components/` | P1 |
| Store audio blob in state | `features/recording/hooks/` | P0 |

**Acceptance Criteria:**
- [ ] Click record → microphone activates
- [ ] Waveform animates during recording
- [ ] Timer counts up
- [ ] Click stop → audio preview plays
- [ ] Can re-record or continue

### Sprint 1.2: Backend Setup (Day 2-3)

**Goal:** FastAPI server with basic endpoints

```
backend/
├── app/
│   ├── main.py           # FastAPI app
│   ├── config.py         # Environment settings
│   ├── api/
│   │   ├── auth.py       # /auth/* routes
│   │   └── memos.py      # /memos/* routes
│   ├── services/
│   │   ├── storage.py    # Supabase Storage
│   │   ├── transcription.py  # Deepgram
│   │   └── extraction.py     # OpenAI/OpenRouter
│   └── models.py         # Pydantic schemas
├── requirements.txt
└── .env
```

| Task | Priority |
|------|----------|
| Create FastAPI project structure | P0 |
| Set up Supabase client | P0 |
| Create `/memos/upload` endpoint | P0 |
| Store audio in Supabase Storage | P0 |
| Return memo ID and status URL | P0 |

**Acceptance Criteria:**
- [ ] POST audio file → returns memo ID
- [ ] Audio stored in Supabase Storage
- [ ] Memo record created in database

### Sprint 1.3: Transcription (Day 3-4)

**Goal:** Audio → Text with Deepgram

| Task | Priority |
|------|----------|
| Integrate Deepgram SDK | P0 |
| Create transcription service | P0 |
| Process audio after upload | P0 |
| Update memo with transcript | P0 |
| Handle errors gracefully | P1 |

**Acceptance Criteria:**
- [ ] Audio file → transcript in <30 seconds
- [ ] Confidence score saved
- [ ] Memo status updates to 'transcribing' → 'extracting'

### Sprint 1.4: Extraction (Day 4-5)

**Goal:** Transcript → Structured CRM Data

| Task | Priority |
|------|----------|
| Integrate OpenRouter for GPT-5-mini | P0 |
| Create extraction prompt | P0 |
| Parse structured JSON output | P0 |
| Update memo with extraction | P0 |
| Calculate confidence scores | P1 |

**Extraction Prompt:**
```
You are an AI assistant that extracts structured CRM data from sales call transcripts.

TRANSCRIPT:
{transcript}

Extract the following in JSON format:
- companyName: string | null
- dealAmount: number | null (in EUR)
- dealStage: string | null
- closeDate: string | null (ISO format)
- contactName: string | null
- contactRole: string | null
- summary: string (2-3 sentences)
- painPoints: string[]
- nextSteps: string[]
- competitors: string[]

Rules:
- Set fields to null if not mentioned
- Provide confidence (0-1) for each field
- Be conservative - only extract what's explicitly stated
```

**Acceptance Criteria:**
- [ ] Transcript → structured extraction in <10 seconds
- [ ] JSON matches our `MemoExtraction` type
- [ ] Confidence scores per field

---

## Phase 2: Approval & CRM (Week 2)

### Sprint 2.1: Approval Workflow (Day 6-7)

**Goal:** User reviews and edits extraction

| Task | Priority |
|------|----------|
| Connect MemoDetail to real API | P0 |
| Add field editing with validation | P0 |
| Add confidence indicators (colors) | P1 |
| Add approve/reject actions | P0 |
| Show success/error states | P0 |

**Acceptance Criteria:**
- [ ] Real memo data loads from API
- [ ] User can edit any field
- [ ] Confidence colors: green >0.9, yellow 0.7-0.9, red <0.7
- [ ] Approve → memo status changes

### Sprint 2.2: Authentication (Day 7-8)

**Goal:** User can sign up and log in

| Task | Priority |
|------|----------|
| Create login/signup pages | P0 |
| Wire up Supabase Auth | P0 |
| Add AuthProvider to app | P0 |
| Protect dashboard routes | P0 |
| Add logout functionality | P0 |

**Acceptance Criteria:**
- [ ] New user can sign up with email
- [ ] User can log in
- [ ] Dashboard requires auth
- [ ] User stays logged in (refresh token)

### Sprint 2.3: HubSpot Integration (Day 8-10)

**Goal:** Connect HubSpot and push data

| Task | Priority |
|------|----------|
| Create HubSpot OAuth flow | P0 |
| Store tokens in Supabase | P0 |
| Fetch HubSpot deal schema | P1 |
| Create/update deal on approval | P0 |
| Create contact if new | P1 |
| Add connection status UI | P0 |

**Acceptance Criteria:**
- [ ] User connects HubSpot via OAuth
- [ ] Connection shows as "connected"
- [ ] Approve memo → deal created/updated in HubSpot
- [ ] Success message shows what was updated

### Sprint 2.4: Polish & Deploy (Day 11-14)

| Task | Priority |
|------|----------|
| Error handling everywhere | P0 |
| Loading states everywhere | P0 |
| Mobile responsiveness check | P0 |
| Deploy frontend to Vercel | P0 |
| Deploy backend to Render | P0 |
| Set up environment variables | P0 |
| End-to-end testing | P0 |

---

## What To Integrate NOW

### Immediate (Today)

1. **Deepgram** - Sign up at [deepgram.com](https://deepgram.com)
   - Create API key
   - Use Nova-2 model for best accuracy
   
2. **OpenRouter** - Sign up at [openrouter.ai](https://openrouter.ai)
   - Create API key
   - Use `openai/gpt-5-mini` for extraction
   - Fallback: `openai/gpt-4o-mini` or local models

3. **Supabase** - Already have? If not, create project
   - Enable Auth (email/password)
   - Create database tables (see schema in ARCHITECTURE.md)
   - Enable Storage for audio files

### This Week

4. **HubSpot** - Create developer account
   - Create app for OAuth
   - Get Client ID and Secret
   - Required scopes: `crm.objects.deals.read`, `crm.objects.deals.write`

---

## API Keys Needed

```env
# AI Services
DEEPGRAM_API_KEY=           # From console.deepgram.com
OPENROUTER_API_KEY=         # From openrouter.ai/keys

# Database & Auth
SUPABASE_URL=               # From supabase dashboard
SUPABASE_ANON_KEY=          # From supabase dashboard
SUPABASE_SERVICE_ROLE_KEY=  # From supabase dashboard (backend only)

# CRM (Week 2)
HUBSPOT_CLIENT_ID=          # From HubSpot developer portal
HUBSPOT_CLIENT_SECRET=      # From HubSpot developer portal
```

---

## Daily Checklist

### Before Starting
- [ ] Pull latest code
- [ ] Check this plan for today's tasks
- [ ] Review any blockers

### Before Committing
- [ ] Code follows RULES.md
- [ ] No lint/type errors
- [ ] Tested manually
- [ ] Commit message format correct

### End of Day
- [ ] Push all changes
- [ ] Update this plan if needed
- [ ] Note any blockers for tomorrow

---

## Success Metrics (MVP)

| Metric | Target |
|--------|--------|
| Recording → CRM update | < 60 seconds |
| Transcription accuracy | > 90% |
| Extraction accuracy | > 85% |
| Zero crashes | ✓ |
| Works on mobile | ✓ |

---

> **Focus:** Ship the core flow first. Polish later.


