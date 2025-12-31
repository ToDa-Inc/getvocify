"""
Direct test script for HubSpot integration.

Tests HubSpot service layer by importing directly from module files.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend/app/services/hubspot to path
backend_dir = Path(__file__).parent
hubspot_dir = backend_dir / "app" / "services" / "hubspot"
sys.path.insert(0, str(hubspot_dir.parent.parent.parent))  # Add backend to path

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv(backend_dir.parent / ".env")
except ImportError:
    # Fallback: read .env manually
    env_file = backend_dir.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")

# Import directly from hubspot modules
from app.services.hubspot.client import HubSpotClient
from app.services.hubspot.validation import HubSpotValidationService
from app.services.hubspot.schema import HubSpotSchemaService


async def test_hubspot():
    """Test HubSpot integration"""
    
    # Get access token from environment
    access_token = os.getenv("HUBSPOT_DEVELOPER_API_KEY") or os.getenv("HUBSPOT_ACCESS_TOKEN")
    
    if not access_token:
        print("❌ ERROR: HUBSPOT_DEVELOPER_API_KEY or HUBSPOT_ACCESS_TOKEN not found in .env")
        print("\nPlease add one of these to your .env file:")
        print("  HUBSPOT_DEVELOPER_API_KEY=pat-na1-...")
        print("  or")
        print("  HUBSPOT_ACCESS_TOKEN=pat-na1-...")
        return
    
    print(f"✅ Found access token: {access_token[:20]}...")
    print("\n" + "="*60)
    print("TESTING HUBSPOT INTEGRATION")
    print("="*60 + "\n")
    
    # Initialize client
    try:
        client = HubSpotClient(access_token)
        print("✅ Client initialized")
    except Exception as e:
        print(f"❌ Failed to create client: {str(e)}")
        import traceback
        traceback.print_exc()
        return
    
    # Test 1: Token Validation
    print("\n1️⃣ Testing token validation...")
    try:
        validation_service = HubSpotValidationService(client)
        result = await validation_service.validate()
        
        if result.valid:
            print(f"   ✅ Token is valid!")
            print(f"   📊 Portal ID: {result.portal_id}")
            print(f"   🔑 Scopes OK: {result.scopes_ok}")
        else:
            print(f"   ❌ Token validation failed: {result.error}")
            print(f"   🔍 Error code: {result.error_code}")
            return
    except Exception as e:
        print(f"   ❌ Validation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return
    
    # Test 2: Get Deal Schema
    print("\n2️⃣ Testing schema fetching (deals)...")
    try:
        schema_service = HubSpotSchemaService(client)
        schema = await schema_service.get_deal_schema()
        
        print(f"   ✅ Schema fetched successfully!")
        print(f"   📋 Properties: {len(schema.properties)}")
        print(f"   🎯 Pipelines: {len(schema.pipelines)}")
        
        # Show some property examples
        if schema.properties:
            print(f"\n   Sample properties:")
            for prop in schema.properties[:5]:
                print(f"      - {prop.name} ({prop.type})")
        
        # Show pipeline stages
        if schema.pipelines:
            print(f"\n   Pipeline stages:")
            for pipeline in schema.pipelines[:2]:
                print(f"      Pipeline: {pipeline.label}")
                for stage in pipeline.stages[:3]:
                    print(f"         - {stage.label} (ID: {stage.id})")
        
    except Exception as e:
        print(f"   ❌ Schema fetch error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Test 3: Test basic API call
    print("\n3️⃣ Testing basic API call (get account info)...")
    try:
        account_info = await client.get("/integrations/v1/me")
        if account_info:
            print(f"   ✅ API call successful!")
            print(f"   📧 Portal ID: {account_info.get('portalId', 'N/A')}")
        else:
            print(f"   ⚠️  Empty response")
    except Exception as e:
        print(f"   ❌ API call error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETE!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_hubspot())

