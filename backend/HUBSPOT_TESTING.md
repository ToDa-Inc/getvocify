# HubSpot Integration Testing Guide

## ✅ What Was Built

Complete HubSpot CRM integration service layer with:

- **10 service modules** (client, validation, schema, search, CRUD, associations, sync)
- **7 exception types** for granular error handling
- **20+ Pydantic models** for type safety
- **5 API endpoints** for connection management
- **Rate limiting & retry logic** built-in
- **Schema caching** for performance

## 🧪 Testing the Endpoints

### Prerequisites

1. **Add to `.env` file:**
   ```bash
   HUBSPOT_DEVELOPER_API_KEY=pat-na1-your-token-here
   ```

2. **Start the backend server:**
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Test Endpoints

#### 1. Connect HubSpot (POST)

```bash
curl -X POST http://localhost:8000/api/v1/crm/hubspot/connect \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_USER_TOKEN" \
  -d '{
    "access_token": "pat-na1-your-hubspot-token"
  }'
```

**Expected Response:**
```json
{
  "connection_id": "uuid-here",
  "status": "connected",
  "portal_id": "12345678"
}
```

#### 2. Test Connection (POST)

```bash
curl -X POST http://localhost:8000/api/v1/crm/hubspot/test \
  -H "Authorization: Bearer YOUR_USER_TOKEN"
```

**Expected Response:**
```json
{
  "valid": true,
  "portal_id": "12345678",
  "scopes_ok": true,
  "error": null,
  "error_code": null
}
```

#### 3. Get Deal Schema (GET)

```bash
curl http://localhost:8000/api/v1/crm/hubspot/schema \
  -H "Authorization: Bearer YOUR_USER_TOKEN"
```

**Expected Response:**
```json
{
  "object_type": "deals",
  "properties": [
    {
      "name": "dealname",
      "label": "Deal Name",
      "type": "string",
      "fieldType": "text",
      "required": true
    },
    ...
  ],
  "pipelines": [
    {
      "id": "default",
      "label": "Sales Pipeline",
      "stages": [...]
    }
  ]
}
```

#### 4. Get Connection Details (GET)

```bash
curl http://localhost:8000/api/v1/crm/hubspot/connection \
  -H "Authorization: Bearer YOUR_USER_TOKEN"
```

#### 5. Disconnect (DELETE)

```bash
curl -X DELETE http://localhost:8000/api/v1/crm/hubspot/disconnect \
  -H "Authorization: Bearer YOUR_USER_TOKEN"
```

## 🧪 Testing with Python Script

Create a test script:

```python
import asyncio
import httpx

async def test():
    base_url = "http://localhost:8000/api/v1/crm"
    headers = {
        "Authorization": "Bearer YOUR_USER_TOKEN",
        "Content-Type": "application/json"
    }
    
    # Test connect
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/hubspot/connect",
            headers=headers,
            json={"access_token": "pat-na1-your-token"}
        )
        print("Connect:", response.json())
        
        # Test schema
        response = await client.get(
            f"{base_url}/hubspot/schema",
            headers=headers
        )
        print("Schema:", response.json())

asyncio.run(test())
```

## ✅ Expected Results

### Successful Connection
- ✅ Token validation passes
- ✅ Portal ID returned
- ✅ Connection saved to database
- ✅ Status: "connected"

### Schema Fetch
- ✅ Properties list returned (50+ properties)
- ✅ Pipelines with stages returned
- ✅ Cached for 1 hour

### Error Handling
- ❌ Invalid token → 400 with error message
- ❌ Missing scopes → 403 with scope details
- ❌ Rate limit → 429 with retry-after

## 🔍 Debugging

### Check Logs
```bash
# Server logs will show:
# - API requests
# - Rate limit warnings
# - Error details
```

### Common Issues

1. **"Token not found"**
   - Check `.env` file has `HUBSPOT_DEVELOPER_API_KEY`
   - Restart server after adding env var

2. **"Authentication failed"**
   - Verify token format: `pat-na1-...`
   - Check token hasn't expired (Private Apps don't expire, but check anyway)

3. **"Missing permissions"**
   - Verify Private App has these scopes:
     - `crm.objects.contacts.read`
     - `crm.objects.contacts.write`
     - `crm.objects.companies.read`
     - `crm.objects.companies.write`
     - `crm.objects.deals.read`
     - `crm.objects.deals.write`
     - `crm.schemas.*.read`

4. **"Module not found"**
   - Install dependencies: `pip install -r requirements.txt`

## 📊 What Gets Tested

1. ✅ **Token Validation**
   - Format checking
   - Authentication test
   - Scope verification

2. ✅ **Schema Fetching**
   - Properties API
   - Pipelines API
   - Caching logic

3. ✅ **Error Handling**
   - Invalid tokens
   - Missing scopes
   - Rate limits
   - Network errors

## 🚀 Next Steps

After testing endpoints:

1. **Integrate with memo approval flow**
   - Wire `HubSpotSyncService` into memo approval endpoint
   - Test full sync: memo → extraction → HubSpot

2. **Test write operations**
   - Create contact
   - Create company
   - Create deal
   - Create associations

3. **Test deduplication**
   - Find existing contacts by email
   - Find existing companies by name

4. **Test stage resolution**
   - Map stage names to IDs
   - Handle invalid stage names

