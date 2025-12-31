"""
Pydantic models for Memo entities
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class MemoExtraction(BaseModel):
    """Extracted CRM data from transcript"""
    
    # Deal Information
    companyName: Optional[str] = None
    dealAmount: Optional[float] = None
    dealCurrency: str = "EUR"
    dealStage: Optional[str] = None
    closeDate: Optional[str] = None  # ISO format YYYY-MM-DD
    
    # Contact Information
    contactName: Optional[str] = None
    contactRole: Optional[str] = None
    contactEmail: Optional[str] = None
    contactPhone: Optional[str] = None
    
    # Meeting Intelligence
    summary: str = ""
    painPoints: List[str] = Field(default_factory=list)
    nextSteps: List[str] = Field(default_factory=list)
    competitors: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    decisionMakers: List[str] = Field(default_factory=list)
    
    # Confidence
    confidence: dict = Field(default_factory=lambda: {"overall": 0.0, "fields": {}})


class TranscriptionResult(BaseModel):
    """Result from Deepgram transcription"""
    transcript: str
    confidence: float = Field(ge=0.0, le=1.0)
    duration: float  # seconds


class MemoBase(BaseModel):
    """Base memo model"""
    audioUrl: str
    audioDuration: float
    status: str


class MemoCreate(MemoBase):
    """Model for creating a new memo"""
    userId: str


class MemoUpdate(BaseModel):
    """Model for updating memo fields"""
    status: Optional[str] = None
    transcript: Optional[str] = None
    transcriptConfidence: Optional[float] = None
    extraction: Optional[MemoExtraction] = None
    errorMessage: Optional[str] = None
    processedAt: Optional[datetime] = None
    approvedAt: Optional[datetime] = None


class Memo(MemoBase):
    """Full memo model returned by API"""
    id: UUID
    userId: str
    transcript: Optional[str] = None
    transcriptConfidence: Optional[float] = None
    extraction: Optional[MemoExtraction] = None
    errorMessage: Optional[str] = None
    createdAt: datetime
    processedAt: Optional[datetime] = None
    approvedAt: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    """Response from upload endpoint"""
    id: str
    status: str
    statusUrl: str


class ApproveMemoRequest(BaseModel):
    """Request body for approving a memo"""
    deal_id: Optional[str] = Field(None, description="Deal ID to update (None = create new)")
    is_new_deal: bool = Field(default=False, description="Whether to create a new deal")
    extraction: Optional[MemoExtraction] = None

