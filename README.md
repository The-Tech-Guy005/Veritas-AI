# Veritas AI — Research Agent & Knowledge Base

Backend module for web research, document ingestion, persistent vector search, and RAG retrieval. Designed to be called by a separate Veritas AI Master Agent.

## Features
- FastAPI REST API
- Tavily web search (requires API key)
- PDF, DOCX, TXT and CSV text extraction
- Text chunking and Sentence Transformers embeddings
- Persistent ChromaDB vector storage
- Semantic retrieval and source metadata
- Structured JSON research response

## Requirements
Python 3.11 or 3.12 recommended. Install a C/C++ build toolchain if a dependency requires compilation.

## Setup
```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Add your Tavily API key to `.env` as `TAVILY_API_KEY=...`. The app can still run without it; web search will return a limitation message. Never commit `.env`.

## Run
```bash
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000/docs

## API examples

Health:
```bash
curl http://127.0.0.1:8000/health
```

Upload a document:
```bash
curl -X POST http://127.0.0.1:8000/documents/upload -F "file=@sample.pdf"
```

Search uploaded documents:
```bash
curl -X POST http://127.0.0.1:8000/knowledge-base/search \
  -H "Content-Type: application/json" \
  -d '{"query":"What does the document say about the project?","top_k":5}'
```

Research:
```bash
curl -X POST http://127.0.0.1:8000/research \
  -H "Content-Type: application/json" \
  -d '{"query":"Summarize recent information about retrieval augmented generation","include_web":true,"top_k":5}'
```

## Endpoints
- `GET /health`
- `POST /research`
- `POST /documents/upload`
- `GET /documents`
- `POST /knowledge-base/search`

## Master Agent response contract
`POST /research` returns:
```json
{
  "status": "ok",
  "answer": "...",
  "sources": [{"title": "...", "url": "https://...", "source_type": "web"}],
  "citations": ["https://..."],
  "retrieved_documents": [
    {"document_id": "...", "filename": "...", "chunk_id": "0", "text": "...", "relevance_score": 0.8}
  ],
  "confidence": "medium",
  "limitations": []
}
```

## Important limitations
- Tavily is an external provider; web search requires a valid API key.
- The embedding model is downloaded on first use and requires internet access at startup.
- This baseline returns retrieved evidence/snippets, not an LLM-written synthesis. The Master Agent can synthesize the evidence, or a separately configured LLM layer can be added.
- Scanned/image-only PDFs need OCR; OCR is not included in this initial module.
- Run tests with `pytest`.
