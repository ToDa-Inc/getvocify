"""
Pydantic models for API requests/responses
"""

from .memo import (
    Memo,
    MemoCreate,
    MemoUpdate,
    MemoExtraction,
    TranscriptionResult,
    UploadResponse,
    ApproveMemoRequest,
)
from .crm_update import (
    CRMUpdate,
    CRMUpdateCreate,
    CRMUpdateUpdate,
)

__all__ = [
    "Memo",
    "MemoCreate",
    "MemoUpdate",
    "MemoExtraction",
    "TranscriptionResult",
    "UploadResponse",
    "ApproveMemoRequest",
    "CRMUpdate",
    "CRMUpdateCreate",
    "CRMUpdateUpdate",
]

