"""
Schema discovery service for HubSpot objects.

Fetches properties and pipelines with intelligent caching.
Supports both in-memory and database caching.
"""

from typing import Literal, Optional
from datetime import datetime, timedelta
from uuid import UUID

from .client import HubSpotClient
from .exceptions import HubSpotError
from .types import HubSpotProperty, HubSpotPipeline, CRMSchema
from supabase import Client


class HubSpotSchemaService:
    """
    Fetches and caches HubSpot object schemas.
    
    Schemas include:
    - Properties (fields) for contacts, companies, deals
    - Pipelines and stages for deals
    
    Caching:
    - Properties change infrequently, cache for 1 hour
    - Pipelines change rarely, cache for 1 hour
    - Cache is per-object-type
    """
    
    CACHE_TTL_SECONDS = 3600  # 1 hour
    DB_CACHE_TTL_HOURS = 24  # 24 hours for database cache
    
    def __init__(self, client: HubSpotClient, supabase: Optional[Client] = None, connection_id: Optional[str] = None):
        self.client = client
        self.supabase = supabase
        self.connection_id = connection_id
        self._cache: dict[str, CRMSchema] = {}
        self._cache_timestamps: dict[str, datetime] = {}
    
    def _is_cache_valid(self, object_type: str) -> bool:
        """Check if cached schema is still valid"""
        if object_type not in self._cache_timestamps:
            return False
        
        age = datetime.utcnow() - self._cache_timestamps[object_type]
        return age.total_seconds() < self.CACHE_TTL_SECONDS
    
    def _get_from_cache(self, object_type: str) -> CRMSchema | None:
        """Get schema from cache if valid"""
        if self._is_cache_valid(object_type) and object_type in self._cache:
            return self._cache[object_type]
        return None
    
    def _set_cache(self, object_type: str, schema: CRMSchema) -> None:
        """Store schema in cache"""
        self._cache[object_type] = schema
        self._cache_timestamps[object_type] = datetime.utcnow()
    
    def invalidate_cache(self, object_type: str | None = None) -> None:
        """
        Invalidate schema cache.
        
        Args:
            object_type: Specific object type to invalidate, or None for all
        """
        if object_type:
            self._cache.pop(object_type, None)
            self._cache_timestamps.pop(object_type, None)
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
    
    async def get_properties(
        self,
        object_type: Literal["contacts", "companies", "deals"],
    ) -> list[HubSpotProperty]:
        """
        Get all properties for an object type.
        
        Args:
            object_type: Object type (contacts, companies, or deals)
            
        Returns:
            List of property definitions
            
        Raises:
            HubSpotError if API call fails
        """
        try:
            response = await self.client.get(f"/crm/v3/properties/{object_type}")
            
            if not response or "results" not in response:
                return []
            
            properties = []
            for prop_data in response["results"]:
                try:
                    prop = HubSpotProperty(**prop_data)
                    properties.append(prop)
                except Exception:
                    # Skip invalid properties
                    continue
            
            return properties
            
        except Exception as e:
            raise HubSpotError(f"Failed to fetch properties for {object_type}: {str(e)}")
    
    async def get_pipelines(
        self,
        object_type: Literal["contacts", "companies", "deals"] = "deals",
    ) -> list[HubSpotPipeline]:
        """
        Get pipelines and stages for an object type.
        
        Note: Only deals have pipelines. Contacts and companies don't.
        
        Args:
            object_type: Object type (default: deals)
            
        Returns:
            List of pipelines with stages
            
        Raises:
            HubSpotError if API call fails
        """
        if object_type != "deals":
            # Only deals have pipelines
            return []
        
        try:
            response = await self.client.get(f"/crm/v3/pipelines/{object_type}")
            
            if not response or "results" not in response:
                return []
            
            pipelines = []
            for pipeline_data in response["results"]:
                try:
                    pipeline = HubSpotPipeline(**pipeline_data)
                    pipelines.append(pipeline)
                except Exception:
                    # Skip invalid pipelines
                    continue
            
            return pipelines
            
        except Exception as e:
            raise HubSpotError(f"Failed to fetch pipelines for {object_type}: {str(e)}")
    
    async def _get_from_db_cache(
        self,
        object_type: str,
    ) -> Optional[CRMSchema]:
        """Get schema from database cache if valid"""
        if not self.supabase or not self.connection_id:
            return None
        
        try:
            result = self.supabase.table("crm_schemas").select("*").eq(
                "connection_id", self.connection_id
            ).eq("object_type", object_type).single().execute()
            
            if not result.data:
                return None
            
            schema_data = result.data
            
            # Check if cache is still valid (24 hours)
            fetched_at = datetime.fromisoformat(schema_data["fetched_at"].replace("Z", "+00:00"))
            age = datetime.utcnow().replace(tzinfo=fetched_at.tzinfo) - fetched_at
            
            if age.total_seconds() > (self.DB_CACHE_TTL_HOURS * 3600):
                # Cache expired
                return None
            
            # Parse cached schema
            properties = [HubSpotProperty(**p) for p in schema_data["properties"]]
            pipelines = []
            if schema_data.get("pipelines"):
                pipelines = [HubSpotPipeline(**p) for p in schema_data["pipelines"]]
            
            return CRMSchema(
                object_type=object_type,
                properties=properties,
                pipelines=pipelines,
            )
        except Exception:
            # If DB cache fails, return None (fall back to API)
            return None
    
    async def _save_to_db_cache(
        self,
        object_type: str,
        schema: CRMSchema,
    ) -> None:
        """Save schema to database cache"""
        if not self.supabase or not self.connection_id:
            return
        
        try:
            cache_data = {
                "connection_id": self.connection_id,
                "object_type": object_type,
                "properties": [p.model_dump() for p in schema.properties],
                "pipelines": [p.model_dump() for p in schema.pipelines] if schema.pipelines else None,
                "fetched_at": datetime.utcnow().isoformat(),
            }
            
            self.supabase.table("crm_schemas").upsert(
                cache_data,
                on_conflict="connection_id,object_type",
            ).execute()
        except Exception:
            # If DB cache save fails, continue (not critical)
            pass
    
    async def get_schema(
        self,
        object_type: Literal["contacts", "companies", "deals"],
        use_cache: bool = True,
    ) -> CRMSchema:
        """
        Get complete schema (properties + pipelines) for an object type.
        
        Checks database cache first, then in-memory cache, then API.
        
        Args:
            object_type: Object type (contacts, companies, or deals)
            use_cache: Whether to use cached schema if available
            
        Returns:
            CRMSchema with properties and pipelines
            
        Raises:
            HubSpotError if API call fails
        """
        # Check database cache first (if available)
        if use_cache and self.supabase and self.connection_id:
            db_cached = await self._get_from_db_cache(object_type)
            if db_cached:
                # Also store in memory cache for faster subsequent access
                self._set_cache(object_type, db_cached)
                return db_cached
        
        # Check in-memory cache
        if use_cache:
            cached = self._get_from_cache(object_type)
            if cached:
                return cached
        
        # Fetch fresh schema from API
        properties = await self.get_properties(object_type)
        pipelines = await self.get_pipelines(object_type) if object_type == "deals" else []
        
        schema = CRMSchema(
            object_type=object_type,
            properties=properties,
            pipelines=pipelines,
        )
        
        # Cache in memory
        self._set_cache(object_type, schema)
        
        # Cache in database (if available)
        if self.supabase and self.connection_id:
            await self._save_to_db_cache(object_type, schema)
        
        return schema
    
    async def get_contact_schema(self, use_cache: bool = True) -> CRMSchema:
        """Get contact schema"""
        return await self.get_schema("contacts", use_cache)
    
    async def get_company_schema(self, use_cache: bool = True) -> CRMSchema:
        """Get company schema"""
        return await self.get_schema("companies", use_cache)
    
    async def get_deal_schema(self, use_cache: bool = True) -> CRMSchema:
        """Get deal schema (includes pipelines)"""
        return await self.get_schema("deals", use_cache)

    async def get_curated_field_specs(
        self,
        object_type: Literal["contacts", "companies", "deals"],
        field_names: list[str],
    ) -> list[dict]:
        """
        Get curated metadata for specific fields to use in LLM prompts.
        
        Strips away API noise and keeps only reasoning-critical info:
        - name (key)
        - label
        - description
        - type
        - options (for enums)
        """
        schema = await self.get_schema(object_type)
        all_props = {p.name: p for p in schema.properties}
        
        curated_specs = []
        for name in field_names:
            if name not in all_props:
                continue
                
            prop = all_props[name]
            spec = {
                "name": prop.name,
                "label": prop.label,
                "type": prop.type,
                "description": prop.description or "",
            }
            
            # For enumerations, provide labels for better LLM reasoning
            if prop.type in ["enumeration", "checkbox", "radio", "select"] and prop.options:
                spec["options"] = [opt.label for opt in prop.options if not opt.hidden]
            
            curated_specs.append(spec)
            
        return curated_specs

