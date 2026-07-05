"""
LLM service layer.
Centralized handling for chat completions, structured extraction, and text generation.
"""

from .client import LLMClient
from .compliance import get_compliance_info
from .router import LLMRouter

__all__ = ["LLMClient", "LLMRouter", "get_compliance_info"]
