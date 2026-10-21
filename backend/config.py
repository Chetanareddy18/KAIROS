"""Central configuration — every tunable comes from the environment (.env)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    env:                    str   = os.getenv("KAIROS_ENV", "development")
    db_path:                str   = os.getenv("KAIROS_DB_PATH", str(ROOT / "kairos.duckdb"))
    api_key:                str   = os.getenv("KAIROS_API_KEY", "")
    sources_file:           str   = os.getenv("KAIROS_SOURCES_FILE", str(ROOT / "sources.yaml"))
    data_dir:               Path  = Path(os.getenv("KAIROS_DATA_DIR", str(ROOT / "data")))
    pipeline_interval_min:  int   = int(os.getenv("KAIROS_PIPELINE_INTERVAL_MIN", "15"))
    scheduler_enabled:      bool  = _bool("KAIROS_SCHEDULER_ENABLED", True)
    connector_timeout_s:    int   = int(os.getenv("KAIROS_CONNECTOR_TIMEOUT_S", "120"))
    connector_workers:      int   = int(os.getenv("KAIROS_CONNECTOR_WORKERS", "8"))
    z_threshold:            float = float(os.getenv("KAIROS_Z_THRESHOLD", "3.5"))
    use_prophet:            bool  = _bool("KAIROS_USE_PROPHET", True)
    alert_cooldown_min:     int   = int(os.getenv("KAIROS_ALERT_COOLDOWN_MIN", "60"))
    alert_min_severity:     str   = os.getenv("KAIROS_ALERT_MIN_SEVERITY", "medium")
    causal_lags:            int   = int(os.getenv("KAIROS_CAUSAL_LAGS", "1"))
    causal_max_vars:        int   = int(os.getenv("KAIROS_CAUSAL_MAX_VARS", "20"))
    groq_api_key:           str   = os.getenv("GROQ_API_KEY", "")
    groq_model:             str   = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    ollama_model:           str   = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    ollama_url:             str   = os.getenv("OLLAMA_URL", "http://localhost:11434")
    llm_enabled:            bool  = _bool("KAIROS_LLM_ENABLED", True)
    cors_origins:           list  = field(default_factory=lambda: [
        o.strip() for o in os.getenv(
            "KAIROS_CORS_ORIGINS", "http://localhost:5173,https://kairos-app.vercel.app"
        ).split(",") if o.strip()
    ])
    max_upload_mb:          int   = int(os.getenv("KAIROS_MAX_UPLOAD_MB", "2048"))

    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def transfer_dir(self) -> Path:
        return self.data_dir / "transfers"


settings = Settings()
