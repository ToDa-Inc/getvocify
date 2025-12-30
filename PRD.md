Vocify.io - Product Requirements Document (PRD)
Project Overview
Product Name: Vocify
Domain: vocify.io
Tagline: "Voice to CRM in 60 seconds. Built for modern sales teams."
Mission: Eliminate 5+ hours/week of manual CRM data entry for field sales reps by converting voice memos into structured CRM updates automatically.

Technical Stack

> **Note:** See `ARCHITECTURE.md` for detailed implementation guidelines and coding rules.

### Core Technologies

| Layer | Technology | Why |
|-------|------------|-----|
| **Frontend** | Vite + React 18 + React Router 6 | Fast builds, simple SPA, no SSR needed |
| **Backend** | Python (FastAPI) | Async, fast, great for AI/ML |
| **Database** | Supabase (PostgreSQL) | Managed Postgres, built-in auth, RLS |
| **Deployment** | Vercel (frontend) + Render (backend) | Simple, scalable |

### AI/ML Services

| Service | Provider | Purpose |
|---------|----------|---------|
| **Speech-to-Text** | Deepgram Nova-2 | Best accuracy, fast, good pricing |
| **LLM** | GPT-5 Mini | Structured extraction from transcripts |

### CRM Integrations

| Phase | CRM | Timeline |
|-------|-----|----------|
| **MVP** | HubSpot | Week 1-2 |
| **V2** | Salesforce | After 100 HubSpot users |
| **V3** | Pipedrive | After Salesforce |

### What We Don't Use (MVP)

- ❌ **Next.js** - Overkill for SPA, no SSR needed
- ❌ **Docker** - Adds complexity, not needed for single dev
- ❌ **LangChain** - Direct API calls are simpler
- ❌ **Redis/Celery** - Sync processing is fast enough
- ❌ **WebSocket streaming** - Batch upload works for 30-120s memos


Design System
Color Palette
css/* Primary Colors */
--cream: #FAF7F0
--black: #0A0A0A
--white: #FFFFFF

/* Accent Colors */
--cream-dark: #E8E3D6
--gray-light: #F5F5F5
--gray-medium: #9CA3AF
--gray-dark: #374151

/* Semantic Colors */
--success: #10B981
--error: #EF4444
--warning: #F59E0B
--info: #3B82F6
```

### Typography
- **Primary Font:** Inter (clean, modern, excellent readability)
- **Font Weights:** 400 (regular), 500 (medium), 600 (semibold), 700 (bold)

### Design Principles
- Minimalist and clean
- Generous whitespace
- Clear visual hierarchy
- Mobile-first responsive design
- Smooth animations (Framer Motion)
- Accessibility compliant (WCAG 2.1 AA)

---

## Repository Structure

> **Note:** See `ARCHITECTURE.md` for detailed folder structure rules and guidelines.

```
vocify/
├── src/                          # Frontend (Vite + React)
│   ├── app/                      # App shell
│   │   ├── App.tsx
│   │   ├── router.tsx
│   │   └── providers.tsx
│   ├── features/                 # Feature modules (THE CORE)
│   │   ├── auth/                 # Authentication
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── api.ts
│   │   │   ├── context.tsx
│   │   │   └── types.ts
│   │   ├── recording/            # Voice recording
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   └── types.ts
│   │   ├── memos/                # Voice memos management
│   │   │   ├── components/
│   │   │   ├── hooks/
│   │   │   ├── api.ts
│   │   │   └── types.ts
│   │   ├── approval/             # Extraction review workflow
│   │   │   ├── components/
│   │   │   └── types.ts
│   │   └── integrations/         # CRM connections
│   │       ├── components/
│   │       ├── hooks/
│   │       ├── api.ts
│   │       └── types.ts
│   ├── shared/                   # Truly shared code
│   │   ├── components/           # Generic UI components
│   │   ├── hooks/                # Generic hooks
│   │   ├── lib/                  # Utilities, API client
│   │   └── types/                # Common types
│   ├── ui/                       # Design system (shadcn)
│   ├── layouts/                  # Page layouts
│   └── pages/                    # Route entry points (thin)
│
├── backend/                      # Python FastAPI
│   ├── app/
│   │   ├── main.py               # FastAPI entry point
│   │   ├── config.py             # Settings
│   │   ├── deps.py               # Dependency injection
│   │   ├── api/
│   │   │   ├── auth.py           # /auth/* endpoints
│   │   │   ├── memos.py          # /memos/* endpoints
│   │   │   └── crm.py            # /crm/* endpoints
│   │   ├── services/
│   │   │   ├── transcription.py  # Deepgram
│   │   │   ├── extraction.py     # GPT-5-mini
│   │   │   └── hubspot.py        # HubSpot API
│   │   └── models.py             # Pydantic schemas
│   ├── requirements.txt
│   └── .env.example
│
├── ARCHITECTURE.md               # Architecture rules (READ THIS)
├── PRD.md                        # Product requirements
├── PRODUCT_OVERVIEW.md           # Product brief
├── package.json
└── README.md

