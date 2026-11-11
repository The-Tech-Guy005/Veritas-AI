import os
from pathlib import Path

class Settings:
    def __init__(self):
        # API Keys & Models
        self.tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")
        self.gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.master_model: str = os.getenv("MASTER_MODEL", "gemini-2.0-flash")

        # Storage Directories
        self.data_dir: str = os.getenv("DATA_DIR", "./data")
        self.reports_dir: str = os.getenv("REPORTS_DIR", os.path.join(self.data_dir, "reports"))
        self.chroma_collection: str = os.getenv("CHROMA_COLLECTION", "veritas_documents")

        # Limits & Processing Config
        self.max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "20"))
        self.chunk_size: int = int(os.getenv("CHUNK_SIZE", "900"))
        self.chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "150"))
        self.max_subtasks: int = int(os.getenv("MAX_SUBTASKS", "6"))
        self.evidence_threshold_score: int = int(os.getenv("EVIDENCE_THRESHOLD_SCORE", "70"))
        self.subagent_timeout_seconds: int = int(os.getenv("SUBAGENT_TIMEOUT_SECONDS", "30"))

        # Limits, Retries & Concurrency Config
        self.max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
        self.retry_initial_delay: float = float(os.getenv("RETRY_INITIAL_DELAY", "0.5"))
        self.retry_backoff_factor: float = float(os.getenv("RETRY_BACKOFF_FACTOR", "2.0"))
        self.max_concurrency: int = int(os.getenv("MAX_CONCURRENCY", "4"))
        self.workflow_recursion_limit: int = int(os.getenv("WORKFLOW_RECURSION_LIMIT", "15"))
        self.rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

        # Nonilion Integration Settings
        self.nonilion_bot_name: str = os.getenv("NONILION_BOT_NAME", "Veritas AI Master")
        self.nonilion_api_url: str = os.getenv("NONILION_API_URL", "https://api.nonilion.com/v1")
        self.nonilion_bot_token: str = os.getenv("NONILION_BOT_TOKEN", "")
        self.nonilion_pairing_code: str = os.getenv("NONILION_PAIRING_CODE", "")
        self.nonilion_room_id: str = os.getenv("NONILION_ROOM_ID", "")
        self.nonilion_webhook_secret: str = os.getenv("NONILION_WEBHOOK_SECRET", "")
        self.nonilion_poll_interval_seconds: int = int(os.getenv("NONILION_POLL_INTERVAL_SECONDS", "5"))

        # Ensure directories exist
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.reports_dir).mkdir(parents=True, exist_ok=True)

settings = Settings()
