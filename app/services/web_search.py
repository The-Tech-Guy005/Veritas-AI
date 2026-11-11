import requests
from app.config import settings

def search_web(query, max_results=5):
    if not settings.tavily_api_key:
        return [], ["TAVILY_API_KEY is not configured; web search was skipped."]
    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False
            },
            timeout=25
        )
        response.raise_for_status()
        payload = response.json()
        results = []
        for item in payload.get("results", []):
            url = item.get("url")
            if url:
                results.append({
                    "title": item.get("title") or url,
                    "url": url,
                    "content": item.get("content", "")
                })
        return results, []
    except Exception as exc:
        return [], ["Web search request failed: " + type(exc).__name__]
