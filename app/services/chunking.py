from app.config import settings

def chunk_text(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    size, overlap = settings.chunk_size, settings.chunk_overlap
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks
