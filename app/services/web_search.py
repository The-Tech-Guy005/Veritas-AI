from tavily import TavilyClient
from app.config import settings

def search_web(query: str, max_results: int = 5) -> tuple[list[dict], list[str]]:
    if not settings.tavily_api_key:
        return [], ["Web search was not run because TAVILY_API_KEY is not configured."]
    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        response = client.search(query=query, max_results=max_results, search_depth="advanced")
        results = []
        for item in response.get("results", []):
            url = item.get("url")
            if not url:
                continue
            results.append({
                "title": item.get("title") or url,
                "url": url,
                "content": item.get("content", "")
            })
        return results, []
    except Exception as exc:
        return [], [f"Web search provider error: {type(exc).__name__}. Check configuration and try again."]
