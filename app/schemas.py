from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
import datetime

# --- Existing Research & Knowledge Schemas (Maintained for Backward Compatibility) ---

class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    include_web: bool = True
    include_knowledge_base: bool = True
    top_k: int = Field(5, ge=1, le=10)

class Source(BaseModel):
    title: str
    url: str
    source_type: str = "web"

class RetrievedDocument(BaseModel):
    document_id: str
    filename: str
    chunk_id: str
    text: str
    relevance_score: Optional[float] = None

class ResearchResponse(BaseModel):
    status: str
    answer: str
    sources: List[Source] = []
    citations: List[str] = []
    retrieved_documents: List[RetrievedDocument] = []
    confidence: str
    limitations: List[str] = []

class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    top_k: int = Field(5, ge=1, le=10)
    user_roles: Optional[List[str]] = None
    user_id: Optional[str] = None
    max_classification: Optional[str] = None

class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    chunks_added: int
    status: str
    classification: str = "public"
    access_roles: List[str] = []


# --- Master Agent & Orchestration Schemas ---

class SubTaskType(str, Enum):
    RESEARCH = "research"
    KNOWLEDGE_BASE = "knowledge_base"
    DOMAIN_ANALYSIS = "domain_analysis"
    COUNTER_ANALYSIS = "counter_analysis"

class SubTaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class SubTask(BaseModel):
    id: str
    title: str
    task_type: SubTaskType
    description: str
    query: str
    assigned_agent: str
    status: SubTaskStatus = SubTaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None

class TaskPlan(BaseModel):
    task_id: str
    original_query: str
    intent_clarification_needed: bool = False
    clarification_prompt: Optional[str] = None
    detected_domain: str = "general"
    subtasks: List[SubTask] = []
    estimated_effort: str = "medium"
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


# --- Evidence Verification & Rubric Schemas ---

class ClaimRelationship(str, Enum):
    SUPPORTS = "supports"
    PARTIALLY_SUPPORTS = "partially_supports"
    CONTRADICTS = "contradicts"
    DOES_NOT_ADDRESS = "does_not_address"

class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    PARTIALLY_SUPPORTED = "partially_supported"
    DISPUTED = "disputed"
    UNVERIFIED = "unverified"

class EvidenceItem(BaseModel):
    source_title: str
    url_or_id: str
    source_type: str = "web"  # "web", "knowledge_base", "analysis"
    publication_date: Optional[str] = None
    retrieved_date: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"))
    passage: str
    authority_level: str = "medium"  # "high", "medium", "low"

class EvidenceMatch(BaseModel):
    """Claim <-> source link: which passage of which source backs (or opposes) a claim."""
    source_title: str
    url_or_id: str
    source_type: str = "web"
    supporting_passage: str = ""          # the exact sentence(s) that matched the claim
    match_score: float = Field(0.0, ge=0.0, le=1.0)
    stance: ClaimRelationship = ClaimRelationship.SUPPORTS
    matched_terms: List[str] = []
    missing_numbers: List[str] = []       # numbers in the claim not found in this passage

class ConflictRecord(BaseModel):
    """A disagreement found while verifying a claim."""
    conflict_type: str   # numeric_mismatch | negation | direction | source_vs_source | counter_analysis
    description: str
    source_a: str
    source_b: Optional[str] = None
    excerpt_a: str = ""
    excerpt_b: str = ""
    resolved: bool = False
    resolution_note: Optional[str] = None

class CriterionDeduction(BaseModel):
    criterion: str
    points_lost: int = 0
    max_points: int = 0
    reason: str = ""

class ClaimDeductionDetail(BaseModel):
    claim_id: str
    statement: str
    total_points_lost: int = 0
    criterion_deductions: List[CriterionDeduction] = []

