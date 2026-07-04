"""
HubSpot CRM API requires deal property names to be lowercase.
LLM / Salesforce-style extractions often use Name, Amount, Description — normalize here.
"""

from __future__ import annotations

# Salesforce Opportunity (and common LLM) field names → HubSpot deal internal names
_SALESFORCE_TO_HUBSPOT_DEAL: dict[str, str] = {
    "name": "dealname",
    "Name": "dealname",
    "deal_name": "dealname",
    "Deal_Name": "dealname",
    "Amount": "amount",
    "Description": "description",
    "CloseDate": "closedate",
    "StageName": "dealstage",
    "Pipeline": "pipeline",
}


def normalize_hubspot_deal_property_key(key: str) -> str:
    """
    Map aliases to canonical HubSpot deal property names.
    Unknown keys are lowercased to satisfy HubSpot validation.
    """
    if not key or not isinstance(key, str):
        return key
    k = key.strip()
    if k in _SALESFORCE_TO_HUBSPOT_DEAL:
        return _SALESFORCE_TO_HUBSPOT_DEAL[k]
    return k.lower()


def normalize_hubspot_allowed_deal_fields(fields: list[str]) -> list[str]:
    """
    Normalize crm_configurations.allowed_deal_fields for HubSpot sync/preview.
    Fixes rows where Salesforce-style names were stored while CRM is HubSpot.
    """
    seen: set[str] = set()
    out: list[str] = []
    for f in fields:
        n = normalize_hubspot_deal_property_key(f)
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out
