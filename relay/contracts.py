"""Typed contracts for Project Relay using Pydantic."""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

VALID_TENANTS = {"northwind", "harbor"}

CategoryType = Literal[
    "returns_refunds",
    "shipping_delivery",
    "warranty_repair",
    "order_change",
    "billing_payments",
    "assembly_setup",
    "appointments",
    "records_privacy",
    "clinical",
    "other",
]

PriorityType = Literal["urgent", "high", "normal", "low"]
ActionType = Literal["draft_reply", "ask_for_info", "escalate"]
StatusType = Literal["pending_approval", "escalated", "held_budget", "failed"]

class TicketInput(BaseModel):
    id: str
    tenant: str
    customer_ref: str = "unknown"
    subject: str = ""
    body: str = ""
    received_at: str

    @field_validator("tenant")
    @classmethod
    def validate_tenant(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in VALID_TENANTS:
            raise ValueError(f"Unknown tenant '{v}'. Must be one of {VALID_TENANTS} (fail-closed).")
        return clean

class TriageResult(BaseModel):
    category: CategoryType
    priority: PriorityType
    injection_detected: bool = False
    action: ActionType
    reasoning: Optional[str] = None

class KBPassage(BaseModel):
    kb_id: str
    title: str
    text: str
    score: float = 0.0

class DraftResult(BaseModel):
    action: ActionType
    draft_reply: Optional[str] = None
    kb_refs: List[str] = Field(default_factory=list)

class CheckerResult(BaseModel):
    passed: bool
    reasons: List[str] = Field(default_factory=list)

class DecisionRecord(BaseModel):
    ticket_id: str
    tenant: str
    run_id: str
    category: CategoryType
    priority: PriorityType
    action: ActionType
    injection_detected: bool
    kb_refs: List[str]
    draft_reply: Optional[str]
    status: StatusType
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int

class OutboxRecord(BaseModel):
    ticket_id: str
    tenant: str
    text: str
    approved_by: str
    approved_at: str
    idempotency_key: str

class CaseRecord(BaseModel):
    ticket_id: str
    tenant: str
    owner: str
    severity: PriorityType
    reason: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
