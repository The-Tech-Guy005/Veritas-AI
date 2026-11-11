from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import master, nonilion, research, documents, knowledge
from app.config import settings

app = FastAPI(
    title="Veritas AI — Collaborative Multi-Agent Intelligence & Evidence Verification System",
    version="1.0.0",
    description="Central Master Agent orchestrator, sub-agent delegation, claim-level evidence verification with deterministic rubric scoring, ReportLab PDF deliverable generation, and Nonilion Bot API integration."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core Master Agent & Nonilion Routers
app.include_router(master.router, tags=["Master Agent & Orchestration"])
app.include_router(nonilion.router, tags=["Nonilion Integration"])

# Sub-Agent & Knowledge Base Routers
app.include_router(research.router, tags=["Research Agent"])
app.include_router(documents.router, tags=["Documents & Ingestion"])
app.include_router(knowledge.router, tags=["Knowledge Base RAG"])

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "veritas-master-agent",
        "version": "1.0.0",
        "capabilities": {
            "master_agent": True,
            "evidence_verification_engine": True,
            "deterministic_rubric": True,
            "pdf_report_generation": True,
            "nonilion_bot_adapter": True,
            "subagent_delegation": True
        }
    }

@app.get("/")
def root():
    return {
        "name": "Veritas AI Master Orchestrator",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "orchestrate": "/master/orchestrate",
            "decompose": "/master/decompose",
            "verify": "/master/verify",
            "nonilion_webhook": "/nonilion/webhook",
            "nonilion_pair": "/nonilion/pair",
            "research": "/research",
            "documents": "/documents/upload",
            "knowledge_search": "/knowledge-base/search"
        }
    }
