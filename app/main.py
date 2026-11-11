from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import research, documents, knowledge
from app.config import settings

app = FastAPI(
    title="Veritas AI — Research Agent & Knowledge Base",
    version="0.2.0",
    description="Prototype service for web research, document ingestion, RAG retrieval and Master Agent handoff."
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(research.router, tags=["Research"])
app.include_router(documents.router, tags=["Documents"])
app.include_router(knowledge.router, tags=["Knowledge Base"])

@app.get("/health")
def health():
    return {"status": "ok", "service": "veritas-research-agent", "version": "0.2.0"}

@app.get("/")
def root():
    return {
        "name": "Veritas AI Research Agent",
        "docs": "/docs",
        "health": "/health",
        "capabilities": ["web research", "PDF/DOCX/TXT/CSV ingestion", "RAG retrieval", "Master Agent JSON response"]
    }
