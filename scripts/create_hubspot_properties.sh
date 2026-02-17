#!/bin/bash
# Create custom HubSpot Deal properties via API
# Requires: HUBSPOT_ACCESS_TOKEN or HUBSPOT_DEVELOPER_API_KEY in .env
# Add to .env: HUBSPOT_ACCESS_TOKEN=pat-na1-xxxx (from HubSpot Private App)

set -e
cd "$(dirname "$0")/.."

# Load token from .env
if [ -f .env ]; then
  set -a
  source .env 2>/dev/null || true
  set +a
fi

TOKEN="${HUBSPOT_ACCESS_TOKEN:-$HUBSPOT_DEVELOPER_API_KEY}"
if [ -z "$TOKEN" ]; then
  echo "❌ ERROR: HUBSPOT_ACCESS_TOKEN or HUBSPOT_DEVELOPER_API_KEY not found in .env"
  echo "   Add your HubSpot Private App token to .env:"
  echo "   HUBSPOT_ACCESS_TOKEN=pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  exit 1
fi

# Use EU endpoint for pat-eu1-* tokens
if [[ "$TOKEN" == pat-eu1-* ]]; then
  BASE_URL="https://api-eu1.hubapi.com"
else
  BASE_URL="https://api.hubapi.com"
fi
OBJECT_TYPE="deals"
GROUP="dealinformation"

echo "✅ Using token: ${TOKEN:0:20}..."
echo ""

# 1. Total employees (number)
echo "1️⃣ Creating: Total employees"
curl -s -X POST "$BASE_URL/crm/v3/properties/$OBJECT_TYPE" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "groupName": "'"$GROUP"'",
    "name": "total_employees",
    "label": "Total employees",
    "type": "number",
    "fieldType": "number"
  }' | jq -r '.name // .message // .' 2>/dev/null || echo "Response above"
echo ""

# 2. Deal ftes (Active) (number)
echo "2️⃣ Creating: Deal ftes (Active)"
curl -s -X POST "$BASE_URL/crm/v3/properties/$OBJECT_TYPE" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "groupName": "'"$GROUP"'",
    "name": "deal_ftes_active",
    "label": "Deal ftes (Active)",
    "type": "number",
    "fieldType": "number"
  }' | jq -r '.name // .message // .' 2>/dev/null || echo "Response above"
echo ""

# 3. Provider (text)
echo "3️⃣ Creating: Provider"
curl -s -X POST "$BASE_URL/crm/v3/properties/$OBJECT_TYPE" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "groupName": "'"$GROUP"'",
    "name": "provider",
    "label": "Provider",
    "type": "string",
    "fieldType": "text"
  }' | jq -r '.name // .message // .' 2>/dev/null || echo "Response above"
echo ""

# 4. Contracted product (select enum)
echo "4️⃣ Creating: Contracted product"
curl -s -X POST "$BASE_URL/crm/v3/properties/$OBJECT_TYPE" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "groupName": "'"$GROUP"'",
    "name": "contracted_product",
    "label": "Contracted product",
    "type": "enumeration",
    "fieldType": "select",
    "options": [
      {"label": "Flexible retribution", "value": "flexible_retribution", "displayOrder": 1},
      {"label": "Social benefit", "value": "social_benefit", "displayOrder": 2},
      {"label": "Hybris", "value": "hybris", "displayOrder": 3},
      {"label": "Full hybrid", "value": "full_hybrid", "displayOrder": 4},
      {"label": "HI new quote", "value": "hi_new_quote", "displayOrder": 5},
      {"label": "HI migration", "value": "hi_migration", "displayOrder": 6},
      {"label": "Flexpay", "value": "flexpay", "displayOrder": 7},
      {"label": "Budgets", "value": "budgets", "displayOrder": 8}
    ]
  }' | jq -r '.name // .message // .' 2>/dev/null || echo "Response above"
echo ""

# 5. ES Hi provider (select enum)
echo "5️⃣ Creating: ES Hi provider"
curl -s -X POST "$BASE_URL/crm/v3/properties/$OBJECT_TYPE" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "groupName": "'"$GROUP"'",
    "name": "es_hi_provider",
    "label": "ES Hi provider",
    "type": "enumeration",
    "fieldType": "select",
    "options": [
      {"label": "None", "value": "none", "displayOrder": 1},
      {"label": "Adeslas", "value": "adeslas", "displayOrder": 2},
      {"label": "Agrupacio", "value": "agrupacio", "displayOrder": 3},
      {"label": "Alan", "value": "alan", "displayOrder": 4},
      {"label": "Asisa", "value": "asisa", "displayOrder": 5},
      {"label": "Axa", "value": "axa", "displayOrder": 6},
      {"label": "Cigna", "value": "cigna", "displayOrder": 7},
      {"label": "DKV", "value": "dkv", "displayOrder": 8},
      {"label": "Mapfre", "value": "mapfre", "displayOrder": 9},
      {"label": "Sanitas", "value": "sanitas", "displayOrder": 10},
      {"label": "Other", "value": "other", "displayOrder": 11}
    ]
  }' | jq -r '.name // .message // .' 2>/dev/null || echo "Response above"
echo ""

