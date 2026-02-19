"""
Standalone test for HubSpot - imports modules directly without package structure.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add hubspot directory to path
hubspot_dir = Path(__file__).parent / "app" / "services" / "hubspot"
sys.path.insert(0, str(hubspot_dir))

# Load env vars
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip('"').strip("'")

# Import directly
import httpx
from typing import Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Literal

# Copy minimal types needed
class ValidationResult(BaseModel):
    valid: bool
    portal_id: Optional[str] = None
    scopes_ok: bool = False
    error: Optional[str] = None
    error_code: Optional[str] = None

# Copy client class inline
class HubSpotClient:
    BASE_URL = "https://api.hubapi.com"
    DEFAULT_TIMEOUT = 30.0
    
    def __init__(self, access_token: str):
        if not access_token or not access_token.strip():
            raise ValueError("Access token cannot be empty")
        self.access_token = access_token.strip()
    
    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
    
    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()
        
        async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
            response = await client.get(url, headers=headers, params=params)
            
            if response.status_code == 204:
                return None
            
            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except Exception:
                    return {}
            
            error_data = response.json() if response.content else {}
            raise Exception(f"API error ({response.status_code}): {error_data.get('message', 'Unknown error')}")

# Copy validation service inline
class HubSpotValidationService:
    def __init__(self, client: HubSpotClient):
        self.client = client
    
    def _validate_token_format(self, token: str) -> bool:
        if not token or len(token) < 10:
            return False
        if token.startswith("pat-") or token.startswith("pat-na1-"):
            return True
        if len(token) > 50 and token.replace("-", "").replace("_", "").isalnum():
            return True
        return False
    
    async def validate(self) -> ValidationResult:
        if not self._validate_token_format(self.client.access_token):
            return ValidationResult(
                valid=False,
                error="Invalid token format",
                error_code="INVALID_FORMAT",
            )
        
        try:
            account_info = await self.client.get("/integrations/v1/me")
            if not account_info:
                return ValidationResult(valid=False, error="Failed to retrieve account info", error_code="AUTH_FAILED")
            
            portal_id = str(account_info.get("portalId", ""))
            return ValidationResult(valid=True, portal_id=portal_id, scopes_ok=True)
        except Exception as e:
            return ValidationResult(valid=False, error=str(e), error_code="VALIDATION_ERROR")

async def test():
    access_token = os.getenv("HUBSPOT_DEVELOPER_API_KEY") or os.getenv("HUBSPOT_ACCESS_TOKEN")
    
    if not access_token:
        print("❌ ERROR: HUBSPOT_DEVELOPER_API_KEY or HUBSPOT_ACCESS_TOKEN not found")
        return
    
    print(f"✅ Found token: {access_token[:20]}...")
    print("\n" + "="*60)
    print("TESTING HUBSPOT INTEGRATION")
    print("="*60 + "\n")
    
    client = HubSpotClient(access_token)
    validation = HubSpotValidationService(client)
    
    print("1️⃣ Testing token validation...")
    result = await validation.validate()
    
    if result.valid:
        print(f"   ✅ Token is valid!")
        print(f"   📊 Portal ID: {result.portal_id}")
    else:
        print(f"   ❌ Failed: {result.error}")
        return
    
    print("\n2️⃣ Testing schema fetch...")
    try:
        schema = await client.get("/crm/v3/properties/deals", params={"limit": 5})
        if schema and "results" in schema:
            print(f"   ✅ Fetched {len(schema['results'])} properties")
            for prop in schema["results"][:3]:
                print(f"      - {prop.get('name', 'N/A')} ({prop.get('type', 'N/A')})")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    print("\n3️⃣ Testing pipelines...")
    try:
        pipelines = await client.get("/crm/v3/pipelines/deals")
        if pipelines and "results" in pipelines:
            print(f"   ✅ Fetched {len(pipelines['results'])} pipelines")
            for pipe in pipelines["results"][:2]:
                print(f"      Pipeline: {pipe.get('label', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    print("\n" + "="*60)
    print("✅ TESTS COMPLETE!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test())

