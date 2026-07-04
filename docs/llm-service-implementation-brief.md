# Vocify LLM Service Layer — Implementation Brief

> **Target:** Cursor Agent  
> **Task:** Refactor the LLM client to support multiple providers with configurable routing  
> **Priority:** Unblocks enterprise sales (lost Inibsa PoC due to vendor assessment gap)  
> **Date:** 2026-07-04 (revised after compliance investigation)

---

## 1. WHAT WE ARE BUILDING

We are building a **multi-provider LLM service layer** (`backend/app/services/llm/`) that replaces the current single-provider OpenRouter client with a routing layer capable of dispatching LLM requests to different backends based on configuration. The service exposes a single unified interface (`chat()` and `chat_json()`) so that all callers — `ExtractionService`, glossary AI, WhatsApp message generation, and any future consumer — continue to work unchanged regardless of which backend is active.

### The problem this solves

**Inibsa (pharmaceutical, Barcelona) killed our PoC during vendor assessment.** Their IT Strategy Manager Roger Esquena asked what data center classification NextBit256 had. We responded: *"De momento no tienen ninguna certificación CPD."* This triggered a rejection, with Roger stating the infrastructure must meet minimum reliability standards.

The real gap was not a missing TIER certificate specifically — it was that we had no documented answer to the question "how reliable is your infrastructure?" Roger used TIER as his reference framework, but his actual concern was performance, availability, and security guarantees.

**What the market actually requires (evidence-based):**

We investigated what real SaaS companies and IT teams demand:

- **Zoho (a $1B+ SaaS company selling across Europe):** Lists ISO 27001, SOC 2 Type II, ISO 27701, ISO 27017/27018, ISO 22301 on their compliance page. Their European data centers are in Amsterdam and Dublin. **They do not mention Uptime Institute TIER certification anywhere.**
- **Reddit r/sysadmin vendor requirements thread:** IT teams ask for ISO 27001, SOC 2, pentest reports, DPA, encryption details. **TIER does not appear on the list.**
- **Stripe's SaaS compliance guide:** Lists GDPR, SOC 2, ISO 27001, HIPAA, PCI DSS as the standard frameworks. TIER is not mentioned.
- **GCP, AWS, and Azure all explicitly state they do NOT pursue Uptime Institute TIER certification.** They provide ISO 27001, SOC 1/2/3, and infrastructure whitepapers instead. Most enterprises have accepted this for 15+ years.
- **ENS (Esquema Nacional de Seguridad)** is only mandatory for Spanish public sector and their direct providers — not for private B2B.

**The real requirement for Vocify prospects (pharma, medical devices):**
- ISO 27001 or SOC 2 Type II (documentable, not necessarily certified yet for a PoC)
- GDPR compliance with signed DPA
- Infrastructure documentation showing reliability and security measures
- Cloud provider certifications (ISO 27001, SOC 2 from GCP/AWS)
- Pentest report (can be a lightweight one for PoC stage)

We need the ability to:
- Use **NextBit256** (cheap, local, GDPR-native Spain) for non-regulated prospects and internal workloads
- Switch to **Google Vertex AI** or **AWS Bedrock** (ISO 27001 + SOC 2 certified cloud, fully documented) for enterprise/regulated prospects where infrastructure transparency is required
- Do this **per-environment or per-prospect** without changing application code

### Inibsa recovery note

This deal is recoverable. The rejection was triggered by our response ("no certification at all"), not by an irreparable technical gap. After implementing this refactor and preparing proper infrastructure documentation, we can re-engage Ricardo with: *"Hemos reforzado nuestra infraestructura con deployment en Google Cloud Madrid (ISO 27001, SOC 2) y documentación de seguridad completa. Cuando reactivéis la iniciativa, estamos listos."*

### What the end state looks like

