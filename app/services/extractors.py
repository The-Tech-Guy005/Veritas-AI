from pathlib import Path
import io
import pandas as pd
import fitz
from docx import Document

SUPPORTED = {".pdf", ".docx", ".txt", ".csv"}

def extract_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {suffix}. Supported: PDF, DOCX, TXT, CSV.")
    if suffix == ".pdf":
        with fitz.open(stream=content, filetype="pdf") as pdf:
            return "\n".join(page.get_text() for page in pdf)
    if suffix == ".docx":
        doc = Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if suffix == ".txt":
        return content.decode("utf-8-sig", errors="replace")
    if suffix == ".csv":
        df = pd.read_csv(io.BytesIO(content), dtype=str).fillna("")
        return df.to_csv(index=False)
    raise ValueError("Unsupported file type")
