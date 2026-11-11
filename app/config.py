import os
from pathlib import Path

class Settings:
    def __init__(self):
        self.tavily_api_key = os.getenv("TAVILY_API_KEY", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.data_dir = os.getenv("DATA_DIR", "./data")
        self.chroma_collection = os.getenv("CHROMA_COLLECTION", "veritas_documents")
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "900"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "150"))
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)

settings = Settings()
