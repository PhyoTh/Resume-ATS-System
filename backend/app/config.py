from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_HERE = Path(__file__).resolve()
_BACKEND_DIR = _HERE.parents[1]
_REPO_ROOT = _HERE.parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(_REPO_ROOT / ".env"),
            str(_BACKEND_DIR / ".env"),
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # TritonAI (OpenAI-compatible gateway provided by CSE 190)
    triton_api_key: str = ""
    triton_base_url: str = "https://tritonai-api.ucsd.edu/v1"
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = 90.0

    # Storage
    data_dir: Path = Path("./data")
    uploads_dir: Path = Path("./data/uploads")
    db_url: str = "sqlite:///./data/app.db"

    # Extraction knobs
    validity_confidence_threshold: float = 0.5
    max_alias_injection: int = 200

    # Server
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    return s
