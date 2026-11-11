import requests
from app.config import settings

def generate_answer(query, web_results, retrieved):
    evidence = []
    for item in web_results:
        evidence.append("WEB SOURCE: {0}\nURL: {1}\nCONTENT: {2}".format(
            item.get("title", ""), item.get("url", ""), item.get("content", "")
        ))
    for item in retrieved:
        evidence.append("UPLOADED DOCUMENT: {0}\nCHUNK: {1}".format(
            item.get("filename", ""), item.get("text", "")
        ))
    if not evidence:
        return "No evidence found. Configure Tavily or upload relevant documents.", "low", [
            "No web results or matching knowledge-base documents were available."
        ]
    if not settings.gemini_api_key:
        return (
            "Evidence retrieved for your query:\n\n" + "\n\n---\n\n".join(evidence),
            "medium",
            ["GEMINI_API_KEY is not configured; returning retrieved evidence without LLM synthesis."]
        )
    prompt = (
        "Answer the user's research question using ONLY the evidence below. "
        "Do not invent facts or citations. Clearly identify uncertainty. "
        "Cite web evidence using its exact URL and uploaded files by filename.\n\n"
        "QUESTION:\n" + query + "\n\nEVIDENCE:\n" + "\n\n".join(evidence)
    )
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/{0}:generateContent?key={1}".format(
            settings.gemini_model, settings.gemini_api_key
        )
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.2}},
            timeout=45
        )
        response.raise_for_status()
        data = response.json()
        answer = data["candidates"][0]["content"]["parts"][0]["text"]
        return answer, "high", []
    except Exception as exc:
        return (
            "LLM synthesis was unavailable. Retrieved evidence:\n\n" + "\n\n---\n\n".join(evidence),
            "medium",
            ["Gemini answer generation failed: " + type(exc).__name__]
        )
