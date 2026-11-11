from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import research, documents, knowledge
from app.config import settings

app = FastAPI(
    title="Veritas AI - Research Agent & Knowledge Base",
    version="1.0.0",
    description="Research, document ingestion, and RAG retrieval service for the Veritas AI Master Agent."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(research.router, tags=["Research"])
app.include_router(documents.router, tags=["Documents"])
app.include_router(knowledge.router, tags=["Knowledge Base"])

@app.get("/health")
def health():
    return {"status": "ok", "service": "veritas-research-agent", "version": "1.0.0"}
