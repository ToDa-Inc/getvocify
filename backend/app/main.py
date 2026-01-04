"""
FastAPI application entry point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from app.config import settings
from app.api.router import api_router
import asyncio


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add 30s timeout to requests.
    
    Excludes:
    - /transcription endpoints (can take longer for real-time transcription)
    - /memos/upload endpoints (file uploads can take time)
    """
    
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Skip timeout for transcription and upload endpoints
        if "/transcription" in path or "/memos/upload" in path:
            return await call_next(request)
        
        # Apply 30s timeout to other endpoints
        try:
            response = await asyncio.wait_for(call_next(request), timeout=30.0)
            return response
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"detail": "Request timeout after 30s"}
            )


app = FastAPI(
    title="Vocify API",
    description="Voice to CRM in 60 seconds",
    version="0.1.0",
)

# Timeout middleware (30s for most endpoints, except transcription/upload)
app.add_middleware(TimeoutMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://localhost:3000",
        # Chrome extension origins (any extension ID)
        "chrome-extension://*",
    ],
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Vocify API",
        "version": "0.1.0",
        "status": "running"
    }


