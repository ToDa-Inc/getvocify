"""
Main API router combining all route modules
"""

from fastapi import APIRouter
from app.api import health, memos

api_router = APIRouter()

# Include all route modules
api_router.include_router(health.router)
api_router.include_router(memos.router)