# 6. Broker (select enum)
echo "6️⃣ Creating: Broker"
curl -s -X POST "$BASE_URL/crm/v3/properties/$OBJECT_TYPE" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "groupName": "'"$GROUP"'",
    "name": "broker",
    "label": "Broker",
    "type": "enumeration",
    "fieldType": "select",
    "options": [
      {"label": "No broker", "value": "no_broker", "displayOrder": 1},
      {"label": "None", "value": "none", "displayOrder": 2},
      {"label": "AON", "value": "aon", "displayOrder": 3},
      {"label": "Asterra", "value": "asterra", "displayOrder": 4},
      {"label": "Bankjssurance", "value": "bankjssurance", "displayOrder": 5},
      {"label": "BMS", "value": "bms", "displayOrder": 6},
      {"label": "Howden", "value": "howden", "displayOrder": 7},
      {"label": "Isalud", "value": "isalud", "displayOrder": 8},
      {"label": "Jhasa", "value": "jhasa", "displayOrder": 9},
      {"label": "Jori", "value": "jori", "displayOrder": 10},
      {"label": "Mercer", "value": "mercer", "displayOrder": 11},
      {"label": "WTW", "value": "wtw", "displayOrder": 12},
      {"label": "Other", "value": "other", "displayOrder": 13},
      {"label": "No health insurance/no broker", "value": "no_health_insurance_no_broker", "displayOrder": 14}
    ]
  }' | jq -r '.name // .message // .' 2>/dev/null || echo "Response above"
echo ""

# 7. Benefit provider (select enum)
echo "7️⃣ Creating: Benefit provider"
curl -s -X POST "$BASE_URL/crm/v3/properties/$OBJECT_TYPE" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "groupName": "'"$GROUP"'",
    "name": "benefit_provider",
    "label": "Benefit provider",
    "type": "enumeration",
    "fieldType": "select",
    "options": [
      {"label": "Alan", "value": "alan", "displayOrder": 1},
      {"label": "Aon", "value": "aon", "displayOrder": 2},
      {"label": "Betterfly", "value": "betterfly", "displayOrder": 3},
      {"label": "Cobee", "value": "cobee", "displayOrder": 4},
      {"label": "Compensa", "value": "compensa", "displayOrder": 5},
      {"label": "Pluxee", "value": "pluxee", "displayOrder": 6},
      {"label": "Edenred", "value": "edenred", "displayOrder": 7},
      {"label": "Factorial", "value": "factorial", "displayOrder": 8},
      {"label": "Mercer", "value": "mercer", "displayOrder": 9},
      {"label": "Payflow", "value": "payflow", "displayOrder": 10},
      {"label": "Retriplus", "value": "retriplus", "displayOrder": 11},
      {"label": "Sesame", "value": "sesame", "displayOrder": 12},
      {"label": "WTW", "value": "wtw", "displayOrder": 13},
      {"label": "Other", "value": "other", "displayOrder": 14}
    ]
  }' | jq -r '.name // .message // .' 2>/dev/null || echo "Response above"
echo ""

# 8. Meal provider (same options as Benefit provider)
echo "8️⃣ Creating: Meal provider"
curl -s -X POST "$BASE_URL/crm/v3/properties/$OBJECT_TYPE" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "groupName": "'"$GROUP"'",
    "name": "meal_provider",
    "label": "Meal provider",
    "description": "Same as benefit provider",
    "type": "enumeration",
    "fieldType": "select",
    "options": [
      {"label": "Alan", "value": "alan", "displayOrder": 1},
      {"label": "Aon", "value": "aon", "displayOrder": 2},
      {"label": "Betterfly", "value": "betterfly", "displayOrder": 3},
      {"label": "Cobee", "value": "cobee", "displayOrder": 4},
      {"label": "Compensa", "value": "compensa", "displayOrder": 5},
      {"label": "Pluxee", "value": "pluxee", "displayOrder": 6},
      {"label": "Edenred", "value": "edenred", "displayOrder": 7},
      {"label": "Factorial", "value": "factorial", "displayOrder": 8},
      {"label": "Mercer", "value": "mercer", "displayOrder": 9},
      {"label": "Payflow", "value": "payflow", "displayOrder": 10},
      {"label": "Retriplus", "value": "retriplus", "displayOrder": 11},
      {"label": "Sesame", "value": "sesame", "displayOrder": 12},
      {"label": "WTW", "value": "wtw", "displayOrder": 13},
      {"label": "Other", "value": "other", "displayOrder": 14}
    ]
  }' | jq -r '.name // .message // .' 2>/dev/null || echo "Response above"
echo ""

# 9. Competitor price (number)
echo "9️⃣ Creating: Competitor price"
curl -s -X POST "$BASE_URL/crm/v3/properties/$OBJECT_TYPE" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "groupName": "'"$GROUP"'",
    "name": "competitor_price",
    "label": "Competitor price",
    "type": "number",
    "fieldType": "number"
  }' | jq -r '.name // .message // .' 2>/dev/null || echo "Response above"
echo ""

echo "✅ Done! Properties created (or already existed)."
echo "   If you see 'Property already exists' errors, the properties are already in HubSpot."
