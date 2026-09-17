"""
Main API router combining all route modules
"""

from fastapi import APIRouter
from app.api import (
    health,
    memos,
    crm,
    crm_salesforce,
    crm_pipedrive,
    transcription,
    auth,
    glossary,
    webhooks,
    stripe_webhooks,
    billing,
    copilot,
    voice_enrollment,
    admin,
    calls,
    hubspot_recordings,
    company,
)

api_router = APIRouter()

# Include all route modules
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(company.router)
api_router.include_router(billing.router)
api_router.include_router(memos.router)
api_router.include_router(crm.router)
api_router.include_router(calls.router)
api_router.include_router(hubspot_recordings.router)
api_router.include_router(crm_salesforce.router, prefix="/api/v1/crm")
api_router.include_router(crm_pipedrive.router, prefix="/api/v1/crm")
api_router.include_router(transcription.router)
api_router.include_router(glossary.router)
api_router.include_router(webhooks.router, prefix="/webhooks")
api_router.include_router(stripe_webhooks.router, prefix="/webhooks")
api_router.include_router(copilot.router)
api_router.include_router(voice_enrollment.router)
api_router.include_router(admin.router)