class ClaimRecord(BaseModel):
    claim_id: str
    statement: str
    evidence_sources: List[EvidenceItem] = []
    relationship: ClaimRelationship = ClaimRelationship.SUPPORTS
    source_quality: str = "secondary"
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    rubric_score: int = Field(0, ge=0, le=100)
    rubric_breakdown: Dict[str, int] = Field(default_factory=dict)
    limitations: List[str] = []
    # --- Person 3 (claim verification) additions; all optional so existing code keeps working ---
    source_answer_span: Optional[str] = None            # sentence of the generated answer the claim came from
    evidence_matches: List[EvidenceMatch] = []          # claim -> source/passage links (supporting + opposing)
    conflicts: List[ConflictRecord] = []                # contradictions detected for this claim
    unsupported_parts: List[str] = []                   # parts of the claim no source covers
    verification_notes: List[str] = []                  # why this status was assigned
    # --- Per-claim points lost & critical claim tracking ---
    is_critical: bool = False
    points_lost: int = 0
    criterion_points_lost: Dict[str, int] = Field(default_factory=dict)
    deduction_items: List[CriterionDeduction] = Field(default_factory=list)

class EvidenceStrengthScore(BaseModel):
    overall_score: int = Field(..., ge=0, le=100)
    label: str = "heuristic"
    verified_claims_count: int = 0
    partially_supported_count: int = 0
    disputed_claims_count: int = 0
    unverified_claims_count: int = 0
    rubric_breakdown: Dict[str, float] = Field(default_factory=dict)
    explanation: str
    deductions: List[str] = []
    # --- Per-criterion and per-claim points lost data ---
    points_lost_by_criterion: Dict[str, float] = Field(default_factory=dict)
    claim_deductions: List[ClaimDeductionDetail] = Field(default_factory=list)


# --- Master Synthesis & Orchestration Request/Response ---

class MasterOrchestrationRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000, description="User research or analysis prompt")
    include_web: bool = True
    include_knowledge_base: bool = True
    generate_pdf: bool = True
    room_id: Optional[str] = None
    top_k: int = Field(5, ge=1, le=10)

class MasterOrchestrationResponse(BaseModel):
    task_id: str
    query: str
    status: str  # "completed", "clarification_needed", "failed"
    clarification_needed: bool = False
    clarification_prompt: Optional[str] = None
    executive_summary: str
    final_synthesis: str
    evidence_strength: EvidenceStrengthScore
    claims: List[ClaimRecord] = []
    subtasks: List[SubTask] = []
    citations: List[str] = []
    sources: List[Source] = []
    limitations: List[str] = []
    report_id: Optional[str] = None
    pdf_download_url: Optional[str] = None
    trace: List[Dict[str, Any]] = []

class DecompositionRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=2000)
    domain_hint: Optional[str] = None

class DecompositionResponse(BaseModel):
    plan: TaskPlan

class ClaimVerificationRequest(BaseModel):
    claims: List[str] = []
    evidence: List[EvidenceItem]
    answer: Optional[str] = None          # optional: raw generated answer; claims are extracted from it if `claims` is empty
    objections: List[str] = []            # optional counter-analysis objections

class ClaimVerificationResponse(BaseModel):
    claims: List[ClaimRecord]
    evidence_strength: EvidenceStrengthScore

class SynthesisRequest(BaseModel):
    query: str
    claims: List[ClaimRecord]
    evidence_strength: EvidenceStrengthScore
    subtasks: List[SubTask]

class SynthesisResponse(BaseModel):
    executive_summary: str
    final_synthesis: str
    citations: List[str]
    limitations: List[str]


# --- Nonilion Bot Integration Schemas ---

class NonilionWebhookPayload(BaseModel):
    event: str = "message.created"  # e.g., "message.created", "bot.paired", "room.joined"
    room_id: str
    sender_id: Optional[str] = None
    sender_name: Optional[str] = None
    text: str
    attachments: List[str] = []
    pairing_code: Optional[str] = None
    timestamp: Optional[str] = None

class NonilionPairRequest(BaseModel):
    pairing_code: str = Field(..., min_length=4, max_length=64)
    room_id: Optional[str] = None

class NonilionPairResponse(BaseModel):
    status: str
    room_id: str
    bot_name: str
    paired_at: str

class NonilionMessageResponse(BaseModel):
    text: str
    attachments: List[str] = []
    status_update: Optional[str] = None
    report_id: Optional[str] = None

class NonilionStatusResponse(BaseModel):
    connected: bool
    paired: bool
    room_id: Optional[str]
    bot_name: str
    polling_active: bool
    last_poll_at: Optional[str]
