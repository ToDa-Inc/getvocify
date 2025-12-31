# CRM Integration Architecture Notes

> **Purpose**: Document architectural decisions, trade-offs, and future improvements for the CRM integration system.

---

## Current Architecture (MVP)

### Design Decisions

1. **Deal-First Approach**
   - Current implementation focuses on deals as the primary CRM object
   - Matching, preview, and sync services are deal-centric
   - Rationale: Deals are the core value proposition - sales reps update deals most frequently

2. **Separate Columns for Critical Fields**
   - `matched_deal_id`, `matched_deal_name`, `is_new_deal` stored as separate columns
   - Configuration stored in dedicated `crm_configurations` table with typed columns
   - Rationale: Type safety, queryability, foreign key constraints, self-documenting schema

3. **Field Whitelisting**
   - Users configure `allowed_deal_fields`, `allowed_contact_fields`, `allowed_company_fields`
   - Only whitelisted fields can be updated by AI
   - Rationale: Trust and safety - users control what AI can touch

---

## Future Improvements

### 1. Multi-Object Support (Contacts, Companies, Deals)

**Current Limitation:**
- Matching, preview, and sync services are deal-specific
- Hard to extend to contacts/companies without duplication

**Proposed Refactoring:**

```python
# Generic object matcher
class CRMObjectMatcher:
    async def find_matches(
        self,
        object_type: Literal["deals", "contacts", "companies"],
        extraction: MemoExtraction,
        config: CRMConfiguration,
    ) -> list[ObjectMatch]:
        """Find matches for any object type"""
        # Object-type agnostic matching logic

# Generic preview service
class CRMUpdatePreview:
    async def build_preview(
        self,
        object_type: Literal["deals", "contacts", "companies"],
        extraction: MemoExtraction,
        matched_objects: list[ObjectMatch],
        config: CRMConfiguration,
    ) -> UpdatePreview:
        """Build preview for any object type"""
        # Object-type agnostic preview logic
```

**Benefits:**
- Single code path for all object types
- Easier to add new CRM objects (tasks, notes, etc.)
- Consistent UX across all object types
- Less code duplication

**When to Implement:**
- When adding contacts/companies matching
- When users request multi-object support
- Before adding 3rd CRM object type

**Migration Path:**
1. Create generic `CRMObjectMatcher` service
2. Refactor `HubSpotMatchingService` to use generic matcher
3. Create generic `CRMUpdatePreview` service
4. Refactor `HubSpotPreviewService` to use generic preview
5. Update sync service to handle multiple object types

---

### 2. JSONB Columns vs Separate Columns

**Current Approach:**
```sql
-- Separate columns for critical fields
matched_deal_id TEXT,
matched_deal_name TEXT,
is_new_deal BOOLEAN,

-- Separate columns for configuration
default_pipeline_id TEXT,
default_pipeline_name TEXT,
default_stage_id TEXT,
default_stage_name TEXT,
allowed_deal_fields TEXT[],
...
```

**JSONB Alternative:**
```sql
-- Single JSONB column for match metadata
crm_match_metadata JSONB DEFAULT '{}',
-- Example: {"deal_id": "123", "deal_name": "Acme", "is_new": false, "match_confidence": 0.95}

-- Single JSONB column for configuration
configuration JSONB NOT NULL DEFAULT '{}',
-- Example: {"pipeline": {"id": "default", "name": "Sales"}, "stage": {...}, "allowed_fields": {...}}
```

**Trade-offs:**

| Aspect | Separate Columns | JSONB Columns |
|--------|------------------|---------------|
| **Type Safety** | ✅ Strong typing | ❌ Runtime validation only |
| **Queryability** | ✅ Easy SQL queries | ⚠️ Requires JSON operators |
| **Foreign Keys** | ✅ Can use FK constraints | ❌ No FK support |
| **Flexibility** | ❌ Requires migrations | ✅ Add fields without migrations |
| **Self-Documenting** | ✅ Schema shows structure | ⚠️ Need to inspect JSON |
| **Performance** | ✅ Indexed columns | ✅ JSONB has indexing too |

**Recommended Hybrid Approach:**

```sql
-- Keep critical fields as columns (for queries, FKs, type safety)
matched_deal_id TEXT,  -- For FK relationships, filtering
is_new_deal BOOLEAN,   -- For filtering, type safety

-- Use JSONB for flexible metadata (avoids frequent migrations)
crm_match_metadata JSONB DEFAULT '{}',
-- {"deal_name": "Acme", "match_confidence": 0.95, "match_reason": "Company match", "contact_id": "456"}

-- Configuration: JSONB makes sense (rarely queried, highly nested)
configuration JSONB NOT NULL DEFAULT '{}',
-- Full config object: {"pipeline": {...}, "stage": {...}, "allowed_fields": {...}}
```

**Why Hybrid:**
- ✅ Critical fields stay queryable and type-safe
- ✅ Flexible metadata avoids frequent migrations
- ✅ Config is nested and rarely filtered - perfect for JSONB
- ✅ Best of both worlds

**When to Migrate:**
- When adding contacts/companies (need `matched_contact_id`, `matched_company_id`)
- When config structure stabilizes (less churn)
- When need for flexible metadata grows (custom fields, provider-specific data)

**Migration Steps:**
1. Add `crm_match_metadata` JSONB column to `memos` table
2. Migrate existing `matched_deal_name` to JSONB
3. Add `configuration` JSONB column to `crm_configurations` table
4. Migrate existing config columns to JSONB
5. Update application code to read/write JSONB
6. Keep critical fields as columns for backward compatibility
7. Deprecate old columns after migration period

---

## Database Schema Evolution

### Current Schema (MVP)

