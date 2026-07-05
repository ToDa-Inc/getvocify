# Vocify LLM Service Layer — Implementation Plan

> **Status:** Approved for implementation (scope locked, no code changed yet)
> **Source brief:** `docs/llm-service-implementation-brief.md`
> **This document:** Corrects the brief against the actual codebase and current Google SDK state, and gives a concrete, ordered implementation plan — with a focused deep-dive on the Vertex AI provider since that's the immediate compliance priority.

## Locked decisions (2026-07-04)

- **v1 scope = OpenRouter + Vertex AI only.** `NextBit256Provider` and `BedrockProvider` are **out** for this pass — no `providers/nextbit.py`, no NextBit env vars, no Bedrock. The router/base interface is still built generically so either can be added later without touching `LLMRouter`, `LLMClient`, or any caller.
- **`glossary_ai.py` migration is in scope.** It moves onto `LLMClient`/`LLMRouter` in this pass so provider routing is universal (see §1, point 2).
- **GCP project: `vocify-prod`.** Use this as `GOOGLE_CLOUD_PROJECT` directly, no placeholder.
- **Railway credentials: plain env var.** Store the service account JSON contents directly in a Railway env var (e.g. `GOOGLE_APPLICATION_CREDENTIALS_JSON`); a small startup step writes it to a temp file and sets `GOOGLE_APPLICATION_CREDENTIALS` to that path before `genai.Client()` is constructed. See §2.3 for the exact mechanism.

---

## 1. Verdict

The brief's business case and compliance research (ISO 27001/SOC 2 > TIER for SaaS) is sound and doesn't need rework. The *implementation* plan needs four corrections before it's safe to build against:

