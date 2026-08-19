"""
Deal operations service for HubSpot.

Handles creating, updating, and finding deals with proper
field mapping from MemoExtraction to HubSpot properties.
Includes pipeline stage resolution.
Includes schema-driven enum validation gate (INVALID_OPTION prevention).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .client import HubSpotClient
from .exceptions import HubSpotError
from .types import (
    HubSpotDeal,
    CreateObjectRequest,
    UpdateObjectRequest,
    AssociationSpec,
    AssociationTo,
    AssociationTypeSpec,
    PropertyOption,
)
from .search import HubSpotSearchService
from .schema import HubSpotSchemaService
from .deal_field_names import normalize_hubspot_deal_property_key
from .note_format import first_bullet_plaintext, summary_looks_markdown
from app.models.memo import MemoExtraction

# HubSpot system-managed deal properties (read-only; cannot be set via API)
HUBSPOT_READ_ONLY_DEAL_PROPERTIES = frozenset({
    "hs_closed_amount", "hs_notes_next_activity", "hs_next_step",
    "hs_lastmodifieddate", "hs_createdate", "hs_object_id",
    "hs_analytics_source", "hs_analytics_source_data_1", "hs_analytics_source_data_2",
    "hs_is_closed", "hs_is_closed_won", "hs_date_entered_closedwon", "hs_date_entered_appointmentscheduled",
    "hs_num_associated_contacts", "hs_num_child_companies", "hs_num_child_deals",
    "hs_merged_object_ids", "hs_analytics_source_data_1", "hs_analytics_source_data_2",
})

# Deal properties this function sets via dedicated typed logic below (amount as
# number, closedate as timestamp, competitors as single enum, etc.) - excluded from
# the generic raw_extraction loop purely to avoid double-processing with a different
# type/shape, not a guess about which extraction keys are "real" CRM fields.
_CORE_FIELDS_HANDLED_SEPARATELY = frozenset({
    "dealname", "amount", "closedate", "description", "competitors", "dealstage",
})

# deal_currency_code: HubSpot validates against the portal's configured currencies;
# sending a raw LLM-guessed code (e.g. "EUR") can fail on portals that don't have it
# enabled. Amount already uses the portal's default currency, so this is never useful
# to send - not a guess about schema, a known-bad property for this integration.
_ALWAYS_EXCLUDED_PROPERTIES = frozenset({"deal_currency_code"})

logger = logging.getLogger(__name__)


def _parse_enum_tokens(value: Any) -> list[str]:
    """Parse value into list of tokens (handles list, comma/semicolon-separated string)."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    s = str(value).strip()
    if not s:
        return []
    # Split on comma or semicolon (common LLM/merge output formats)
    return [t.strip() for t in s.replace(";", ",").split(",") if t.strip()]


def _resolve_token_to_option_value(token: str, options: list[PropertyOption]) -> Optional[str]:
    """Map token (label or value) to canonical HubSpot option value. Case-insensitive."""
    if not token or not options:
        return None
    tok = token.strip().lower()
    for opt in options:
        if opt.hidden:
            continue
        if (opt.value or "").lower() == tok:
            return opt.value
        if (opt.label or "").lower() == tok:
            return opt.value
    return None


def _is_empty_raw_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, str)) and len(value) == 0:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _coerce_scalar_property_value(value: Any) -> Any:
    """HubSpot deal properties are scalars; LLM output may use string[]."""
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if v is not None and str(v).strip()]
        if not parts:
            return None
        return ";".join(parts) if len(parts) > 1 else parts[0]
    if isinstance(value, dict):
        return None
    return value



# Properties that are always safe to send even though they aren't listed in
# /crm/v3/properties/deals (association/system fields set via dedicated params).
_NON_SCHEMA_ALLOWED_PROPERTIES = frozenset({"pipeline", "hubspot_owner_id"})


