"""Data contracts and Pydantic DTOs shared across all microservices."""
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


import uuid

# -------------------------------------------------------------------
# 1. Gateway & Client Inquiries
# -------------------------------------------------------------------
class QueryRequest(BaseModel):
    """Client request sent to the API Gateway."""
    query: str = Field(..., description="Customer message or inquiry text")
    session_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique conversation session ID")
    customer_id: Optional[str] = Field(default=None, description="Optional customer account ID")


# -------------------------------------------------------------------
# 2. Intent Classification Service Contracts
# -------------------------------------------------------------------
class IntentPredictionRequest(BaseModel):
    """Payload for intent prediction."""
    query: str = Field(..., description="User query to classify")


class IntentPredictionResponse(BaseModel):
    """Prediction output from intent_service."""
    intent: str = Field(..., description="Predicted intent name")
    confidence: float = Field(ge=0.0, le=1.0, description="Prediction confidence score")
    is_in_scope: bool = Field(..., description="Whether intent belongs to operational scope")
    language: Optional[str] = None
    model_name: Optional[str] = None
    latency_ms: Optional[float] = Field(default=None, ge=0)
    all_probabilities: Dict[str, float] = Field(
        default_factory=dict,
        description="Probability distribution across candidate classes"
    )


# -------------------------------------------------------------------
# 3. Knowledge Base & RAG Contracts
# -------------------------------------------------------------------
class RetrievedDocument(BaseModel):
    """Policy or knowledge base document item.

    policy_type distinguishes two categories:
      - "permanent"  : Standard operational policies with no fixed end date.
                       expiration_date is null; only is_active=False blocks it.
      - "temporary"  : Time-bound campaigns or promotions.  Both effective_date
                       and expiration_date MUST be set and are checked strictly.
      - "superseded" : Old version of a permanent policy, replaced by a newer
                       version.  Always treated as inactive regardless of dates.
    """
    doc_id: str = Field(..., description="Unique document / policy ID")
    category: Optional[str] = Field(default=None, description="Policy category (e.g. return_refund, shipping, payment, promotions, support, warranty)")
    title: str = Field(..., description="Document title")
    content: str = Field(..., description="Policy body / chunk content")
    version: str = Field(default="1.0", description="Document version")
    is_active: bool = Field(..., description="Active status of this document")
    policy_type: str = Field(
        default="permanent",
        description="Policy type: 'permanent' | 'temporary' | 'superseded'",
    )
    effective_date: Optional[str] = Field(default=None, description="ISO effective start date (YYYY-MM-DD)")
    expiration_date: Optional[str] = Field(default=None, description="ISO expiration end date (YYYY-MM-DD). Null for permanent policies.")
    tags: List[str] = Field(default_factory=list, description="Associated policy tags")
    score: Optional[float] = Field(default=None, description="Relevance similarity score")


class RAGRetrieveRequest(BaseModel):
    """Request payload for RAG retrieval."""
    query: str = Field(..., description="Query string for search")
    intent: Optional[str] = Field(default=None, description="Contextual intent for retrieval")
    top_k: int = Field(default=3, ge=1, le=10, description="Top K candidate documents to retrieve")
    filter_active_only: bool = Field(default=False, description="Filter out expired (is_active=False) documents")


class RAGGenerateRequest(BaseModel):
    """Request payload for LLM draft generation."""
    query: str = Field(..., description="Original customer query")
    citations: List[RetrievedDocument] = Field(..., description="List of validated policy documents to cite")


class RAGGenerateResponse(BaseModel):
    draft_text: str
    citations: List[RetrievedDocument] = Field(default_factory=list)
    latency_ms: int = Field(ge=0)
    generation_mode: str = "unknown"
    fallback_reason: Optional[str] = None


# -------------------------------------------------------------------
# 4. Guardrail & Policy Routing Contracts
# -------------------------------------------------------------------
class GuardrailResult(BaseModel):
    """Decision evaluated by API Gateway guardrail checks."""
    allow_llm: bool = Field(..., description="Whether generation with LLM is permitted")
    action_type: str = Field(..., description="Action: PROCEED_TO_LLM, DIRECT_REFUND_FORM, ESCALATE_HUMAN")
    reason: str = Field(..., description="Audit rationale explaining the decision")
    faithfulness_score: Optional[float] = Field(default=None, description="Response faithfulness / NLI entailment score (0.0 to 1.0)")
    hallucination_detected: Optional[bool] = Field(default=None, description="Whether hallucination was detected in response")
    temporal_status: Optional[str] = Field(default=None, description="Temporal status: ACTIVE, EXPIRED, NOT_YET_EFFECTIVE")


