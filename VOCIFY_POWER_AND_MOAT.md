# Vocify: Power, Value & Competitive Moat

> A clear articulation of what Vocify offers, why it matters, and what makes it defensible for end users—especially in the Spanish-speaking market.

---

## What Vocify Is

**Vocify** is a voice-to-CRM SaaS that converts voice memos into structured CRM updates in ~60 seconds. Sales reps speak for 30 seconds instead of typing for 10 minutes. The target: field sales reps who waste 5+ hours every week on manual CRM data entry.

**Core flow:**
1. Rep records a voice memo (or sends one via WhatsApp)
2. AI transcribes → extracts deals, contacts, next steps, objections
3. Rep reviews and approves
4. CRM (HubSpot) updates automatically

---

## Why It's Valuable

### 1. Time Savings That Compound

- **Before:** 10+ minutes per meeting to type notes, update deals, log next steps
- **After:** ~60 seconds total—record, review, approve
- **Impact:** 5+ hours saved per rep per week → €12,400+ revenue recovery per rep per year (based on average sales performance loss)

### 2. Data Quality & Compliance

- Reps who "forget to log it" create incomplete pipelines
- Managers can't coach without visibility
- Vocify ensures every meeting is captured, structured, and synced—with human approval before anything touches the CRM

### 3. Works Where Reps Already Are

- **Web app** — record from any device
- **Chrome extension** — hotkey (`Alt+Shift+V`) recording, context-aware (auto-associates with HubSpot deal when on a deal page)
- **WhatsApp** — no app download; reps send a voice note to Vocify and get extraction + approve/reject via buttons

---

## The Moat: What We Offer That Competitors Don't

### 1. WhatsApp-First Voice-to-CRM

**What we do:** Full WhatsApp integration (Meta + Unipile). Reps send a voice note to Vocify's WhatsApp number → transcription → extraction → interactive buttons (Approve / Add fields / Reject) → CRM sync. All without leaving WhatsApp.

**Why it's a moat:**
- WhatsApp is the dominant channel in LatAm and Spain for business communication
- No new app to install or learn
- Works on any phone, any plan
- Natural-language intent handling: "sí aprueba", "1", "add more" → system understands and acts

### 2. Spanish-Speaking Market Focus

**What we do:**
- Full i18n (EN + ES) for landing, dashboard, and UX
- Glossary + **phonetic collision correction** built for Spanish-English Spanglish sales environments
- LLM prompt explicitly instructs: "All text fields MUST use the SAME language as the transcript. Never translate."
- Extraction understands Spanish sales terminology (aseguradora, bróker, presupuesto, cierre, etc.)

**Phonetic collision rules (from codebase):**
- **Acronym collision:** FTES → FPS, FTS, "FT is", Efetes
- **Vowel flattening:** Cobee → Cobi, Deal → Dil
- **Consonant softening:** 50k → 50 cash, Edenred → En red
- **Entity priority:** If transcript sounds like a glossary term, always use the glossary term

**Why it's a moat:** Generic voice-to-CRM tools fail on Spanglish and Spanish accents. We're built for it.

### 3. Custom Glossary & Domain Adaptation

**What we do:**
- Users add custom terms (product names, acronyms, client names) to a glossary
- Glossary feeds into:
  - **Deepgram** (keywords) for better transcription
  - **Speechmatics** (custom_vocabulary + sounds_like)
  - **LLM extraction** (ground-truth correction rules)
- AI-generated phonetic hints for common mishearings

**Why it's a moat:** Medical device sales, insurance, real estate—each vertical has its own jargon. Vocify learns the user's vocabulary and corrects STT errors before extraction.

### 4. Schema-Driven Extraction

**What we do:**
- Pulls HubSpot field specs (deal, contact, company) and uses them as the extraction schema
- Only extracts what the user's CRM actually has
- Field whitelisting: users choose which fields the AI can update
- No generic "one size fits all" schema—adapts to each org

**Why it's a moat:** Enterprises have custom properties. We don't force a fixed schema; we map to theirs.

### 5. Deal Matching & Approval Workflow

**What we do:**
- Intelligent deal matching: when extraction mentions a company/contact, we search HubSpot and suggest existing deals
- User can: create new deal, match to existing, or choose from multiple matches (1, 2, 3)
- Approval preview: shows exactly what will be updated before sync
- Audit trail: every CRM operation logged in `crm_updates`

**Why it's a moat:** Reduces duplicate deals, keeps pipeline clean, and gives users control. No "AI overwrote my deal" surprises.

### 6. Multi-Channel, Multi-Provider Resilience

**What we do:**
- Transcription: Deepgram (batch) + Speechmatics (batch/WebSocket)
- Real-time WebSocket transcription during recording
- WhatsApp: Meta direct + Unipile (for multi-account / B2B setups)
- LLM: OpenRouter (model configurable: grok, gpt-5-mini, etc.)

**Why it's a moat:** Not locked to one vendor. Can swap providers without changing product behavior.

### 7. GDPR & EU Data Residency

**What we do:**
- Supabase (EU option)
- Encrypted in transit and at rest
- User data stays in user's control; no training on customer data

**Why it's a moat:** Spanish/EU customers require compliance. We're built for it from day one.

### 8. Chrome Extension: Context-Aware Recording

**What we do:**
- Hotkey recording from any tab
- When on a HubSpot deal page, extension parses URL and associates memo with that deal
- No need to open Vocify app—record in flow

**Why it's a moat:** Reps live in HubSpot. We meet them there.

---

## Spanish-Speaking Market: Strategic Fit

| Factor | Why Vocify Wins |
|--------|-----------------|
| **WhatsApp dominance** | LatAm/Spain use WhatsApp for work. We're the only voice-to-CRM that works natively in WhatsApp. |
| **Spanglish** | Sales calls mix Spanish and English. Our glossary + phonetic rules handle it. |
| **Vertical jargon** | Insurance, medical devices, real estate—each has terms. Glossary adapts. |
| **Mobile-first** | Many reps don't have laptops in the field. WhatsApp on phone = zero friction. |
| **GDPR** | EU customers need compliance. We're ready. |
| **Pricing** | €25/rep/month is accessible for SMBs in the region. |

---

## Summary: The Moat in One Sentence

**Vocify is the only voice-to-CRM that works natively in WhatsApp, understands Spanish and Spanglish sales terminology, adapts to each user's CRM schema and custom glossary, and gives full approval control before any sync—built for the Spanish-speaking market first.**

---

## What We Don't Claim (Honest Scope)

- Salesforce and Pipedrive integrations are planned, not yet live
- Multi-language extraction is improved for Spanish; other languages (FR, DE, IT, PT) are supported but not as deeply tuned
- Usage analytics and team dashboards exist in structure but may need refinement

---

*Based on codebase analysis: PRODUCT_OVERVIEW.md, CODEBASE_UNDERSTANDING.md, PRD.md, extraction/glossary services, WhatsApp processor, i18n, and chrome-extension.*
