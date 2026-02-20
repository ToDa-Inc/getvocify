"""
Real-time transcription WebSocket endpoint
Proxies audio stream to Speechmatics (Deepgram disabled)
"""

import asyncio
import json
import logging
import ssl
import os
import certifi
from typing import Optional, List

# GLOBAL SURGICAL FIX: Force use of certifi certificates for macOS
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['WEBSOCKETS_CA_BUNDLE'] = certifi.where()

# THE NUCLEAR OPTION: Monkey-patch the ssl module's default context creation
# This forces every library (including websockets) to skip verification if the OS is broken
def _patched_create_default_context(*args, **kwargs):
    ctx = ssl._orig_create_default_context(*args, **kwargs)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

if not hasattr(ssl, '_orig_create_default_context'):
    ssl._orig_create_default_context = ssl.create_default_context
    ssl.create_default_context = _patched_create_default_context
    # Also patch for HTTPS specifically
    ssl._create_default_https_context = ssl._create_unverified_context

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.config import settings
from app.services.glossary import GlossaryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/transcription", tags=["transcription"])

class SpeechmaticsProxy:
    """
    Surgical Proxy for Speechmatics Real-time API.
    Handles bi-directional streaming between Client and Speechmatics.
    """
    def __init__(self, language: str = "multi", glossary: List[dict] = None):
        # Map multi to es for now as Speechmatics prefers specific codes
        self.language = "es" if language == "multi" else language
        self.glossary = glossary or []
        # ROBUST KEY FETCH: settings -> os.environ -> direct fallback
        self.api_key = (
            settings.SPEECHMATICS_API_KEY or 
            os.environ.get("SPEECHMATICS_API_KEY") or 
            os.environ.get("SPEECHNATICS_API_KEY") # Handle common typo from user query
        )
        # Use eu2 as per user's previous working project
        self.base_url = "wss://eu2.rt.speechmatics.com/v2"
        self.ws = None

    async def proxy_session(self, client_ws: WebSocket, audio_queue: asyncio.Queue):
        """
        Manages the Speechmatics session.
        """
        if not self.api_key:
            logger.error("SPEECHMATICS_API_KEY IS NOT SET IN THE BACKEND.")
            return

        # AS PER WORKING PROJECT: URL must include the language path
        # If language is multi, we default to es for Speechmatics
        target_lang = "es" if self.language == "multi" else self.language
        connection_url = f"{self.base_url}/{target_lang}"
        logger.info(f"Speechmatics connecting to: {connection_url}")

        try:
            # Connect to Speechmatics with Authorization Header
            # NOTE: For websockets v15.0.1, additional_headers is used
            async with websockets.connect(
                connection_url,
                additional_headers={"Authorization": f"Bearer {self.api_key}"}
            ) as sm_ws:
                logger.info("Speechmatics connection handshake successful")
                
                # Start Recognition Configuration
                config = {
                    "message": "StartRecognition",
                    "audio_format": {
                        "type": "raw", 
                        "encoding": "pcm_s16le", 
                        "sample_rate": 16000
                    },
                    "transcription_config": {
                        "language": target_lang,
                        "operating_point": "enhanced",
                        "diarization": "none",
                        "enable_partials": True,
                        "max_delay": 1.0,
                    }
                }
                
                # INJECT CUSTOM VOCABULARY
                if self.glossary:
                    service = GlossaryService()
                    # AS PER DOCS: Field name is 'additional_vocab'
                    config["transcription_config"]["additional_vocab"] = service.format_for_speechmatics(self.glossary)
                    logger.info(f"Injected {len(self.glossary)} glossary terms into Speechmatics")

                await sm_ws.send(json.dumps(config))
                
                # Internal state to wait for RecognitionStarted
                self.recognition_started = asyncio.Event()

                async def send_audio():
                    # Wait for recognition to officially start before streaming audio
                    await self.recognition_started.wait()
                    logger.info("Speechmatics recognition started, now streaming audio")
                    
                    while True:
                        audio_chunk = await audio_queue.get()
                        if audio_chunk is None: # Termination signal
                            await sm_ws.send(json.dumps({"message": "EndOfStream", "last_seq_no": 0}))
                            break
                        await sm_ws.send(audio_chunk)

                async def receive_transcripts():
                    async for message in sm_ws:
                        data = json.loads(message)
                        msg_type = data.get("message")
                        
                        if msg_type == "RecognitionStarted":
                            self.recognition_started.set()
                            logger.info("Speechmatics RecognitionStarted received")
                        
                        elif msg_type in ["AddPartialTranscript", "AddTranscript"]:
                            transcript = data.get("metadata", {}).get("transcript", "")
                            if transcript:
                                response = {
                                    "type": "Results",
                                    "provider": "speechmatics",
                                    "is_final": msg_type == "AddTranscript",
                                    "channel": {
                                        "alternatives": [{"transcript": transcript, "confidence": 0.99 if msg_type == "AddTranscript" else 0.5}]
                                    }
                                }
                                await client_ws.send_json(response)
                        
                        elif msg_type == "Error":
                            reason = data.get("reason", "Unknown error")
                            logger.error(f"Speechmatics error: {reason}")
                            await client_ws.send_json({
                                "type": "Error",
                                "provider": "speechmatics",
                                "error": reason
                            })
                        
                        elif msg_type == "Warning":
                            logger.warning(f"Speechmatics warning: {data.get('reason')}")

                await asyncio.gather(send_audio(), receive_transcripts())

        except Exception as e:
            logger.error(f"Speechmatics session error: {e}")
            await client_ws.send_json({
                "type": "Error",
                "provider": "speechmatics",
                "error": str(e)
            })

class SpeechmaticsOnlyProxy:
    """
    Real-time transcription via Speechmatics only (Deepgram disabled).
    """
    def __init__(self, language: str = "multi", glossary: List[dict] = None):
        self.language = language
        self.glossary = glossary or []
        self.sm_queue = asyncio.Queue()
        self.sm_proxy = SpeechmaticsProxy(language, glossary=self.glossary)

    async def proxy_session(self, client_ws: WebSocket):
        try:
            await client_ws.send_json({"type": "connected", "model": "speechmatics"})

            async def client_to_queue():
                try:
                    while True:
                        msg = await client_ws.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if "bytes" in msg:
                            await self.sm_queue.put(msg["bytes"])
                        elif "text" in msg:
                            data = json.loads(msg["text"])
                            if data.get("type") == "CloseStream":
                                break
                finally:
                    await self.sm_queue.put(None)

            await asyncio.gather(
                client_to_queue(),
                self.sm_proxy.proxy_session(client_ws, self.sm_queue)
            )

        except Exception as e:
            logger.error("Speechmatics proxy session error: %s", e)
        finally:
            logger.info("Speechmatics proxy session finished")

@router.websocket("/live")
async def live_transcription(
    websocket: WebSocket,
):
    """
    FastAPI WebSocket entry point for real-time transcription (Speechmatics).
    """
    await websocket.accept()
    language = websocket.query_params.get("language", "multi")
    user_id = websocket.query_params.get("user_id")
    
    glossary = []
    if user_id:
        try:
            glossary_service = GlossaryService()
            glossary = await glossary_service.get_user_glossary(user_id)
            logger.info("Loaded %d glossary terms for user %s", len(glossary), user_id)
        except Exception as e:
            logger.error("Failed to load glossary: %s", e)

    proxy = SpeechmaticsOnlyProxy(language=language, glossary=glossary)
    await proxy.proxy_session(websocket)
