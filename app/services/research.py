from app.services.web_search import search_web
from app.services.vector_store import search_chunks

def run_research(query: str, include_web: bool = True, top_k: int = 5) -> dict:
    retrieved = search_chunks(query, top_k=top_k)
    web_results, limitations = search_web(query, max_results=top_k) if include_web else ([], ["Web search disabled for this request."])
    parts = []
    if retrieved:
        parts.append("Relevant information from uploaded documents:")
        for i, item in enumerate(retrieved, 1):
            parts.append(f"[D{i}] {item['text']}")
    if web_results:
        parts.append("Web research results (summaries/snippets returned by the search provider):")
        for i, item in enumerate(web_results, 1):
            parts.append(f"[W{i}] {item['title']} — {item['content']} (Source: {item['url']})")
    if not parts:
        answer = "No matching uploaded documents or web results were found. Configure Tavily or upload relevant documents and try again."
        confidence = "low"
    else:
        answer = "\n\n".join(parts)
        confidence = "medium" if retrieved or web_results else "low"
    sources = [{"title": x["title"], "url": x["url"], "source_type": "web"} for x in web_results]
    citations = [x["url"] for x in sources]
    docs = [{
        "document_id": x["document_id"], "filename": x["filename"],
        "chunk_id": x["chunk_id"], "text": x["text"],
        "relevance_score": x["relevance_score"]
    } for x in retrieved]
    return {"status": "ok", "answer": answer, "sources": sources, "citations": citations,
            "retrieved_documents": docs, "confidence": confidence, "limitations": limitations}
