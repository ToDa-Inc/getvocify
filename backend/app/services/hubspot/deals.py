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


async def _sanitize_enum_properties(
    schema_service: HubSpotSchemaService,
    properties: dict[str, Any],
) -> dict[str, Any]:
    """
    Schema-driven validation gate for enum properties.
    Validates against allowed options, formats multi-select as semicolon-separated,
    drops invalid values. Non-enum properties pass through unchanged.
    """
    if not properties:
        return properties

    try:
        schema = await schema_service.get_deal_schema()
        prop_map = {p.name: p for p in schema.properties}
    except Exception as e:
        logger.warning("Schema fetch failed, skipping enum validation: %s", e)
        return properties

    sanitized: dict[str, Any] = {}
    for key, value in properties.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue

        prop = prop_map.get(key)
        if not prop or prop.type not in ("enumeration", "checkbox", "radio", "select") or not prop.options:
            sanitized[key] = value
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
        if extraction.companyName:
            return f"{extraction.companyName} Deal"
        elif contact_name:
            return f"{contact_name} Deal"
        elif extraction.contactName:
            return f"{extraction.contactName} Deal"
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
    
    async def _resolve_stage_id(self, stage_value: Optional[str]) -> Optional[str]:
        """
        Resolve pipeline stage (label or ID) to valid HubSpot stage ID.
        
        HubSpot expects stage IDs (e.g. closedwon, appointmentscheduled), not labels
        (e.g. "Cierre", "Cita agendada"). This method maps labels to IDs via schema,
        or validates/returns the value if it's already a valid stage ID.
        
        Args:
            stage_value: Stage label (e.g. "Cierre") or stage ID (e.g. "closedwon")
            
        Returns:
            Stage ID if found/valid, None otherwise (do not send invalid values to HubSpot)
        """
        if not stage_value or not str(stage_value).strip():
            return None
        
        val = str(stage_value).strip().lower()
        
        try:
            schema = await self.schema.get_deal_schema()
            all_stage_ids: set[str] = set()
            
            for pipeline in schema.pipelines:
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
    ) -> dict[str, Any]:
        """
        Convert MemoExtraction fields to HubSpot deal properties.
        
        Args:
            extraction: MemoExtraction from voice memo
            deal_name: Optional deal name (will generate if not provided)
            
        Returns:
            Dictionary of HubSpot property names to values
        """
        properties: dict[str, Any] = {}
        
        # 1. Handle Legacy / Standard Fields (Backward Compatibility)
        # Deal name (required)
        properties["dealname"] = deal_name or self._generate_deal_name(extraction)
        
        # Amount
        if extraction.dealAmount is not None:
            properties["amount"] = str(extraction.dealAmount)
        
        # Close date
        if extraction.closeDate:
            timestamp = self._to_hubspot_timestamp(extraction.closeDate)
            if timestamp:
                properties["closedate"] = timestamp
        
        # Description (summary)
        if extraction.summary:
            properties["description"] = extraction.summary

        # 2. Handle Dynamic CRM Fields (The "Gold Standard")
        # If we have raw_extraction, use it as the source of truth for CRM fields
        if extraction.raw_extraction:
            # Fields we already handled in step 1 or that are not CRM deal properties
            # deal_currency_code: omit - HubSpot validates against portal's effective currencies;
            # sending EUR (or other) can fail if not configured for the portal. Amount uses portal default.
            # dealstage: omit - must be resolved via pipeline schema (label→ID); never send raw labels like "Cierre"
            skip_fields = [
                "dealname", "amount", "closedate", "description",
                "summary", "painPoints", "nextSteps", "competitors",
                "objections", "decisionMakers", "confidence",
                "contactName", "companyName", "contactEmail",  # Used for associations, not deal props
                "deal_currency_code",  # Portal-specific; omit to avoid INVALID_OPTION validation
                "dealstage",  # Resolved separately via _resolve_stage_id; labels (e.g. "Cierre") are invalid
            ]
            
            for key, value in extraction.raw_extraction.items():
                if key in skip_fields or key in HUBSPOT_READ_ONLY_DEAL_PROPERTIES or value is None:
                    continue
                
                # Special handling for dates if they are in raw_extraction
                if key == "closedate" and isinstance(value, str):
                    ts = self._to_hubspot_timestamp(value)
                    if ts:
                        properties[key] = ts
                # Special handling for numbers
                elif isinstance(value, (int, float)):
                    properties[key] = str(value)
                # Everything else is passed through
                else:
                    properties[key] = value
        
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
    ) -> dict[str, Any]:
        """
        Convert MemoExtraction to HubSpot properties, including stage resolution.
        
        This is the async version that resolves stage IDs.
        
        Args:
            extraction: MemoExtraction from voice memo
            deal_name: Optional deal name
            
        Returns:
            Dictionary of HubSpot property names to values
        """
        properties = self.map_extraction_to_properties(extraction, deal_name)
        
        # Resolve deal stage: only set when we have a valid HubSpot stage ID
        # (Labels like "Cierre" are resolved via _resolve_stage_id; invalid values are omitted)
        stage_raw = extraction.dealStage or (
            extraction.raw_extraction.get("dealstage") if extraction.raw_extraction else None
        )
        if stage_raw:
            stage_id = await self._resolve_stage_id(stage_raw)
            if stage_id:
                properties["dealstage"] = stage_id

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
    ) -> HubSpotDeal:
        """
        Create a new deal based on extraction data.
        
        Note: We always create a new deal (don't update existing).
        This matches the product principle: one voice memo = one CRM update.
        
        Args:
            extraction: MemoExtraction with deal data
            contact_id: Optional contact ID to associate
            company_id: Optional company ID to associate
            
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
        )

        return await self.create(
            properties,
            contact_id=contact_id,
            company_id=company_id,
            hubspot_owner_id=hubspot_owner_id,
        )

