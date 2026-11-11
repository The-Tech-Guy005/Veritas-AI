from pydantic import BaseModel, Field
from typing import Any

class ResearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=2000)
    include_web: bool = True
    top_k: int = Field(default=5, ge=1, le=20)

class Source(BaseModel):
    title: str
    url: str
    source_type: str = "web"

class RetrievedDocument(BaseModel):
    document_id: str
    filename: str
    chunk_id: str
    text: str
    relevance_score: float | None = None

class ResearchResponse(BaseModel):
    status: str
    answer: str
    sources: list[Source] = []
    citations: list[str] = []
    retrieved_documents: list[RetrievedDocument] = []
    confidence: str
    limitations: list[str] = []

class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)

class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    chunks_added: int
    status: str