# -------------------------------------------------------------------
# 5. Telemetry & Audit Contracts
# -------------------------------------------------------------------
class AuditLogCreate(BaseModel):
    """Initial interaction telemetry log to persist."""
    interaction_id: str = Field(..., description="Unique UUID trace ID")
    customer_query: str = Field(..., description="Customer input text")
    predicted_intent: str = Field(..., description="Predicted intent")
    intent_confidence: float = Field(..., description="Confidence score")
    guardrail_action: str = Field(..., description="Guardrail action chosen")
    retrieved_doc_ids: str = Field(..., description="Comma-separated cited document IDs")
    raw_draft_text: str = Field(..., description="Generated draft text")
    latency_ms: int = Field(default=0, ge=0, description="End-to-end processing latency")


class HumanActionUpdate(BaseModel):
    """CS Support agent action recorded on a draft."""
    interaction_id: str = Field(..., description="Target interaction ID")
    action: Literal["APPROVE", "EDIT", "REJECT", "ESCALATE"]
    final_text: Optional[str] = Field(default=None, description="Final sent text after agent edit")
    agent_notes: Optional[str] = Field(default=None, description="Agent notes")
    handling_time_ms: int = Field(default=0, ge=0, description="Time spent by agent in milliseconds")


# -------------------------------------------------------------------
# 6. Gateway End-to-End Response
# -------------------------------------------------------------------
class GatewayResponse(BaseModel):
    """Final unified response returned by API Gateway to UI."""
    interaction_id: str = Field(..., description="Interaction trace ID")
    intent: IntentPredictionResponse = Field(..., description="Intent classification result")
    guardrail: GuardrailResult = Field(..., description="Guardrail decision")
    citations: List[RetrievedDocument] = Field(default_factory=list, description="Policy citations")
    draft_text: str = Field(..., description="Generated draft response")
    order_data: Optional[Dict[str, Any]] = Field(default=None, description="Mock order data for financial reviews")
    generation_mode: str = "not_generated"

# -------------------------------------------------------------------
# 7. Policy Filter & Creation Contracts
# -------------------------------------------------------------------

class RawPolicyFilterRequest(BaseModel):
    """Payload containing raw policy text supplied by staff."""
    raw_text: str = Field(..., description="Unstructured policy text to be parsed")
    suggested_category: Optional[str] = Field(default=None, description="Optional hint for category")
    gemini_api_key: Optional[str] = Field(default=None, description="Optional Gemini API key passed from UI/caller")

class PolicyFilterResult(BaseModel):
    """Result of automatic extraction, ready for human review/edit."""
    extracted_policy: RetrievedDocument
    warnings: List[str] = Field(default_factory=list, description="Extraction or validation warnings")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence of automatic parsing")

class PolicyCreateRequest(BaseModel):
    """Final payload to persist a new policy after human confirmation."""
    policy: RetrievedDocument
    admin_note: Optional[str] = None
    performed_by: Optional[str] = "Admin"
    reason: Optional[str] = None


class PolicyUpdateRequest(BaseModel):
    """Payload to partially update an existing policy with audit tracking."""
    updates: Dict[str, Any]
    performed_by: Optional[str] = "Admin"
    reason: Optional[str] = None


class PolicyAuditLogEntry(BaseModel):
    """Audit log entry capturing policy lifecycle changes for traceability and rollback."""
    log_id: str
    timestamp: str
    doc_id: str
    action: str  # "CREATE", "UPDATE", "SUPERSEDE", "ROLLBACK"
    performed_by: str = "Admin"
    reason: Optional[str] = None
    before_snapshot: Optional[Dict[str, Any]] = None
    after_snapshot: Optional[Dict[str, Any]] = None


class PolicyRollbackRequest(BaseModel):
    """Request to rollback a policy to a prior version/state based on an audit log ID."""
    log_id: str
    performed_by: Optional[str] = "Admin"
    reason: Optional[str] = None

