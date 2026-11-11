# Veritas AI — Research Agent & Knowledge Base (Prototype)

A backend prototype for the Veritas AI team. It provides web research, document ingestion, persistent vector retrieval (RAG), and a structured API response for a separate Master Agent.

## Features
- FastAPI API and interactive Swagger docs
- Web search using Tavily (optional API key)
- Optional Gemini-powered evidence synthesis
- PDF, DOCX, TXT and CSV ingestion
- Text chunking and persistent ChromaDB vector storage
- Semantic retrieval from uploaded documents
- Source URLs, citations, retrieved document metadata and limitations
- Master Agent-friendly JSON response

## Run locally (Python 3.9+)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs

## Configure optional providers
Edit `.env`:
- `TAVILY_API_KEY`: enables live web search.
- `GEMINI_API_KEY`: enables LLM synthesis of retrieved evidence.
Never commit `.env` or expose API keys.

Without keys, document upload and retrieval still work. Research returns retrieved evidence and clearly reports which provider was not configured.

## API
- `GET /health`
- `POST /research`
- `POST /documents/upload` (multipart file: PDF/DOCX/TXT/CSV)
- `GET /documents`
- `POST /knowledge-base/search`

### Research request
```json
{
  "query": "Explain the latest developments in renewable energy",
  "include_web": true,
  "include_knowledge_base": true,
  "top_k": 5
}
```

### Knowledge-base search request
```json
{
  "query": "Summarize the uploaded report",
  "top_k": 5
}
```

### Master Agent response contract
```json
{
  "status": "ok",
  "answer": "Evidence-based answer or retrieved evidence",
  "sources": [{"title": "Source title", "url": "https://example.com", "source_type": "web"}],
  "citations": ["https://example.com"],
  "retrieved_documents": [
    {"document_id": "id", "filename": "report.pdf", "chunk_id": "0", "text": "relevant text", "relevance_score": 0.8}
  ],
  "confidence": "medium",
  "limitations": []
}
```

## Prototype notes
- ChromaDB's default embedding function is used to avoid requiring a separate Torch installation.
- The first vector operation may download its embedding model.
- Gemini synthesis is optional; without a key the API returns retrieved evidence, not a fabricated summary.
- Scanned PDFs requiring OCR are not supported in this prototype.
- This is a prototype and should receive security, reliability and integration testing before production use.
