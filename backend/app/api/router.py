"""
Main API router combining all route modules
"""

from fastapi import APIRouter
from app.api import health, memos, crm, transcription, auth, glossary

api_router = APIRouter()

# Include all route modules
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(memos.router)
api_router.include_router(crm.router)
api_router.include_router(transcription.router)
api_router.include_router(glossary.router)


