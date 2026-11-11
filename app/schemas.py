from typing import List, Optional
from pydantic import BaseModel, Field

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

class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    chunks_added: int
    status: str
