"""
LLM service layer.
Centralized handling for chat completions, structured extraction, and text generation.
"""

from .client import LLMClient

__all__ = ["LLMClient"]
