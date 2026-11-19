"""What this backend can do right now (#66).

The app uses it to decide whether to show AI features such as Explore.
It requires the API token so configuration is not exposed through the
public /api/health.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from stock_manager.api import ai_client

router = APIRouter()


class AICapabilities(BaseModel):
    text: bool  # Explore / Expand (and text intake, #63)
    vision: bool = False  # image input, set by #63 phase 2
    asr: bool = False  # speech transcription, set by #32


class CapabilitiesResponse(BaseModel):
    ai: AICapabilities


@router.get("", response_model=CapabilitiesResponse)
def capabilities():
    """Which optional features are available."""
    config = ai_client.get_config()
    return CapabilitiesResponse(ai=AICapabilities(text=config.available, vision=config.vision_available))