async def _sanitize_enum_properties(
    schema_service: HubSpotSchemaService,
    properties: dict[str, Any],
) -> dict[str, Any]:
    """
    Schema-driven validation gate (allowlist, not denylist).

    This is the single safety net before any property reaches the HubSpot API:
    - Drops any key that isn't an actual property in the portal's deal schema
      (prevents PROPERTY_DOESNT_EXIST 400s from aborting the whole sync, no matter
      what new field name a future extraction/prompt change introduces).
    - Drops read-only properties (schema-driven, in addition to the static list).
    - Validates enum values against allowed options, formats multi-select as
      semicolon-separated, drops invalid tokens.
    - Non-enum, schema-known properties pass through coerced to scalars.

    If the schema fetch itself fails, we fail open (pass properties through) rather
    than blocking the whole sync on a transient schema-API hiccup.
    """
    if not properties:
        return properties

    try:
        schema = await schema_service.get_deal_schema()
        prop_map = {p.name: p for p in schema.properties}
    except Exception as e:
        logger.warning("Schema fetch failed, skipping property validation: %s", e)
        return properties

    sanitized: dict[str, Any] = {}
    for key, value in properties.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if key in _ALWAYS_EXCLUDED_PROPERTIES:
            # Enforced here too (not just in the raw_extraction loop) since this
            # function is the last stop before HubSpot for every property, from
            # every code path - it shouldn't rely on callers upstream having
            # already filtered known-bad properties out.
            continue

        prop = prop_map.get(key)
        if not prop:
            if key in _NON_SCHEMA_ALLOWED_PROPERTIES:
                sanitized[key] = value
            else:
                logger.info(
                    "Dropping property not present in HubSpot deal schema: %s",
                    key,
                    extra={"hubspot_dropped_property": key},
                )
            continue
        if prop.readOnlyValue:
            continue

        if prop.type not in ("enumeration", "checkbox", "radio", "select") or not prop.options:
            coerced = _coerce_scalar_property_value(value)
            if coerced is not None and not (isinstance(coerced, str) and not coerced.strip()):
                sanitized[key] = coerced
            continue

        tokens = _parse_enum_tokens(value)
        is_multi = prop.fieldType == "checkbox"
        resolved: list[str] = []
        for t in tokens:
            canonical = _resolve_token_to_option_value(t, prop.options)
            if canonical and canonical not in resolved:
                resolved.append(canonical)

        if not resolved:
            continue  # Drop invalid enum value (don't send to HubSpot)
        if is_multi:
            sanitized[key] = ";".join(resolved)
        else:
            sanitized[key] = resolved[0]

    return sanitized