Core Features (MVP - Week 1-2)
1. Authentication & User Management

Email/password signup
OAuth with Google (optional for faster signup)
Email verification
Supabase Auth integration

2. Voice Memo Recording
User Flow:

User clicks "Record Voice Memo" button
Browser requests microphone permission
User speaks for 30-120 seconds
Audio automatically uploads to backend
Processing starts immediately

Technical Requirements:

Browser MediaRecorder API
Audio format: WebM or MP3
Max file size: 10MB
Max duration: 3 minutes
Upload progress indicator
Support for both recording and file upload

3. Speech-to-Text Processing
Deepgram Integration:
python# Example implementation
async def transcribe_audio(audio_file: bytes) -> dict:
    """
    Transcribe audio using Deepgram
    
    Returns:
        {
            "transcript": "full text",
            "confidence": 0.95,
            "words": [...],  # word-level timestamps
            "duration": 45.2  # seconds
        }
    """
    # Deepgram Nova-2 model (highest accuracy)
    # Features: punctuation, diarization, paragraphs
4. Structured Data Extraction
GPT-5 Mini Integration:
python# Example structured output schema
class VoiceMemoExtraction(BaseModel):
    """Structured extraction from sales voice memo"""
    
    # Deal Information
    company_name: Optional[str]
    deal_amount: Optional[float]
    deal_stage: Optional[str]
    close_date: Optional[str]  # ISO format
    
    # Contact Information
    contact_name: Optional[str]
    contact_role: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    
    # Meeting Details
    meeting_summary: str
    pain_points: List[str]
    next_steps: List[str]
    competitors_mentioned: List[str]
    decision_makers: List[str]
    
    # Metadata
    confidence_score: float  # 0-1
    requires_review: bool
    extraction_notes: Optional[str]
```

**Extraction Prompt Template:**
```
You are an AI assistant that extracts structured CRM data from sales call transcripts.

TRANSCRIPT:
{transcript}

EXISTING CRM CONTEXT (if available):
{crm_context}

Extract the following information in JSON format:
- Company name and deal details (amount, stage, close date)
- Contact information (name, role, email, phone)
- Meeting summary (2-3 sentences)
- Pain points discussed
- Next steps and action items
- Competitors mentioned
- Decision makers identified

If information is unclear or missing, set the field to null.
Provide a confidence score (0-1) for the extraction quality.
Flag requires_review=true if confidence < 0.8 or critical fields are ambiguous.
5. HubSpot Integration
OAuth Flow:

User clicks "Connect HubSpot"
Redirect to HubSpot OAuth consent screen
Receive authorization code
Exchange for access + refresh tokens
Store tokens securely in Supabase (encrypted)

Deal Schema Detection:
pythonasync def get_hubspot_deal_schema(access_token: str, pipeline_id: str) -> dict:
    """
    Fetch HubSpot deal properties and pipeline stages
    
    Returns:
        {
            "properties": [
                {
                    "name": "dealname",
                    "label": "Deal Name",
                    "type": "string",
                    "required": true
                },
                {
                    "name": "amount",
                    "label": "Deal Amount",
                    "type": "number",
                    "required": false
                },
                # ... all custom properties
            ],
            "stages": [
                {"id": "123", "label": "Qualification"},
                {"id": "124", "label": "Needs Analysis"},
                # ... all stages
            ]
        }
    """
Auto-Mapping Logic:
pythonasync def map_extraction_to_hubspot(
    extraction: VoiceMemoExtraction,
    deal_schema: dict,
    existing_deal_id: Optional[str] = None
) -> dict:
    """
    Intelligently map extracted data to HubSpot fields
    
    Uses:
    - Exact field name matching
    - Fuzzy matching for custom fields
    - GPT-5 Mini for ambiguous mappings
    
    Returns HubSpot API payload
    """