```sql
-- Memos table
CREATE TABLE memos (
    ...
    matched_deal_id TEXT,
    matched_deal_name TEXT,
    is_new_deal BOOLEAN,
    ...
);

-- Configurations table
CREATE TABLE crm_configurations (
    ...
    default_pipeline_id TEXT NOT NULL,
    default_pipeline_name TEXT NOT NULL,
    default_stage_id TEXT NOT NULL,
    default_stage_name TEXT NOT NULL,
    allowed_deal_fields TEXT[],
    allowed_contact_fields TEXT[],
    allowed_company_fields TEXT[],
    ...
);
```

### Future Schema (v2)

```sql
-- Memos table (hybrid approach)
CREATE TABLE memos (
    ...
    -- Critical fields (keep as columns)
    matched_deal_id TEXT,
    matched_contact_id TEXT,  -- New: for contact matching
    matched_company_id TEXT,  -- New: for company matching
    is_new_deal BOOLEAN,
    
    -- Flexible metadata (JSONB)
    crm_match_metadata JSONB DEFAULT '{}',
    -- Example structure:
    -- {
    --   "deal": {"id": "123", "name": "Acme", "confidence": 0.95},
    --   "contact": {"id": "456", "name": "John", "confidence": 0.88},
    --   "company": {"id": "789", "name": "Acme Corp", "confidence": 0.92}
    -- }
    ...
);

-- Configurations table (JSONB for config)
CREATE TABLE crm_configurations (
    ...
    -- Keep connection_id as FK
    connection_id UUID NOT NULL REFERENCES crm_connections(id),
    
    -- Full config in JSONB
    configuration JSONB NOT NULL DEFAULT '{}',
    -- Example structure:
    -- {
    --   "deals": {
    --     "pipeline": {"id": "default", "name": "Sales Pipeline"},
    --     "stage": {"id": "appointmentscheduled", "name": "Appointment Scheduled"},
    --     "allowed_fields": ["dealname", "amount", "description", "closedate"]
    --   },
    --   "contacts": {
    --     "allowed_fields": ["firstname", "lastname", "email", "phone"],
    --     "auto_create": true
    --   },
    --   "companies": {
    --     "allowed_fields": ["name", "domain"],
    --     "auto_create": true
    --   }
    -- }
    ...
);
```

---

## Service Layer Evolution

### Current Services (MVP)

```
HubSpotMatchingService (deal-specific)
HubSpotPreviewService (deal-specific)
HubSpotSyncService (deal-focused)
```

### Future Services (v2)

```
CRMObjectMatcher (generic)
  └── HubSpotObjectMatcher (provider-specific)
  
CRMUpdatePreview (generic)
  └── HubSpotUpdatePreview (provider-specific)
  
CRMSyncOrchestrator (generic)
  └── HubSpotSyncOrchestrator (provider-specific)
```

**Benefits:**
- Easier to add Salesforce, Pipedrive later
- Consistent interface across providers
- Less code duplication

---

## Configuration Evolution

### Current Config Structure

```python
class CRMConfigurationRequest:
    default_pipeline_id: str
    default_pipeline_name: str
    default_stage_id: str
    default_stage_name: str
    allowed_deal_fields: list[str]
    allowed_contact_fields: list[str]
    allowed_company_fields: list[str]
    auto_create_contacts: bool
    auto_create_companies: bool
```

### Future Config Structure (JSONB)

```python
class CRMConfiguration:
    deals: DealConfig
    contacts: ContactConfig
    companies: CompanyConfig
    
class DealConfig:
    pipeline: PipelineConfig
    stage: StageConfig
    allowed_fields: list[str]
    
class ContactConfig:
    allowed_fields: list[str]
    auto_create: bool
    
class CompanyConfig:
    allowed_fields: list[str]
    auto_create: bool
```

**Stored as JSONB:**
```json
{
  "deals": {
    "pipeline": {"id": "default", "name": "Sales Pipeline"},
    "stage": {"id": "appointmentscheduled", "name": "Appointment Scheduled"},
    "allowed_fields": ["dealname", "amount", "description", "closedate"]
  },
  "contacts": {
    "allowed_fields": ["firstname", "lastname", "email", "phone"],
    "auto_create": true
  },
  "companies": {
    "allowed_fields": ["name", "domain"],
    "auto_create": true
  }
}
```

---

## Implementation Priority

### Phase 1: MVP (Current) ✅
- [x] Deal-focused matching
- [x] Deal-focused preview
- [x] Deal-focused sync
- [x] Separate config columns
- [x] Field whitelisting

### Phase 2: Multi-Object Support
- [ ] Generic object matcher
- [ ] Generic preview service
- [ ] Contact/company matching
- [ ] Contact/company preview
- [ ] Multi-object sync orchestration

### Phase 3: Schema Optimization
- [ ] Add `crm_match_metadata` JSONB column
- [ ] Migrate config to JSONB
- [ ] Keep critical fields as columns
- [ ] Update application code

### Phase 4: Multi-Provider Support
- [ ] CRM adapter interface
- [ ] Salesforce adapter
- [ ] Pipedrive adapter
- [ ] Provider-agnostic services

---

## Key Principles

1. **YAGNI** - Don't build for hypothetical futures
2. **Type Safety First** - Use typed columns for critical fields
3. **Flexibility Where Needed** - Use JSONB for metadata/config
4. **Incremental Evolution** - Refactor when adding new features, not before
5. **Backward Compatibility** - Keep old columns during migration period

---

## Notes

- Current MVP architecture is solid and production-ready
- JSONB migration should happen when adding contacts/companies
- Generic services should be created when adding 2nd object type
- Don't over-engineer - current approach works well for MVP

---

**Last Updated**: 2025-12-30
**Status**: MVP Complete, Future Improvements Documented