class HubSpotDealService:
    """
    Service for managing HubSpot deals.
    
    Features:
    - Field mapping from MemoExtraction to HubSpot properties
    - Pipeline stage resolution (name → stage ID)
    - Date formatting (ISO → HubSpot timestamp)
    - Deal name generation
    - Create or update logic
    """
    
    OBJECT_TYPE = "deals"
    
    def __init__(
        self,
        client: HubSpotClient,
        search: HubSpotSearchService,
        schema: HubSpotSchemaService,
    ):
        self.client = client
        self.search = search
        self.schema = schema
    
    def _generate_deal_name(
        self,
        extraction: MemoExtraction,
        contact_name: Optional[str] = None,
    ) -> str:
        """
        Generate a deal name from extraction data.
        
        Priority:
        1. Company name + " Deal"
        2. Contact name + " Deal"
        3. "New Deal"
        
        Args:
            extraction: MemoExtraction data
            contact_name: Optional contact name for fallback
            
        Returns:
            Deal name string
        """
        def _add_deal_suffix(s: str) -> str:
            s = s.strip()
            if s.lower().endswith("deal"):
                return s
            return f"{s} Deal"

        if extraction.companyName:
            return _add_deal_suffix(extraction.companyName)
        elif contact_name:
            return _add_deal_suffix(contact_name)
        elif extraction.contactName:
            return _add_deal_suffix(extraction.contactName)
        else:
            return "New Deal"
    
    def _to_hubspot_timestamp(self, iso_date: Optional[str]) -> str:
        """
        Convert ISO date string to HubSpot timestamp (milliseconds since epoch).
        
        Args:
            iso_date: ISO format date string (YYYY-MM-DD)
            
        Returns:
            Timestamp string in milliseconds, or None if invalid
        """
        try:
            from datetime import datetime
            
            # Parse ISO date
            dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
            
            # Convert to milliseconds since epoch
            timestamp_ms = int(dt.timestamp() * 1000)
            
            return str(timestamp_ms)
            
        except Exception:
            return None
    
    async def _resolve_stage_id(
        self,
        stage_value: Optional[str],
        pipeline_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Resolve pipeline stage (label or ID) to valid HubSpot stage ID.
        
        HubSpot expects stage IDs (e.g. closedwon, appointmentscheduled), not labels
        (e.g. "Cierre", "Cita agendada"). This method maps labels to IDs via schema,
        or validates/returns the value if it's already a valid stage ID.

        Args:
            stage_value: Stage label (e.g. "Cierre") or stage ID (e.g. "closedwon")
            pipeline_id: If provided, only match stages within this pipeline first
                (prevents pairing a stage from one pipeline with a different pipeline,
                which HubSpot rejects). Falls back to searching all pipelines.

        Returns:
            Stage ID if found/valid, None otherwise (do not send invalid values to HubSpot)
        """
        if not stage_value or not str(stage_value).strip():
            return None
        
        val = str(stage_value).strip().lower()
        
        try:
            schema = await self.schema.get_deal_schema()
            all_stage_ids: set[str] = set()

            pipelines_to_search = schema.pipelines
            if pipeline_id:
                scoped = [p for p in schema.pipelines if p.id == pipeline_id]
                if scoped:
                    pipelines_to_search = scoped

            for pipeline in pipelines_to_search:
                for stage in pipeline.stages:
                    all_stage_ids.add(stage.id.lower())
                    # Match by label (e.g. "Cierre" → closedwon when label is "Cierre ganado" etc.)
                    if stage.label and stage.label.lower() == val:
                        return stage.id
                    # Match by ID (extraction already has valid ID)
                    if stage.id.lower() == val:
                        return stage.id
            
            # Fallback: common Spanish/English labels → default pipeline stage IDs
            # Used when schema labels don't match (e.g. localized/custom labels)
            LABEL_TO_ID = {
                "cierre": "closedwon", "cierre ganado": "closedwon", "cerrado": "closedwon",
                "closed": "closedwon", "closed won": "closedwon", "ganado": "closedwon", "won": "closedwon",
                "cierre perdido": "closedlost", "closed lost": "closedlost", "perdido": "closedlost", "lost": "closedlost",
                "cita": "appointmentscheduled", "cita agendada": "appointmentscheduled",
                "appointment": "appointmentscheduled", "appointmentscheduled": "appointmentscheduled",
                "calificacion": "qualifiedtobuy", "qualified": "qualifiedtobuy", "qualifiedtobuy": "qualifiedtobuy",
                "presentacion": "presentationscheduled", "presentationscheduled": "presentationscheduled",
                "contrato": "contractsent", "contract": "contractsent", "contractsent": "contractsent",
                "decisionmakerboughtin": "decisionmakerboughtin",
            }
            resolved = LABEL_TO_ID.get(val)
            if resolved and resolved in all_stage_ids:
                return resolved
            
            return None
            
        except Exception:
            return None
    
    def map_extraction_to_properties(
        self,
        extraction: MemoExtraction,
        deal_name: Optional[str] = None,
        allowed_fields: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Convert MemoExtraction fields to HubSpot deal properties.

        allowed_fields (from CRM Configuration) is the single gate for what can be
        written: a field is only ever set if the user explicitly enabled it. This
        replaces guessing which extraction keys "look like" real CRM fields vs.
        meeting-intelligence fields (painPoints, nextSteps, etc.) - those are simply
        never in allowed_fields, so they're excluded without a hardcoded denylist.

        Args:
            extraction: MemoExtraction from voice memo
            deal_name: Optional deal name (will generate if not provided)
            allowed_fields: Fields the user enabled in CRM Configuration. When None,
                no restriction is applied (legacy/internal callers only - all sync
                and preview call sites always pass this).
            
        Returns:
            Dictionary of HubSpot property names to values
        """
        properties: dict[str, Any] = {}
        allowed_norm = (
            {normalize_hubspot_deal_property_key(f) for f in allowed_fields}
            if allowed_fields is not None else None
        )

        def _is_allowed(key: str) -> bool:
            return allowed_norm is None or key in allowed_norm

        # Deal name: always required by HubSpot to create a deal. This is a record
        # identity field, not a togglable "content" field the AI decides to write.
        properties["dealname"] = deal_name or self._generate_deal_name(extraction)

        if _is_allowed("amount") and extraction.dealAmount is not None:
            properties["amount"] = str(extraction.dealAmount)

        if _is_allowed("closedate") and extraction.closeDate:
            timestamp = self._to_hubspot_timestamp(extraction.closeDate)
            if timestamp:
                properties["closedate"] = timestamp

        if _is_allowed("description") and extraction.summary:
            if summary_looks_markdown(extraction.summary):
                bullet = first_bullet_plaintext(extraction.summary)
                if bullet:
                    properties["description"] = bullet
            else:
                properties["description"] = extraction.summary

        # Dynamic CRM fields: any curated field from the portal's schema that the LLM
        # extracted into raw_extraction, scoped to what the user enabled.
        if extraction.raw_extraction:
            for key, value in extraction.raw_extraction.items():
                norm_key = normalize_hubspot_deal_property_key(key)
                if (
                    norm_key in _CORE_FIELDS_HANDLED_SEPARATELY
                    or norm_key in _ALWAYS_EXCLUDED_PROPERTIES
                    or norm_key in HUBSPOT_READ_ONLY_DEAL_PROPERTIES
                    or _is_empty_raw_value(value)
                    or not _is_allowed(norm_key)
                ):
                    continue

                # Special handling for dates if they are in raw_extraction
                if norm_key == "closedate" and isinstance(value, str):
                    ts = self._to_hubspot_timestamp(value)
                    if ts:
                        properties[norm_key] = ts
                # Special handling for numbers
                elif isinstance(value, (int, float)):
                    properties[norm_key] = str(value)
                else:
                    coerced = _coerce_scalar_property_value(value)
                    if coerced is not None and not (isinstance(coerced, str) and not coerced.strip()):
                        properties[norm_key] = coerced

        # competitors: HubSpot expects single enum value (string), e.g. "cobee"
        if _is_allowed("competitors"):
            competitors_val = extraction.competitors
            if not competitors_val and extraction.raw_extraction:
                raw_comp = extraction.raw_extraction.get("competitors")
                if isinstance(raw_comp, list) and raw_comp:
                    competitors_val = [raw_comp[0]] if isinstance(raw_comp[0], str) else []
                elif isinstance(raw_comp, str) and raw_comp.strip():
                    competitors_val = [raw_comp.strip()]
            if competitors_val:
                single = competitors_val[0] if isinstance(competitors_val[0], str) else str(competitors_val[0])
                if single:
                    properties["competitors"] = single
        
        return properties
    
    def _normalize_enum_value(
        self, value: any, options: list
    ) -> any:
        """
        Map label to value for HubSpot enum fields.
        LLM extraction returns labels (e.g. 'High'); HubSpot API expects values (e.g. 'high').
        """
        if not isinstance(value, str) or not options:
            return value
        for opt in options:
            if opt.label.lower() == value.strip().lower():
                return opt.value
        # Fallback: lowercase often works for standard enums like hs_priority
        return value.lower()

    async def map_extraction_to_properties_with_stage(
        self,
        extraction: MemoExtraction,
        deal_name: Optional[str] = None,
        allowed_fields: Optional[list[str]] = None,
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
        is_new_deal: bool = True,
    ) -> dict[str, Any]:
        """
        Convert MemoExtraction to HubSpot properties, including stage resolution.
        
        This is the async version that resolves stage IDs.
        
        Args:
            extraction: MemoExtraction from voice memo
            deal_name: Optional deal name
            allowed_fields: Fields the user enabled in CRM Configuration.
            default_pipeline_id: User-configured pipeline (CRM Configuration screen).
                Applied so new deals land where the user expects instead of HubSpot's
                account-wide default pipeline (which may be a different, unwatched view).
            default_stage_id: Fallback stage (the target pipeline's first stage) used
                only when the transcript gives no signal about where the deal stands.
            is_new_deal: When True (creating a brand new deal), the AI-inferred stage is
                always applied since there's nothing to override and the deal needs some
                starting stage. When False (updating an existing deal), stage is only
                touched if the user explicitly enabled "dealstage" in allowed_fields -
                same rule as every other field, so a rep's manual pipeline management
                is never silently overridden.
            
        Returns:
            Dictionary of HubSpot property names to values
        """
        properties = self.map_extraction_to_properties(extraction, deal_name, allowed_fields=allowed_fields)

        dealstage_allowed = is_new_deal or "dealstage" in (allowed_fields or [])

        stage_raw = extraction.dealStage or (
            extraction.raw_extraction.get("dealstage") if extraction.raw_extraction else None
        )
        stage_id = None
        if dealstage_allowed and stage_raw:
            # Scope to the configured pipeline first so we never pair a stage from
            # one pipeline with a different pipeline (HubSpot rejects that combination).
            stage_id = await self._resolve_stage_id(stage_raw, pipeline_id=default_pipeline_id)

        if stage_id:
            properties["dealstage"] = stage_id
        elif is_new_deal and default_stage_id:
            # Fallback when the transcript gave no stage signal at all. Only applies to
            # new deals - existing deals should never be force-moved to a "default" stage.
            properties["dealstage"] = default_stage_id

        # Always set pipeline when configured, so new deals land in the pipeline the
        # user picked in CRM Configuration - not HubSpot's account-wide default pipeline,
        # which is where they'd otherwise silently end up and go unnoticed.
        if default_pipeline_id:
            properties["pipeline"] = default_pipeline_id

        # Normalize enum fields: LLM returns labels, HubSpot API expects values
        try:
            schema = await self.schema.get_deal_schema()
            prop_map = {p.name: p for p in schema.properties}
            for key in list(properties.keys()):
                prop = prop_map.get(key)
                if prop and prop.type in ("enumeration", "radio", "select") and prop.options:
                    properties[key] = self._normalize_enum_value(properties[key], prop.options)
        except Exception:
            pass  # If schema fetch fails, properties stay as-is

        return properties
    
    async def get(
        self,
        deal_id: str,
        properties: Optional[list[str]] = None,
    ) -> HubSpotDeal:
        """
        Get a deal by ID.

        Args:
            deal_id: HubSpot deal ID
            properties: Optional list of property names to fetch (default: standard set)

        Returns:
            HubSpotDeal object

        Raises:
            HubSpotNotFoundError if deal doesn't exist
            HubSpotError for other errors
        """
        props_param = ",".join(properties) if properties else (
            "dealname,amount,deal_currency_code,dealstage,closedate,description"
        )
        try:
            response = await self.client.get(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{deal_id}",
                params={"properties": props_param},
            )

            if not response:
                raise HubSpotError("Empty response from HubSpot")

            return HubSpotDeal(**response)

        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to get deal: {str(e)}")
    
    async def create(
        self,
        properties: dict[str, Any],
        contact_id: Optional[str] = None,
        company_id: Optional[str] = None,
        hubspot_owner_id: Optional[str] = None,
    ) -> HubSpotDeal:
        """
        Create a new deal with optional associations.
        
        Args:
            properties: Dictionary of HubSpot property names to values
            contact_id: Optional contact ID to associate
            company_id: Optional company ID to associate
            
        Returns:
            Created HubSpotDeal
            
        Raises:
            HubSpotError for API errors
        """
        if not properties.get("dealname"):
            raise HubSpotError("Deal name is required")

        properties = await _sanitize_enum_properties(self.schema, properties)
        if hubspot_owner_id:
            properties = {**properties, "hubspot_owner_id": str(hubspot_owner_id)}

        request = CreateObjectRequest(properties=properties)
        
        # Add associations if provided (HubSpot format: to.id + types)
        if contact_id:
            request.associations.append(
                AssociationSpec(
                    to=AssociationTo(id=contact_id),
                    types=[AssociationTypeSpec(associationTypeId=3)],  # deal to contact
                )
            )
        if company_id:
            request.associations.append(
                AssociationSpec(
                    to=AssociationTo(id=company_id),
                    types=[AssociationTypeSpec(associationTypeId=5)],  # deal to company
                )
            )
        
        try:
            response = await self.client.post(
                f"/crm/v3/objects/{self.OBJECT_TYPE}",
                data=request.model_dump(exclude_none=True, by_alias=True),
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotDeal(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to create deal: {str(e)}")
    
    async def update(
        self,
        deal_id: str,
        properties: dict[str, Any],
        hubspot_owner_id: Optional[str] = None,
    ) -> HubSpotDeal:
        """
        Update an existing deal.
        
        Args:
            deal_id: HubSpot deal ID
            properties: Dictionary of properties to update
            
        Returns:
            Updated HubSpotDeal
            
        Raises:
            HubSpotNotFoundError if deal doesn't exist
            HubSpotError for other errors
        """
        properties = await _sanitize_enum_properties(self.schema, properties)
        if hubspot_owner_id:
            properties = {**properties, "hubspot_owner_id": str(hubspot_owner_id)}

        request = UpdateObjectRequest(properties=properties)

        try:
            response = await self.client.patch(
                f"/crm/v3/objects/{self.OBJECT_TYPE}/{deal_id}",
                data=request.model_dump(exclude_none=True, by_alias=True),
            )
            
            if not response:
                raise HubSpotError("Empty response from HubSpot")
            
            return HubSpotDeal(**response)
            
        except Exception as e:
            if isinstance(e, HubSpotError):
                raise
            raise HubSpotError(f"Failed to update deal: {str(e)}")
    
    async def create_or_update(
        self,
        extraction: MemoExtraction,
        contact_id: Optional[str] = None,
        company_id: Optional[str] = None,
        hubspot_owner_id: Optional[str] = None,
        allowed_fields: Optional[list[str]] = None,
        default_pipeline_id: Optional[str] = None,
        default_stage_id: Optional[str] = None,
    ) -> HubSpotDeal:
        """
        Create a new deal based on extraction data.
        
        Note: We always create a new deal (don't update existing).
        This matches the product principle: one voice memo = one CRM update.
        
        Args:
            extraction: MemoExtraction with deal data
            contact_id: Optional contact ID to associate
            company_id: Optional company ID to associate
            allowed_fields: Fields the user enabled in CRM Configuration - only
                these are ever written, regardless of what the LLM extracted.
            default_pipeline_id: User-configured pipeline for new deals
            default_stage_id: User-configured default stage for new deals
            
        Returns:
            Created HubSpotDeal
            
        Raises:
            HubSpotError for API errors
        """
        deal_name = self._generate_deal_name(
            extraction,
            contact_name=None,  # Could fetch contact name if needed
        )
        
        properties = await self.map_extraction_to_properties_with_stage(
            extraction,
            deal_name=deal_name,
            allowed_fields=allowed_fields,
            default_pipeline_id=default_pipeline_id,
            default_stage_id=default_stage_id,
            is_new_deal=True,
        )

        return await self.create(
            properties,
            contact_id=contact_id,
            company_id=company_id,
            hubspot_owner_id=hubspot_owner_id,
        )