6. Approval Workflow
Before/After Comparison UI:
typescriptinterface ApprovalView {
  original_transcript: string
  extracted_data: ExtractedData
  crm_updates: {
    field_name: string
    current_value: any
    new_value: any
    confidence: number
  }[]
  suggested_actions: {
    type: 'create_deal' | 'update_deal' | 'create_contact' | 'create_task'
    description: string
    data: any
  }[]
}
User Actions:

✅ Approve All (high confidence > 0.9)
✏️ Edit & Approve (medium confidence 0.7-0.9)
❌ Reject (low confidence < 0.7)
🔄 Re-extract (if transcription was wrong)

7. CRM Update Execution
Atomic Updates:

All CRM updates happen in a transaction
If any update fails, roll back all changes
Provide detailed error messages
Retry logic for transient failures (rate limits, network issues)

Audit Log:
pythonclass CRMUpdate(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    voice_memo_id: uuid.UUID
    crm_type: str  # hubspot, salesforce, etc
    action_type: str  # create, update, delete
    resource_type: str  # deal, contact, activity, task
    resource_id: Optional[str]  # CRM's internal ID
    payload: dict
    status: str  # pending, success, failed
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

Database Schema (Supabase)
Users Table
sqlCREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  email VARCHAR(255) UNIQUE NOT NULL,
  full_name VARCHAR(255),
  company_name VARCHAR(255),
  phone VARCHAR(50),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
CRM Connections Table
sqlCREATE TABLE crm_connections (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  crm_type VARCHAR(50) NOT NULL, -- hubspot, salesforce, pipedrive, ghl
  access_token TEXT NOT NULL, -- encrypted
  refresh_token TEXT, -- encrypted
  token_expires_at TIMESTAMP,
  crm_user_id VARCHAR(255),
  crm_user_email VARCHAR(255),
  portal_id VARCHAR(255), -- for HubSpot
  instance_url VARCHAR(255), -- for Salesforce
  is_active BOOLEAN DEFAULT true,
  last_synced_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(user_id, crm_type)
);
Voice Memos Table
sqlCREATE TABLE voice_memos (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  audio_url TEXT NOT NULL,
  audio_duration FLOAT, -- seconds
  file_size INTEGER, -- bytes
  transcript TEXT,
  transcript_confidence FLOAT,
  extracted_data JSONB, -- structured extraction
  extraction_confidence FLOAT,
  status VARCHAR(50) DEFAULT 'processing', -- processing, completed, failed, approved, rejected
  error_message TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  processed_at TIMESTAMP,
  approved_at TIMESTAMP
);
CRM Updates Table
sqlCREATE TABLE crm_updates (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  voice_memo_id UUID REFERENCES voice_memos(id) ON DELETE CASCADE,
  crm_connection_id UUID REFERENCES crm_connections(id) ON DELETE CASCADE,
  action_type VARCHAR(50), -- create_deal, update_deal, create_contact, etc
  resource_type VARCHAR(50), -- deal, contact, activity, task
  resource_id VARCHAR(255), -- CRM's internal ID
  payload JSONB,
  status VARCHAR(50) DEFAULT 'pending', -- pending, success, failed, rolled_back
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW(),
  completed_at TIMESTAMP
);
Usage Tracking Table
sqlCREATE TABLE usage_tracking (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  voice_memos_count INTEGER DEFAULT 0,
  total_audio_duration FLOAT DEFAULT 0, -- seconds
  crm_updates_count INTEGER DEFAULT 0,
  month_year VARCHAR(7), -- YYYY-MM
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(user_id, month_year)
);
```

---

## API Endpoints

### Authentication
```
POST   /api/v1/auth/signup
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me
```

### Voice Memos
```
POST   /api/v1/voice/upload          # Upload audio file
POST   /api/v1/voice/record-start    # Start recording session
POST   /api/v1/voice/record-chunk    # Upload audio chunk
POST   /api/v1/voice/record-end      # Finalize recording
GET    /api/v1/voice/memos           # List user's memos
GET    /api/v1/voice/memos/:id       # Get specific memo
DELETE /api/v1/voice/memos/:id       # Delete memo
POST   /api/v1/voice/memos/:id/approve      # Approve extraction
POST   /api/v1/voice/memos/:id/reject       # Reject extraction
POST   /api/v1/voice/memos/:id/re-extract   # Re-run extraction
```

### CRM Integration
```
GET    /api/v1/crm/hubspot/authorize         # Initiate OAuth
GET    /api/v1/crm/hubspot/callback          # OAuth callback
POST   /api/v1/crm/hubspot/disconnect        # Disconnect CRM
GET    /api/v1/crm/hubspot/schema            # Get deal schema
GET    /api/v1/crm/hubspot/deals             # List deals
GET    /api/v1/crm/hubspot/contacts          # List contacts
POST   /api/v1/crm/hubspot/test              # Test connection

# Same pattern for other CRMs
GET    /api/v1/crm/salesforce/authorize
GET    /api/v1/crm/ghl/authorize
GET    /api/v1/crm/pipedrive/authorize
```

### User & Settings
```
GET    /api/v1/user/profile
PATCH  /api/v1/user/profile
GET    /api/v1/user/usage
GET    /api/v1/user/connections
```

---

## Frontend Pages & Components

### Page Structure
```
app/
├── (auth)/
│   ├── login/page.tsx
│   ├── signup/page.tsx
│   └── verify-email/page.tsx
├── (dashboard)/
│   ├── layout.tsx                    # Dashboard shell
│   ├── page.tsx                      # Dashboard home (recent memos)
│   ├── record/page.tsx               # Voice recording page
│   ├── memos/page.tsx                # Memos list
│   ├── memos/[id]/page.tsx           # Memo detail + approval
│   ├── integrations/page.tsx         # CRM connections
│   ├── integrations/hubspot/page.tsx
│   ├── settings/page.tsx
│   └── usage/page.tsx
├── api/
│   └── (proxy routes to backend)
└── page.tsx                          # Landing page
Key Components
VoiceRecorder.tsx
typescript'use client'

interface VoiceRecorderProps {
  onRecordingComplete: (audioBlob: Blob) => void
  maxDuration?: number // seconds
}

export function VoiceRecorder({ onRecordingComplete, maxDuration = 180 }: VoiceRecorderProps) {
  // Features:
  // - Request microphone permission
  // - Visual waveform during recording
  // - Timer display
  // - Auto-stop at max duration
  // - Cancel recording
  // - Preview playback before submit
}
ApprovalWorkflow.tsx
typescriptinterface ApprovalWorkflowProps {
  memoId: string
  transcript: string
  extraction: ExtractedData
  crmUpdates: CRMUpdate[]
  onApprove: () => void
  onEdit: (updates: Partial<ExtractedData>) => void
  onReject: () => void
}

export function ApprovalWorkflow(props: ApprovalWorkflowProps) {
  // Features:
  // - Side-by-side comparison
  // - Inline editing
  // - Confidence indicators
  // - Field-by-field approval
  // - Bulk actions
}
CRMConnectionCard.tsx
typescriptinterface CRMConnectionCardProps {
  crmType: 'hubspot' | 'salesforce' | 'pipedrive' | 'ghl'
  connection?: CRMConnection
  onConnect: () => void
  onDisconnect: () => void
  onTest: () => void
}

export function CRMConnectionCard(props: CRMConnectionCardProps) {
  // Features:
  // - Connection status
  // - Last synced time
  // - Test connection button
  // - Reconnect if expired
}

User Flows
Onboarding Flow

User signs up (email + password)
Email verification sent
User redirected to dashboard
Welcome modal: "Connect your CRM to get started"
User clicks "Connect HubSpot"
OAuth flow → HubSpot authorization
Success: "HubSpot connected! Try recording your first voice memo."
Tour of voice recording interface
User records first memo
System processes and shows approval workflow
User approves → CRM updated
Success message: "Your first deal is updated! 🎉"

Daily Usage Flow

User finishes client meeting
Opens Vocify on phone
Clicks "Record Voice Memo"
Speaks for 45 seconds covering:

Company name
Meeting highlights
Deal status
Next steps


Clicks "Done" → Audio uploads
Notification: "Processing your memo..."
30 seconds later: "Memo ready for review"
User opens approval screen
Reviews extracted data
Edits close date (AI suggested wrong date)
Clicks "Approve & Update CRM"
Success: "HubSpot deal updated in 60 seconds"


MVP Success Criteria
Week 1-2 (Build Phase)

✅ User can sign up and log in
✅ User can connect HubSpot account
✅ User can record 60-second voice memo
✅ System transcribes with Deepgram (>90% accuracy)
✅ System extracts structured data with GPT-5 Mini
✅ User can review and approve extraction
✅ System updates HubSpot deal/contact/activity
✅ User sees success confirmation

Week 3-4 (Beta Testing)

✅ 10 beta users testing product
✅ 80%+ extraction accuracy
✅ 90%+ transcription accuracy
✅ <5% error rate on CRM updates
✅ Average processing time <60 seconds
✅ Positive user feedback (NPS >40)

Month 1 (Launch)

✅ 20 paying customers ($500 MRR)
✅ 5+ voice memos per user per week
✅ <5% churn rate
✅ CAC <$200


Technical Considerations
Permissions & Security
typescript// Browser permissions required
navigator.permissions.query({ name: 'microphone' })

// Supabase Row Level Security (RLS)
// Users can only access their own data
CREATE POLICY "Users can only view their own voice memos"
  ON voice_memos FOR SELECT
  USING (auth.uid() = user_id);

// Encrypted token storage
// Use Supabase Vault for CRM tokens
Performance Optimization

Audio compression before upload (reduce file size 50%+)
Streaming transcription (Deepgram supports WebSocket)
Parallel processing (transcribe + extract simultaneously)
Background jobs for non-critical tasks (Celery or similar)
Redis caching for CRM schema (reduce API calls)

Error Handling
pythonclass VocifyException(Exception):
    """Base exception for Vocify"""
    pass

class TranscriptionError(VocifyException):
    """Error during speech-to-text"""
    pass

class ExtractionError(VocifyException):
    """Error during structured extraction"""
    pass

class CRMIntegrationError(VocifyException):
    """Error communicating with CRM API"""
    pass

# Implement retry logic with exponential backoff
# Log all errors to Sentry or similar monitoring service
Monitoring & Observability

Log all API calls (request/response)
Track processing times for each step
Monitor Deepgram API usage and costs
Monitor OpenAI API usage and costs
Set up alerts for high error rates
Track user behavior (Mixpanel or PostHog)


Deployment Strategy
Development Environment
yaml# docker-compose.yml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./backend:/app
    command: uvicorn app.main:app --reload --host 0.0.0.0

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    volumes:
      - ./frontend:/app
    command: npm run dev
```

### Production Deployment

**Frontend (Vercel):**
- Automatic deployments from `main` branch
- Environment variables configured in Vercel dashboard
- Custom domain: vocify.io

**Backend (Render):**
- Dockerfile deployment
- Auto-scaling based on CPU/memory
- Environment variables configured in Render dashboard
- Custom domain: api.vocify.io

**Database (Supabase):**
- Managed PostgreSQL
- Automatic backups
- Connection pooling enabled

---

## Development Timeline

### Week 1: Core Infrastructure
**Days 1-2:**
- Set up monorepo structure
- Configure Next.js + FastAPI
- Set up Supabase project
- Configure Docker
- Implement authentication (Supabase Auth)

**Days 3-4:**
- Implement voice recording component
- Audio upload to Supabase Storage
- Integrate Deepgram API
- Test transcription accuracy

**Days 5-7:**
- Integrate GPT-5 Mini for extraction
- Build structured output schema
- Implement extraction pipeline
- Test extraction accuracy

### Week 2: CRM Integration & UI
**Days 8-9:**
- Implement HubSpot OAuth flow
- Fetch and parse HubSpot deal schema
- Build field mapping logic
- Test HubSpot API updates

**Days 10-12:**
- Build approval workflow UI
- Implement before/after comparison
- Build CRM update execution
- Error handling and retry logic

**Days 13-14:**
- Build landing page
- Polish dashboard UI
- End-to-end testing
- Bug fixes

### Week 3-4: Beta Testing & Iteration
- Recruit 10 beta users
- Monitor usage and errors
- Fix critical bugs
- Gather feedback
- Iterate on UX

---

## Cursor AI Prompts for Development

### Initial Setup
```
Create a monorepo structure for Vocify with:
1. Next.js 14 frontend (App Router, TypeScript, Tailwind)
2. Python FastAPI backend
3. Supabase integration
4. Docker setup for local development

Use this color palette:
- Primary: #FAF7F0 (cream)
- Text: #0A0A0A (black)
- Background: #FFFFFF (white)
- Accent: #E8E3D6 (cream-dark)

Install these dependencies:
Frontend: next, react, typescript, tailwindcss, @supabase/supabase-js, framer-motion
Backend: fastapi, uvicorn, supabase-py, deepgram-sdk, openai, httpx, pydantic

Set up Supabase Auth with email/password.
```

### Voice Recording Component
```
Create a VoiceRecorder React component using:
- Browser MediaRecorder API
- Visual waveform animation during recording
- Timer display (MM:SS format)
- Max duration: 3 minutes (auto-stop)
- Buttons: Start, Stop, Cancel, Playback Preview
- Upload audio to Supabase Storage on complete
- Show upload progress bar

Use Framer Motion for smooth animations.
Style with Tailwind using the cream/black/white palette.
Make it mobile-responsive.
```

### Deepgram Integration
```
Create a Python service class for Deepgram integration:

Class: DeepgramService
Methods:
- async transcribe_audio(audio_bytes, language='en') -> dict
  - Use Deepgram Nova-2 model
  - Enable: punctuation, diarization, paragraphs
  - Return: transcript, confidence, word timestamps, duration
  
Handle errors gracefully with custom exceptions.
Add retry logic for transient failures.
Log all API calls for monitoring.
```

### GPT-5 Mini Extraction
```
Create a Python service for structured extraction:

Class: ExtractionService
Methods:
- async extract_crm_data(transcript: str, crm_context: dict = None) -> VoiceMemoExtraction
  - Use GPT-5 Mini with structured outputs
  - Extract: company, deal details, contacts, pain points, next steps
  - Provide confidence score (0-1)
  - Flag for review if confidence < 0.8
  
Use this Pydantic model for structured output:
[provide VoiceMemoExtraction schema from PRD]

Add comprehensive error handling.
```

### HubSpot OAuth
```
Implement HubSpot OAuth 2.0 flow:

Endpoints:
1. GET /api/v1/crm/hubspot/authorize
   - Redirect to HubSpot OAuth with required scopes
   
2. GET /api/v1/crm/hubspot/callback
   - Exchange code for access token
   - Store tokens in Supabase (encrypted)
   - Redirect to dashboard with success message

Required scopes:
- crm.objects.contacts.read/write
- crm.objects.deals.read/write
- crm.objects.companies.read/write
- crm.schemas.deals.read

Store tokens using Supabase Vault for encryption.
```

### Approval Workflow UI
```
Create an ApprovalWorkflow component with:

Layout:
- Left side: Original transcript (scrollable)
- Right side: Extracted data fields

Features:
- Color-coded confidence indicators (green >0.9, yellow 0.7-0.9, red <0.7)
- Inline editing for each field
- "Approve All" button (disabled if any field has confidence <0.7)
- "Edit & Approve" for individual fields
- "Reject" button to discard extraction
- Loading state during CRM update

Use React Hook Form for form handling.
Style with Tailwind and Framer Motion for smooth transitions.

Environment Variables
Frontend (.env.local)
bashNEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SITE_URL=http://localhost:3000
Backend (.env)
bash# Supabase
DATABASE_URL=postgresql://...
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# AI Services
DEEPGRAM_API_KEY=your_deepgram_key
OPENAI_API_KEY=your_openai_key

# HubSpot OAuth
HUBSPOT_CLIENT_ID=your_hubspot_client_id
HUBSPOT_CLIENT_SECRET=your_hubspot_client_secret
HUBSPOT_REDIRECT_URI=http://localhost:8000/api/v1/crm/hubspot/callback

# App Config
JWT_SECRET=your_jwt_secret
ENVIRONMENT=development
```

---

## Next Steps for Cursor Development

1. **Start with repository setup**
```
   Create the monorepo structure with Next.js + FastAPI
   Set up Docker Compose for local development
   Configure Supabase client
```

2. **Build authentication**
```
   Implement Supabase Auth signup/login
   Create protected routes in Next.js
   Build login/signup UI with the cream/black design
```

3. **Implement voice recording**
```
   Build VoiceRecorder component
   Add audio upload to Supabase Storage
   Create backend endpoint to receive audio
```

4. **Integrate Deepgram**
```
   Create DeepgramService class
   Test transcription with sample audio
   Handle errors and edge cases
```

5. **Integrate GPT-5 Mini**
```
   Create ExtractionService class
   Define structured output schema
   Test extraction with sample transcripts
```

6. **Build HubSpot integration**
```
   Implement OAuth flow
   Fetch HubSpot deal schema
   Build update logic
   Test with real HubSpot account
```

7. **Create approval workflow**
```
   Build ApprovalWorkflow UI
   Connect to backend APIs
   Test end-to-end flow
```

8. **Polish and deploy**
```
   Build landing page
   Final UI polish
   Deploy to Vercel + Render
   Test in production