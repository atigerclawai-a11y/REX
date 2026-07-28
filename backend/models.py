"""
REX — Pydantic data models
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    journey_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    secure: bool = False
    phi_detected: bool = False
    model: Optional[str] = None
    system_prompt: Optional[str] = None

class Journey(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    title: Optional[str] = None
    message_count: int = 0
    secure_mode: bool = False


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: str
    details: Dict[str, Any] = {}


class SendMessageRequest(BaseModel):
    content: str
    model: str = "anthropic/claude-sonnet-4-5"
    journey_id: Optional[str] = None


class SecureModeRequest(BaseModel):
    enabled: bool


class ProviderModel(BaseModel):
    id: str          # e.g. "anthropic/claude-opus-4-5"
    name: str        # Display name
    provider: str    # "anthropic" | "openai" | "google" | "xai" | "ollama"
    local: bool = False  # True for Ollama
    available: bool = True


class JourneyExport(BaseModel):
    journey: Journey
    messages: List[ChatMessage]
    audit_events: List[AuditEvent]
