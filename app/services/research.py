from app.services.web_search import search_web
from app.services.vector_store import search_chunks
from app.services.answer_generator import generate_answer

def run_research(query, include_web=True, include_knowledge_base=True, top_k=5):
    retrieved = search_chunks(query, top_k) if include_knowledge_base else []
    web_results, limitations = search_web(query, top_k) if include_web else ([], ["Web search disabled."])
    answer, confidence, answer_limits = generate_answer(query, web_results, retrieved)
    sources = [
        {"title": item["title"], "url": item["url"], "source_type": "web"}
        for item in web_results
    ]
    docs = [{
        "document_id": item["document_id"],
        "filename": item["filename"],
        "chunk_id": item["chunk_id"],
        "text": item["text"],
        "relevance_score": item["relevance_score"]
    } for item in retrieved]
    return {
        "status": "ok",
        "answer": answer,
        "sources": sources,
        "citations": [item["url"] for item in sources],
        "retrieved_documents": docs,
        "confidence": confidence,
        "limitations": limitations + answer_limits
    }