```
LLM_REQUEST → LLMRouter (config-driven)
                ├── OpenRouterProvider   (current default, via OpenRouter API)
                ├── VertexAIProvider     (Google Cloud, europe-southwest1 Madrid, ISO 27001 + SOC 2)
                ├── NextBit256Provider   (Spanish GPU cloud, low cost + GDPR-native Spain)
                └── BedrockProvider      (AWS, eu-south-2 Zaragoza, ISO 27001 + SOC 2 — optional future)
```

---

## 2. WHY THIS MATTERS — THE INIBSA POSTMORTEM

### What happened

1. Inibsa (pharmaceutical, Barcelona) was evaluating Vocify for a PoC
2. Their IT Strategy Manager Roger asked what classification the data center had
3. We said: NextBit256 doesn't have any CPD certification
4. Roger rejected the PoC: *"no poden garantir el servei en quant a rendiment, disponibilitat ni seguretat"*

### Root cause analysis

Roger's real concern was infrastructure reliability, not the Uptime Institute stamp specifically. He used TIER as his reference framework because that's what he knows. His own words prove this was unusual: *"es la primera vegada que ens trobem en aquesta situació, mai em tirat enrere un projecte per aquests temes, ja que les empreses saben com han de fer les coses."* Every other SaaS vendor Inibsa works with presumably passed this check — not because they had TIER (most SaaS companies don't), but because they had documented answers about their infrastructure.

The fatal response was *"no tienen ninguna certificación CPD."* A better response would have been: *"NextBit256 opera con infraestructura Fortinet, uptime >99%, en data centers españoles con cumplimiento GDPR. Si necesitáis documentación adicional, nuestro CTO de infraestructura puede hacer una llamada técnica con vosotros."*

### What we need to be able to document for enterprise prospects

| Question from IT team | Current state | Target state |
|------------------------|---------------|--------------|
| Where are our data stored and processed? | NextBit256 (Spain) + OpenRouter (varies) | Configurable: EU cloud region, documented |
| What security certifications does the infrastructure have? | "None" (NextBit256) | ISO 27001 + SOC 2 via GCP/AWS documentation |
| Are data used for model training? | No (NextBit256) but OpenRouter is opaque | Provider-specific: document opt-out per provider |
| Do you have a DPA? | Not formalized | Standard DPA template, signed |
| What is the uptime SLA? | ">99% but no formal SLA" | Cloud provider SLA documentation |
| Is there a pentest report? | No | Lightweight pentest (can be commissioned) |

### The compliance reality for cloud providers

**Important correction:** Neither GCP, AWS, nor Azure hold Uptime Institute TIER certification. All three explicitly state they do not pursue it. What they DO provide:

| Cloud | Key Certifications |
|-------|-------------------|
| **GCP** | ISO 27001, SOC 1/2/3, ISO 27701, ISO 27017/27018, ISO 22301 |
| **AWS** | ISO 27001, SOC 1/2/3, HIPAA, FedRAMP, PCI DSS |
| **Azure** | ISO 27001, SOC 1/2/3, HIPAA, FedRAMP |

These are the certifications that enterprises actually ask for. TIER is a data center operator certification, not a SaaS requirement.

**For strict TIER requirements (if a prospect literally demands the Uptime Institute certificate):** The only path is Alex Fabregat's offer — NextBit256 deploys a dedicated server in a TIER III/IV certified colocation facility in Spain. ECX Sant Boi (Barcelona, TIER III) and Adam (Barcelona/Madrid, TIER III) are certified options.

---

## 3. HOW THE ARCHITECTURE WORKS

### 3.1 Provider Interface

Every provider implements the same abstract interface. This is the contract:

```python
class BaseLLMProvider(ABC):
    """Every LLM backend must implement this."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        response_format: Optional[dict] = None,
    ) -> str:
        """Send chat completion, return raw string content."""
        ...

    @abstractmethod
    async def chat_json(
        self,
        messages: list[dict],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
    ) -> dict:
        """Chat with JSON response, parse and return dict."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable name for logging/metrics: 'openrouter', 'vertex_ai', etc."""
        ...

    @abstractmethod
    def compliance_info(self) -> dict:
        """Return dict with keys: iso_27001, soc2, gdpr_dpa, data_region, docs_url.
        Used to answer vendor assessment questions instantly."""
        ...
```

The `compliance_info()` method replaces the previous `supports_certification()` and `certification_documentation_url()`. Instead of a boolean for TIER (which we now know is not the standard), it returns the full compliance profile that enterprise IT teams actually ask for.

### 3.2 Router

The `LLMRouter` is the single entry point. It reads `LLM_PROVIDER` from config and instantiates the correct provider. All existing call sites (`ExtractionService`, glossary AI, WhatsApp generation) call `router.chat()` or `router.chat_json()` — same API, different backend.

```python
class LLMRouter:
    def __init__(self, provider_name: Optional[str] = None):
        self._provider = self._resolve_provider(provider_name or settings.LLM_PROVIDER)

    def _resolve_provider(self, name: str) -> BaseLLMProvider:
        providers = {
            "openrouter": OpenRouterProvider,
            "vertex_ai": VertexAIProvider,
            "nextbit": NextBit256Provider,
            "bedrock": BedrockProvider,
        }
        cls = providers.get(name)
        if not cls:
            raise ValueError(f"Unknown LLM provider: {name}")
        return cls()

    async def chat(self, messages, **kwargs):
        return await self._provider.chat(messages, **kwargs)

    async def chat_json(self, messages, **kwargs):
        return await self._provider.chat_json(messages, **kwargs)
    
    def get_active_compliance_info(self) -> dict:
        """Returns compliance profile of the active provider for vendor assessment."""
        return self._provider.compliance_info()
```

### 3.3 Configuration

New environment variables in `.env` / `config.py`:

```bash
# LLM Provider: which backend to use
# Options: openrouter, vertex_ai, nextbit, bedrock
LLM_PROVIDER=openrouter

# --- OpenRouter (current default) ---
OPENROUTER_API_KEY=sk-or-...
EXTRACTION_MODEL=x-ai/grok-4.1-fast

# --- Google Vertex AI ---
# Required when LLM_PROVIDER=vertex_ai
# Runs in europe-southwest1 (Madrid) — data residency in Spain
# GCP provides: ISO 27001, SOC 1/2/3, ISO 27701, standard DPA
GOOGLE_CLOUD_PROJECT=vocify-prod
GOOGLE_CLOUD_LOCATION=europe-southwest1
VERTEX_AI_MODEL=gemini-2.5-flash
# Auth: uses Application Default Credentials (gcloud auth) or service account JSON

# --- NextBit256 ---
# Required when LLM_PROVIDER=nextbit
# Spanish GPU cloud, GDPR-native, no formal ISO/SOC certs
# CEO Alex Fabregat: available for custom deployments including TIER colocation
NEXTBIT_API_KEY=nb-...
NEXTBIT_BASE_URL=https://api.nextbit256.com
NEXTBIT_MODEL=gemini-3.1-flash

# --- AWS Bedrock ---
# Required when LLM_PROVIDER=bedrock
# Runs in eu-south-2 (Zaragoza) — data residency in Spain
# AWS provides: ISO 27001, SOC 1/2/3, HIPAA, standard DPA
AWS_REGION=eu-south-2
BEDROCK_MODEL=anthropic.claude-sonnet-4-20250514-v1:0
```

### 3.4 The Backward Compatibility Layer

The existing `LLMClient` class in `client.py` becomes a thin wrapper around the router for backward compatibility:

```python
class LLMClient:
    """Backward-compatible wrapper. Routes to configured provider via LLMRouter."""

    def __init__(self, api_key=None, model=None):
        self.router = LLMRouter()
        self._override_model = model

    async def chat(self, messages, *, model=None, temperature=0.0, response_format=None):
        return await self.router.chat(
            messages,
            model=model or self._override_model,
            temperature=temperature,
            response_format=response_format,
        )

    async def chat_json(self, messages, *, model=None, temperature=0.0):
        return await self.router.chat_json(
            messages,
            model=model or self._override_model,
            temperature=temperature,
        )
```

This means `ExtractionService` (which does `self.llm = LLMClient()`) continues to work without any code changes. The routing is transparent.

---

## 4. PROVIDER IMPLEMENTATION DETAILS

### 4.1 OpenRouterProvider (current, stays as default)

**What it does:** Wraps the existing OpenRouter API call. This is the current production path.

**Model:** Configurable via `EXTRACTION_MODEL`. Currently `x-ai/grok-4.1-fast`.

**Compliance profile:** OpenRouter routes to various model providers. Infrastructure varies per model — destination is opaque. No SOC 2 or ISO 27001 guarantee at the OpenRouter level. **Use for non-regulated prospects and development only.** Not suitable for enterprise vendor assessments where data processing location must be documented.

**Implementation:** Extract the existing `LLMClient.chat()` logic into `OpenRouterProvider`. It already handles retries, error formatting, and JSON extraction. The `_extract_json()` method moves to a shared utility since all providers need it.

### 4.2 VertexAIProvider (the enterprise-ready path)

**What it does:** Calls Google Vertex AI (Gemini models) via the official `google-cloud-aiplatform` SDK.

**Region:** `europe-southwest1` (Madrid). Data processed and stored in Spain.

**Compliance profile:**
```python
{
    "iso_27001": True,
    "soc2": True,  # SOC 1/2/3
    "iso_27701": True,
    "gdpr_dpa": True,  # Standard DPA included
    "data_region": "europe-southwest1 (Madrid, Spain)",
    "docs_url": "https://cloud.google.com/security/compliance",
    "uptime_sla": "99.99% (Google Cloud SLA)",
    "note": "GCP does NOT hold Uptime Institute TIER certification. It exceeds TIER III standards with its own performance-based approach. ISO 27001 + SOC 2 are the certifications enterprises actually require."
}
```

**Auth:** Uses Google Cloud Application Default Credentials (ADC). In development: `gcloud auth application-default login`. In production (Railway): set `GOOGLE_APPLICATION_CREDENTIALS` to a mounted service account JSON file.

**Dependencies:** Add `google-cloud-aiplatform>=1.60.0` to `requirements.txt`.

**How it works:**
```python
import vertexai
from vertexai.generative_models import GenerativeModel

class VertexAIProvider(BaseLLMProvider):
    def __init__(self):
        vertexai.init(
            project=settings.GOOGLE_CLOUD_PROJECT,
            location=settings.GOOGLE_CLOUD_LOCATION,  # europe-southwest1
        )
        self._model_name = settings.VERTEX_AI_MODEL  # gemini-2.5-flash

    async def chat(self, messages, *, model=None, temperature=0.0, response_format=None):
        model_obj = GenerativeModel(model or self._model_name)
        contents = self._to_gemini_contents(messages)
        config = {"temperature": temperature}
        if response_format and response_format.get("type") == "json_object":
            config["response_mime_type"] = "application/json"
        response = model_obj.generate_content(contents, generation_config=config)
        return response.text

    def _to_gemini_contents(self, messages: list[dict]) -> list:
        """Convert [{'role':'system','content':'...'}, ...] to Gemini Content objects."""
        ...
```

**Key concern:** Gemini's API uses a different message format than OpenAI's. The provider must convert `[{"role": "...", "content": "..."}]` to Gemini `Content` objects. The system prompt must be set via `system_instruction` in the model config, not as a separate message. JSON mode uses `response_mime_type="application/json"` instead of `response_format`.

### 4.3 NextBit256Provider (low cost, GDPR-native Spain)

**What it does:** Calls NextBit256's OpenAI-compatible API. NextBit256 hosts models on their own GPU infrastructure in Spain.

**Model:** `gemini-3.1-flash` (placeholder — actual model TBD).

**Compliance profile:**
```python
{
    "iso_27001": False,
    "soc2": False,
    "gdpr_dpa": True,  # Spanish company, GDPR-native, DPA on request
    "ens": "in_progress",  # ENS certification in progress (per CEO Alex Fabregat)
    "data_region": "Spain (NextBit256 infrastructure)",
    "docs_url": None,  # No public compliance page; documentation on request
    "uptime_sla": ">99% (non-contractual)",
    "note": "NextBit256 does NOT hold Uptime Institute TIER or ISO 27001 certification. For prospects requiring TIER certification, a dedicated server can be deployed in a TIER III/IV colocation facility (ECX Barcelona, Adam Madrid/Barcelona). Contact CEO Alex Fabregat for custom deployments. For non-regulated prospects and internal workloads, the base service is cost-effective and GDPR-compliant out of the box."
}
```

**Implementation:** Very simple — NextBit256 exposes an OpenAI-compatible `/v1/chat/completions` endpoint. This is essentially the same HTTP call as OpenRouter but pointed at NextBit256's API.

**TIER colocation option:** For prospects that strictly require Uptime Institute TIER certification (rare but possible — Inibsa was one), Alex can deploy a dedicated server in a TIER-certified facility. This increases cost but delivers literal TIER III/IV certification. Available facilities include ECX Sant Boi (Barcelona, TIER III) and Adam (Barcelona/Madrid, TIER III). This is the only path to actual Uptime Institute TIER certification, since no hyperscale cloud provides it.

### 4.4 BedrockProvider (future, optional)

**What it does:** Calls AWS Bedrock (Claude, Llama, etc.) in `eu-south-2` (Zaragoza).

**Why include it:** If Gemini quality isn't sufficient for extraction, Claude on Bedrock is the fallback. Both GCP and AWS have equivalent compliance profiles (ISO 27001, SOC 2). Implement as a stretch goal — not needed for the initial refactor.

**Compliance profile:** Equivalent to Vertex AI — ISO 27001, SOC 1/2/3, HIPAA-eligible, standard DPA. AWS also does not hold Uptime Institute TIER. See: https://aws.amazon.com/compliance/uptimeinstitute/

---

## 5. PROJECT STRUCTURE (what to create)

```
backend/app/services/llm/
├── __init__.py              # Exports LLMClient, LLMRouter, get_compliance_info
├── client.py                # LLMClient (backward-compatible wrapper, existing code cleaned up)
├── router.py                # LLMRouter (new — provider selection logic)
├── base.py                  # BaseLLMProvider abstract class (new)
├── providers/
│   ├── __init__.py
│   ├── openrouter.py        # OpenRouterProvider (extracted from current client.py)
│   ├── vertex_ai.py         # VertexAIProvider (new — Gemini via Google Cloud)
│   └── nextbit.py           # NextBit256Provider (new — OpenAI-compatible endpoint)
├── shared.py                # _extract_json() and other shared utilities (moved from client.py)
└── compliance.py            # Compliance profiles and vendor assessment helpers (new, was certs.py)
```

### File responsibilities

| File | Purpose |
|------|---------|
| `base.py` | `BaseLLMProvider` ABC. Defines the contract: `chat()`, `chat_json()`, `provider_name`, `compliance_info()`. |
| `router.py` | `LLMRouter`. Reads `settings.LLM_PROVIDER`, instantiates provider, delegates. Has `get_active_compliance_info()` for vendor assessments. |
| `client.py` | `LLMClient`. Backward-compatible wrapper. Keeps the same constructor signature. Routes through `LLMRouter`. Zero changes in callers. |
| `shared.py` | `_extract_json()` and `_parse_amount()`. Moved from current `client.py` since all providers need JSON parsing from LLM output. |
| `compliance.py` | Per-provider compliance profiles and `get_compliance_info(provider_name)`. Returns the full profile that enterprise IT teams ask for in vendor assessments. |
| `providers/openrouter.py` | `OpenRouterProvider`. Extracted from current `LLMClient.chat()`. Same logic, same error handling, in a provider class. |
| `providers/vertex_ai.py` | `VertexAIProvider`. New. Uses `google-cloud-aiplatform`. Converts OpenAI format to Gemini format. |
| `providers/nextbit.py` | `NextBit256Provider`. New. HTTP POST to NextBit256 API with OpenAI-compatible payload. |

---

## 6. WHAT NEEDS TO CHANGE IN EXISTING FILES

### `backend/app/config.py`
Add these settings:
```python
# LLM Provider routing
LLM_PROVIDER: str = "openrouter"  # openrouter | vertex_ai | nextbit | bedrock

# Vertex AI (enterprise path: ISO 27001 + SOC 2, Madrid region)
GOOGLE_CLOUD_PROJECT: Optional[str] = None
GOOGLE_CLOUD_LOCATION: str = "europe-southwest1"
VERTEX_AI_MODEL: str = "gemini-2.5-flash"

# NextBit256 (low cost, GDPR-native Spain)
NEXTBIT_API_KEY: Optional[str] = None
NEXTBIT_BASE_URL: str = "https://api.nextbit256.com"
NEXTBIT_MODEL: str = "gemini-3.1-flash"

# Bedrock (optional future: ISO 27001 + SOC 2, Zaragoza region)
AWS_REGION: str = "eu-south-2"
BEDROCK_MODEL: str = "anthropic.claude-sonnet-4-20250514-v1:0"
```

`OPENROUTER_API_KEY` should become `Optional[str] = None` — it's only required when `LLM_PROVIDER=openrouter`. Validate at provider init time, not at settings load time.

### `backend/requirements.txt`
Add:
```
google-cloud-aiplatform>=1.60.0
```
Remove none. The `httpx` dependency stays (needed by OpenRouter and NextBit providers).

### `backend/app/services/extraction.py`
Zero changes needed. `ExtractionService.__init__` already does `self.llm = LLMClient()`. The `LLMClient` wrapper handles routing transparently.

### `backend/app/services/llm/__init__.py`
Update exports:
```python
from .client import LLMClient
from .router import LLMRouter
from .compliance import get_compliance_info

__all__ = ["LLMClient", "LLMRouter", "get_compliance_info"]
```

---

## 7. THE ROUTING CONFIGURATION — HOW IT WORKS

The provider is selected via a single env var:

```bash
# .env
LLM_PROVIDER=vertex_ai
```

This means:
- **Development (local):** `LLM_PROVIDER=openrouter` — cheapest, easiest
- **Production (non-regulated prospects):** `LLM_PROVIDER=nextbit` — low cost, GDPR-native Spain
- **Production (enterprise/regulated prospects):** `LLM_PROVIDER=vertex_ai` — ISO 27001 + SOC 2 cloud, Madrid region, documentation ready for vendor assessment
- **Production (strict TIER requirement):** `LLM_PROVIDER=nextbit` with colocation deployment — the only path to literal Uptime Institute TIER III/IV certification (via Alex's offer)

Per-prospect routing (different providers per customer) would need a `provider` column in the organization settings in Supabase. Not needed for v1 — environment-level routing is sufficient.

---

## 8. REFERENCE DOCUMENTS — WHAT ENTERPRISE IT TEAMS ACTUALLY ASK FOR

These are the frameworks and documentation that matter for Inibsa-style vendor assessments. Based on real market data, not assumptions.

### ISO 27001 — Information Security Management
- **What it is:** International standard for Information Security Management System (ISMS)
- **Who has it:** GCP, AWS, Azure (all certified)
- **Relevance:** This is the #1 certification enterprise IT teams ask for in Europe
- **GCP link:** https://cloud.google.com/security/compliance/iso-27001

### SOC 2 Type II — Service Organization Controls
- **What it is:** Audited controls for security, availability, processing integrity, confidentiality, privacy
- **Who has it:** GCP, AWS, Azure (all certified)
- **Relevance:** Market-driven expectation for B2B SaaS. "Without SOC 2, earning the trust of larger customers is difficult." — Scrut.io, 2025
- **AWS link:** https://aws.amazon.com/compliance/soc-faqs/

### GDPR / Data Processing Agreement (DPA)
- **What it is:** EU regulation for personal data protection. DPA is the contract between controller and processor
- **Who has it:** GCP and AWS include standard DPA in terms. NextBit256 (Spanish company) provides on request
- **Relevance:** Mandatory in EU. Non-negotiable for any prospect

### Uptime Institute TIER (NOT a SaaS requirement)
- **What it is:** Physical data center certification for power redundancy and cooling (designed for colocation operators, not cloud SaaS)
- **Who has it:** Traditional colocation data centers — ECX Sant Boi (Barcelona, TIER III), Adam (Barcelona/Madrid, TIER III), BBVA (Madrid, TIER IV). Zoho ($1B+ SaaS) does not. Salesforce does not. No major SaaS company has it.
- **Relevance:** Only relevant if a prospect explicitly demands the Uptime Institute certificate (rare — Inibsa was an exception). In that case, the colocation option via Alex is the path. Otherwise, cloud provider ISO 27001 + SOC 2 documentation is the standard answer.
- **GCP statement:** "Google focuses on scalability of performance rather than the Tier Classification System" — https://cloud.google.com/security/compliance/uptime-institue-tiers
- **AWS statement:** "AWS has chosen not to have a certified Uptime Institute-based tiering level" — https://aws.amazon.com/compliance/uptimeinstitute/

### ENS (Esquema Nacional de Seguridad)
- **What it is:** Spanish government security framework (Real Decreto 311/2022)
- **Who needs it:** Spanish public administrations and private companies providing services to them
- **Relevance:** Not mandatory for B2B private sector. NextBit256 is pursuing it. Good to have but not a blocker

### EU AI Act
- **What it is:** EU regulation for AI systems, fully in effect 2025
- **Relevance:** Vocify processes voice data with AI — must comply. Fines up to €35M or 7% of global revenue
- **Action:** Document that Vocify does not use customer data for model training, has data retention policies, and provides transparency about AI processing

### Pentest Report
- **What it is:** Independent security assessment of the application
- **Relevance:** Frequently requested in vendor security questionnaires. Can be commissioned for ~€3-5K

---

## 9. IMPLEMENTATION ORDER (what to build first)

1. **Create `base.py`** — the abstract provider interface with `compliance_info()`
2. **Create `shared.py`** — move `_extract_json()` from client.py, add shared utilities
3. **Create `providers/openrouter.py`** — extract current OpenRouter logic into a provider class
4. **Create `router.py`** — the `LLMRouter` with provider selection
5. **Refactor `client.py`** — `LLMClient` becomes a thin backward-compatible wrapper
6. **Create `providers/vertex_ai.py`** — new Gemini provider with message format conversion
7. **Create `providers/nextbit.py`** — new NextBit256 provider (simple, OpenAI-compatible)
8. **Create `compliance.py`** — compliance profiles for each provider (replaces old `certs.py`)
9. **Update `config.py`** — add new env vars, make OPENROUTER_API_KEY optional
10. **Update `__init__.py`** — new exports
11. **Update `requirements.txt`** — add `google-cloud-aiplatform`
12. **Test** — run extraction with each provider, verify JSON parsing works identically

---

## 10. SUCCESS CRITERIA

After implementation, the following must be true:

1. **No code changes in `extraction.py`** — `LLMClient()` works identically
2. **Switching providers is one env var** — `LLM_PROVIDER=vertex_ai` and restart
3. **JSON extraction works identically** — shared `_extract_json()` across all providers
4. **Compliance info is queryable** — calling `get_compliance_info("vertex_ai")` returns `{iso_27001: true, soc2: true, gdpr_dpa: true, data_region: "europe-southwest1 (Madrid)", docs_url: "..."}`
5. **Existing tests pass** — backward compatibility is non-negotiable
6. **Logging includes provider name** — every LLM request log shows which provider handled it
7. **Vendor assessment ready** — the `compliance.py` module can generate a one-page infrastructure document for any active provider
8. **Correct framing** — the code and documentation correctly state that cloud providers offer ISO 27001 + SOC 2 (not TIER), and TIER colocation is available as a custom option via NextBit256

---

## 11. OPEN QUESTIONS FOR THE AGENT TO ANALYZE

These are decisions the implementing agent should evaluate and propose solutions for:

### Q1: Message format conversion
Gemini uses a different message format than OpenAI. How should we handle system messages (which Gemini expects as `system_instruction` in model config, not as a separate `Content`)? Should we build a general-purpose converter in `shared.py` or keep it provider-specific?

### Q2: JSON mode across providers
- **OpenRouter/OpenAI:** `response_format: {"type": "json_object"}`
- **Gemini:** `response_mime_type: "application/json"` in generation config
- **NextBit256:** OpenAI-compatible, so `response_format` works
- Should `chat_json()` handle this internally per provider, or should the router normalize it?

### Q3: Error handling uniformity
OpenRouter returns HTTP error codes with JSON messages. Gemini throws Python exceptions. NextBit256 returns OpenAI-compatible error JSON. How should errors be normalized so `ExtractionService` gets consistent exceptions regardless of provider?

### Q4: Should we abstract STT too?
Speechmatics and Google Cloud STT (Chirp) have different compliance profiles. Should this refactor include an STT abstraction, or is that a separate project? (Decision: separate project — not in scope for v1.)

### Q5: Per-request provider override
Should `LLMClient.chat(provider=...)` accept a `provider` kwarg to override the environment setting for a single request? This would allow A/B testing. If yes, how does it interact with the router?

### Q6: What happens to `EXTRACTION_MODEL`?
Currently a single global string. With multiple providers, each has its own model config key (`VERTEX_AI_MODEL`, `NEXTBIT_MODEL`). The `LLMClient.__init__(model=...)` override should still work — the explicit model takes priority over provider defaults.

### Q7: OpenRouter data transparency
NextBit256 sometimes routes through OpenRouter. If so, data may leave NextBit256's infrastructure and lose GDPR/DPA guarantees. The agent should analyze whether the NextBit256 provider needs to warn or block OpenRouter-routed requests when compliance mode is active.

---

## 12. SUMMARY FOR THE AGENT

**Goal:** Build a multi-provider LLM routing layer that lets Vocify switch between OpenRouter, Google Vertex AI, and NextBit256 with one environment variable. No code changes in callers.

**Why:** Enterprise prospects (pharma, medical devices) require documented infrastructure for vendor assessment. Our current provider (NextBit256) lacks formal certifications, and our response to Inibsa's inquiry ("no certification") was the real reason the PoC was killed — not a missing TIER certificate specifically. Most SaaS companies don't have TIER. They document their cloud provider's ISO 27001 and SOC 2 certifications instead.

**Compliance reality (evidence-based):**
- ISO 27001 + SOC 2 are the standard enterprise requirements for SaaS — not TIER
- GCP, AWS, and Azure provide these; they do not pursue Uptime Institute TIER
- Zoho ($1B+ SaaS) lists ISO/SOC, not TIER
- ENS is only mandatory for Spanish public sector
- For strict TIER requirements (rare), the colocation path via Alex is available

**Non-goals:**
- NOT building an STT abstraction (separate task)
- NOT migrating off OpenRouter entirely (stays as default for non-regulated)
- NOT implementing Bedrock in v1 (stretch goal)

**Key constraint:** `ExtractionService` must continue to work with `self.llm = LLMClient()` — zero changes to extraction logic.