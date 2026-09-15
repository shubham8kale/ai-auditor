from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    auditor_env: str = "development"
    auditor_local_auth: bool = False
    database_url: str = "sqlite:///./data/auditor.db"
    database_password: str = ""
    storage_root: Path = Path("data/files")
    frontend_origin: str = "http://localhost:5173"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "audit-evidence"
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.8-27b"
    groq_zdr_confirmed: bool = False
    max_upload_mb: int = 12

    def validate_runtime(self):
        if self.supabase_anon_key.startswith("sb_secret_"):
            raise RuntimeError("The frontend key must be a publishable key, never a server secret.")
        if self.auditor_env == "production":
            if self.auditor_local_auth or self.database_url.startswith("sqlite"):
                raise RuntimeError(
                    "Production requires named authentication and a persistent PostgreSQL database."
                )
            if not all((self.supabase_url, self.supabase_anon_key, self.supabase_service_role_key)):
                raise RuntimeError(
                    "Production requires Supabase authentication and private evidence storage."
                )
        if self.groq_api_key and not self.groq_zdr_confirmed:
            raise RuntimeError("Confirm Groq Zero Data Retention before enabling document processing.")


@lru_cache
def settings() -> Settings:
    return Settings()
