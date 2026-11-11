from app.config import settings

def chunk_text(text):
    text = " ".join(text.split())
    if not text:
        return []
    size = settings.chunk_size
    overlap = min(settings.chunk_overlap, max(0, size // 2))
    output, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        piece = text[start:end].strip()
        if piece:
            output.append(piece)
        if end >= len(text):
            break
        start = end - overlap
    return output
