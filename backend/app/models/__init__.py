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
from .hubspot import (
    ConnectHubSpotRequest,
    ConnectHubSpotResponse,
    TestConnectionResponse,
    HubSpotConnection,
    CreateDealRequest,
    UpdateDealRequest,
)
from .crm_config import (
    CRMConfigurationRequest,
    CRMConfigurationResponse,
    PipelineOption,
    StageOption,
)
from .approval import (
    DealMatch,
    ProposedUpdate,
    ApprovalPreview,
    ApproveRequest,
)
from .conversation import (
    Conversation,
    ConversationMessage,
    ConversationState,
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
    "ConnectHubSpotRequest",
    "ConnectHubSpotResponse",
    "TestConnectionResponse",
    "HubSpotConnection",
    "CreateDealRequest",
    "UpdateDealRequest",
    "CRMConfigurationRequest",
    "CRMConfigurationResponse",
    "PipelineOption",
    "StageOption",
    "DealMatch",
    "ProposedUpdate",
    "ApprovalPreview",
    "ApproveRequest",
    "Conversation",
    "ConversationMessage",
    "ConversationState",
]

