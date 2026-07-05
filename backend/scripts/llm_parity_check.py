#!/usr/bin/env python3
"""
Smoke test for LLM router: chat_json with a fixed prompt.

Usage (from backend/):
  LLM_PROVIDER=openrouter python scripts/llm_parity_check.py
  LLM_PROVIDER=vertex_ai python scripts/llm_parity_check.py

Requires credentials for the active provider (OPENROUTER_API_KEY or GCP ADC).
"""

import asyncio
import json
import os
import sys

# Ensure backend app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services.llm import LLMClient, get_compliance_info


PROMPT_MESSAGES = [
    {
        "role": "system",
        "content": "You output only valid JSON with no markdown.",
    },
    {
        "role": "user",
        "content": 'Return JSON: {"status": "ok", "provider_test": true}',
    },
]


async def main() -> int:
    provider = settings.LLM_PROVIDER
    print(f"LLM_PROVIDER={provider}")
    print(f"Compliance: {json.dumps(get_compliance_info(provider), indent=2)}")

    client = LLMClient()
    try:
        result = await client.chat_json(PROMPT_MESSAGES, temperature=0.0)
    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    if not isinstance(result, dict):
        print(f"FAIL: expected dict, got {type(result)}", file=sys.stderr)
        return 1

    print(f"OK: {json.dumps(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
