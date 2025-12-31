"""
Test script for HubSpot integration endpoints.

Run this to verify the HubSpot service layer works correctly.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from app.services.hubspot import (
    HubSpotClient,
    HubSpotValidationService,
    HubSpotSchemaService,
)


async def test_hubspot():
    """Test HubSpot integration"""
    
    # Get access token from environment
    access_token = os.getenv("HUBSPOT_DEVELOPER_API_KEY") or os.getenv("HUBSPOT_ACCESS_TOKEN")
    
    if not access_token:
        print("❌ ERROR: HUBSPOT_DEVELOPER_API_KEY or HUBSPOT_ACCESS_TOKEN not found in .env")
        return
    
    print(f"✅ Found access token: {access_token[:20]}...")
    print("\n" + "="*60)
    print("TESTING HUBSPOT INTEGRATION")
    print("="*60 + "\n")
    
    # Initialize client
    client = HubSpotClient(access_token)
    
    # Test 1: Token Validation
    print("1️⃣ Testing token validation...")
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
        return
    
    print()
    
    # Test 2: Get Deal Schema
    print("2️⃣ Testing schema fetching (deals)...")
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
    
    print()
    
    # Test 3: Test basic API call
    print("3️⃣ Testing basic API call (get account info)...")
    try:
        account_info = await client.get("/integrations/v1/me")
        if account_info:
            print(f"   ✅ API call successful!")
            print(f"   📧 Portal ID: {account_info.get('portalId', 'N/A')}")
        else:
            print(f"   ⚠️  Empty response")
    except Exception as e:
        print(f"   ❌ API call error: {str(e)}")
    
    print()
    print("="*60)
    print("✅ ALL TESTS COMPLETE!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(test_hubspot())