1. **The brief's Vertex AI SDK choice is already deprecated/removed.** Must use `google-genai`, not `vertexai.generative_models`.
2. **`glossary_ai.py` bypasses the LLM client entirely today.** It has its own duplicated OpenRouter HTTP call. Left unfixed, switching `LLM_PROVIDER=vertex_ai` would still leak glossary data to OpenRouter — directly undermining the compliance goal this whole project exists for.
3. **`config.py`'s `OPENROUTER_API_KEY` validator will crash on `None`.** Making the key optional (as the brief requires) needs a validator fix, not just a type change.
4. **There is no existing test suite** (`backend/tests/` doesn't exist). "Existing tests pass" isn't a meaningful success criterion — it's replaced below with a concrete manual/scripted verification step.

---

## 2. Vertex AI deep-dive (the part that matters most right now)

### 2.1 Which SDK

| | Brief's proposal | Correct as of today (2026-07-04) |
|---|---|---|
| Package | `google-cloud-aiplatform>=1.60.0` | `google-genai` (current: 1.74.0+; check latest) |
| Import | `import vertexai; from vertexai.generative_models import GenerativeModel` | `from google import genai; from google.genai import types` |
| Status | `vertexai.generative_models` deprecated 2025-06-24, **removed 2026-06-24** (already past) | Actively maintained, GA, unified SDK for both Gemini Developer API and Vertex AI |

**Why this matters:** building the compliance-critical enterprise path on a removed module would mean it breaks the moment `pip install` resolves a current version, or silently runs on a pinned old version that Google no longer patches — the opposite of the "documented, reliable infrastructure" story this project is trying to sell to Inibsa-like prospects.

### 2.2 Client shape

```python
from google import genai
from google.genai import types

client = genai.Client(
    vertexai=True,
    project=settings.GOOGLE_CLOUD_PROJECT,
    location=settings.GOOGLE_CLOUD_LOCATION,   # europe-southwest1
)

response = await client.aio.models.generate_content(
    model=model or self._model_name,           # e.g. "gemini-2.5-flash"
    contents=self._to_gemini_contents(messages),
    config=types.GenerateContentConfig(
        system_instruction=system_text,          # extracted from role="system" messages
        temperature=temperature,
        response_mime_type="application/json" if json_mode else None,
    ),
)
return response.text
```

This is genuinely async (`client.aio.*`), not a sync call wrapped in a thread — a small implementation simplification versus what the brief implied.

### 2.3 Auth (no code, ops-only)

ADC resolution order (SDK handles this automatically once `vertexai=True`):
1. Explicit `credentials=` param (not needed for us)
2. `GOOGLE_APPLICATION_CREDENTIALS` env var → path to a service account JSON key
3. `gcloud auth application-default login` (local dev only)
4. Attached service account (Cloud Run / GCE — not our deployment target)

**Local dev:** `gcloud auth application-default login` once, no key file needed.

**Production (Railway) — decided:** Railway has no native GCP workload identity, so we use a plain env var. Set `GOOGLE_APPLICATION_CREDENTIALS_JSON` in Railway to the full service account JSON contents (single-line, escaped). At app startup (in `config.py` or a small `main.py` bootstrap step, before `Settings()`/any provider is constructed), if that env var is present:

```python
import json, tempfile, os

creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
if creds_json and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        f.write(creds_json)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
```

This keeps `VertexAIProvider` itself credential-agnostic — it just relies on ADC via `GOOGLE_APPLICATION_CREDENTIALS`, which is set either by this bootstrap step (Railway) or by `gcloud auth application-default login` (local). No Vertex-specific code needs to know about Railway at all.

### 2.4 Region / model availability (verified against current GCP data)

- `europe-southwest1` (Madrid) **does** support `gemini-2.5-flash` and `gemini-2.0-flash` as regional (single-region) endpoints — this is what makes the "data stays in Spain" compliance claim actually true.
- `gemini-3.x` models are currently GA only via the **EU multi-region** endpoint (routing stays inside EU geography, still covered by Vertex's DPA, but *not* pinned to Madrid specifically) — single-region `europe-southwest1`/`europe-west3`/`europe-west4` support for 3.x is not yet confirmed.
- **Recommendation:** keep `VERTEX_AI_MODEL=gemini-2.5-flash` as the default (matches the brief), and treat any future move to `gemini-3.x` as a deliberate compliance-review decision (multi-region EU vs. single-region Madrid), not a routine model bump.

### 2.5 Message format conversion (Q1 from the brief)

Gemini has no `system` role in `contents` — system prompts go in `GenerateContentConfig.system_instruction`. Needed conversion logic (goes in `shared.py`, reusable by any future Gemini-family provider):

```python
def to_gemini_contents(messages: list[dict]) -> tuple[Optional[str], list]:
    """Split messages into (system_instruction, contents) for Gemini."""
    system_parts = [m["content"] for m in messages if m.get("role") == "system"]
    system_instruction = "\n\n".join(system_parts) or None
    contents = [
        {"role": "user" if m["role"] != "assistant" else "model", "parts": [{"text": m["content"]}]}
        for m in messages if m.get("role") != "system"
    ]
    return system_instruction, contents
```

### 2.6 JSON mode

`response_mime_type="application/json"` in `GenerateContentConfig` — no `response_schema` needed initially (schema-less JSON mode is enough to match current `chat_json()` behavior, since `ExtractionService` supplies its own prompt-level schema description). The shared `_extract_json()` fallback parser stays as a safety net in case Gemini wraps output unexpectedly.

### 2.7 Error handling

`google-genai` raises Python exceptions (`google.genai.errors.APIError` and subclasses) rather than returning OpenAI-style HTTP+JSON errors. The provider's `chat()` should catch these and re-raise as the same `Exception("LLM request failed: ...")` shape the rest of the codebase already expects from `LLMClient`, so `ExtractionService`/`IntentService`/`TaskMergeService` don't need any error-handling changes.

### 2.8 Complexity & effort estimate

| Component | Effort | Why |
|---|---|---|
| `VertexAIProvider` class itself | **Small** (~1 day) | SDK is clean; async-native; message conversion is ~20 lines |
| GCP project setup on `vocify-prod` (enable Vertex AI API, IAM role, service account) | **Small** (~1-2 hrs, one-time, ops not code) | Standard GCP setup |
| Railway env-var credential bootstrap | **Small** (~1-2 hrs) | Simple JSON-to-tempfile step, decided in §2.3 — no ambiguity left to resolve |
| Router/base/shared scaffolding (needed regardless of Vertex) | **Medium** (~1-2 days) | New files, but mostly mechanical extraction of existing OpenRouter logic |
| `glossary_ai.py` migration to router | **Small** (~half day) | Two call sites, logic mostly transferable |
| Verification (manual + a small parity script) | **Small-Medium** (~half day) | No existing tests to build on |
| **Total for Vertex AI usable end-to-end** | **~3 days** | Assuming no GCP org-policy surprises (e.g. org restricting Vertex AI API activation, which would add IT/approval delay outside engineering's control) |

**Bottom line:** the Vertex AI provider itself is low complexity — the SDK is well-designed for this use case. The real effort is in the surrounding refactor (router/base/shared) and closing the `glossary_ai.py` gap, both of which are needed once, regardless of which second provider you pick.

### 2.9 Risks specific to Vertex AI

- **Railway ↔ GCP credential delivery** is decided (§2.3) but should still be validated with a real deploy, not just local ADC, before calling this production-ready.
- **Cold-start GCP project setup on `vocify-prod`** (billing account, API enablement, quota) can take longer than the coding itself if Vertex AI hasn't been enabled on that project before — recommend doing this in parallel with Phase 1 coding, not after.
- **Model pinning discipline**: someone bumping `VERTEX_AI_MODEL` to a shiny `gemini-3.x` model later could silently move data out of strict Madrid single-region pinning into EU multi-region. Worth a code comment / compliance.py note, not just documentation.

---

## 3. Full corrected file plan (v1 scope: OpenRouter + Vertex AI)

```
backend/app/services/llm/
├── __init__.py              # exports LLMClient, LLMRouter, get_compliance_info
├── client.py                # LLMClient — thin backward-compatible wrapper (refactored)
├── router.py                # LLMRouter — provider selection + get_active_compliance_info()
├── base.py                  # BaseLLMProvider ABC + LLMProviderError
├── providers/
│   ├── __init__.py
│   ├── openrouter.py        # extracted from current client.py, unchanged behavior
│   └── vertex_ai.py         # google-genai based, per §2 above
├── shared.py                 # _extract_json, _parse_amount, to_gemini_contents
└── compliance.py             # per-provider compliance profiles + get_compliance_info()
```

`providers/nextbit.py` and a Bedrock provider are **not** built in this pass (see locked decisions above). `LLMRouter._resolve_provider` should still raise a clear `ValueError` for `"nextbit"`/`"bedrock"` rather than silently doing nothing, so it's an obvious "not implemented yet" rather than a confusing failure if someone sets the env var early.

Files touched outside `llm/`:
- `backend/app/config.py` — new env vars (`LLM_PROVIDER`, `GOOGLE_CLOUD_PROJECT=vocify-prod`, `GOOGLE_CLOUD_LOCATION`, `VERTEX_AI_MODEL`); `OPENROUTER_API_KEY` → `Optional[str]`; validator fixed for `None`; Railway credential bootstrap (§2.3).
- `backend/requirements.txt` — add `google-genai>=1.74.0` (NOT `google-cloud-aiplatform`).
- `backend/app/metrics.py` — add `provider` label to the `llm_requests` Counter.
- `backend/app/services/glossary_ai.py` — replace both direct `httpx`/OpenRouter calls with `LLMClient`.
- `backend/app/api/health.py` — report active `LLM_PROVIDER` instead of a hardcoded OpenRouter key field.

---

## 4. Implementation order

**Phase 0 — fix what's broken today (blocking prerequisite)**
1. `config.py`: `OPENROUTER_API_KEY: Optional[str] = None` + validator handles `None`.

**Phase 1 — scaffolding**
3. `base.py` — `BaseLLMProvider` ABC (`chat`, `chat_json`, `provider_name`, `compliance_info`) + `LLMProviderError`.
4. `shared.py` — move `_extract_json`/`_parse_amount`, add `to_gemini_contents`.
5. `compliance.py` — static profiles per provider (content from brief §4, corrected where needed) + `get_compliance_info(name)`.

**Phase 2 — providers**
6. `providers/openrouter.py` — extract current `client.py` logic verbatim (retries, logging, metrics with `provider` label).
7. `providers/vertex_ai.py` — per §2 above, using `google-genai`.
(NextBit and Bedrock: not built in v1 — see locked decisions.)

**Phase 3 — router & backward-compat wrapper**
8. `router.py` — `LLMRouter._resolve_provider` (raises clearly for `nextbit`/`bedrock` as not-yet-implemented), `get_active_compliance_info()`, optional per-call `provider=` override.
9. `client.py` — `LLMClient` becomes thin wrapper delegating to `LLMRouter`.
10. `__init__.py` — updated exports.

**Phase 4 — config & infra**
11. `config.py` — `LLM_PROVIDER`, `GOOGLE_CLOUD_PROJECT=vocify-prod`, `GOOGLE_CLOUD_LOCATION=europe-southwest1`, `VERTEX_AI_MODEL=gemini-2.5-flash`, Railway credential bootstrap (§2.3).
12. `requirements.txt` — add `google-genai`.
13. `metrics.py` — `provider` label on `llm_requests`.
14. `health.py` — reflect active provider.
15. **GCP setup (parallel, ops track):** confirm Vertex AI API enabled on `vocify-prod`, create service account with `roles/aiplatform.user`, generate its JSON key, set `GOOGLE_APPLICATION_CREDENTIALS_JSON` in Railway.

**Phase 5 — migrate `glossary_ai.py`**
16. Replace both direct OpenRouter calls with `LLMClient()` + `chat_json()`/`chat()`, preserving bulk-batch behavior and fallback list parsing.

**Phase 6 — verification**
17. Small parity script: run `chat_json()` with a fixed prompt against each configured provider, assert shape-compatible output. This is the actual regression guard, since there's no prior test coverage.
18. Manual end-to-end test with `LLM_PROVIDER=vertex_ai` against `vocify-prod` (ADC locally, then a real Railway deploy with the env-var credential path) before calling this "vendor-assessment ready."

---

## 5. Remaining open item

Everything else is decided. The one thing that still needs a human action (not an engineering decision) before Phase 4 step 15 can complete: someone with access to the `vocify-prod` GCP project needs to enable the Vertex AI API (if not already), create the service account, and generate its JSON key so it can be pasted into Railway as `GOOGLE_APPLICATION_CREDENTIALS_JSON`.
