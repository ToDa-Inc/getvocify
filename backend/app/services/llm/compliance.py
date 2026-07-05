"""Per-provider compliance profiles for vendor assessment."""

from typing import Any

_COMPLIANCE_PROFILES: dict[str, dict[str, Any]] = {
    "openrouter": {
        "iso_27001": False,
        "soc2": False,
        "gdpr_dpa": False,
        "data_region": "Varies per routed model (opaque)",
        "docs_url": "https://openrouter.ai/docs",
        "uptime_sla": None,
        "note": (
            "OpenRouter routes to various model providers. Infrastructure varies per model. "
            "Use for development and non-regulated workloads only."
        ),
    },
    "vertex_ai": {
        "iso_27001": True,
        "soc2": True,
        "iso_27701": True,
        "gdpr_dpa": True,
        "data_region": "europe-southwest1 (Madrid, Spain)",
        "docs_url": "https://cloud.google.com/security/compliance",
        "uptime_sla": "99.99% (Google Cloud SLA)",
        "note": (
            "GCP does NOT hold Uptime Institute TIER certification. "
            "ISO 27001 + SOC 2 are the certifications enterprises typically require. "
            "Keep VERTEX_AI_MODEL on gemini-2.5-flash for strict Madrid single-region pinning."
        ),
    },
}


def get_compliance_info(provider_name: str) -> dict[str, Any]:
    """Return compliance profile for a provider (or empty dict if unknown)."""
    profile = _COMPLIANCE_PROFILES.get(provider_name)
    if profile is None:
        return {"provider": provider_name, "error": "Unknown provider"}
    return {"provider": provider_name, **profile}
