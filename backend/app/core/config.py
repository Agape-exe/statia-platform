from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    allowed_origins: str = "http://localhost:5173"
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: int = Field(default=35, ge=5, le=45)
    gemini_context_chars: int = Field(default=45000, ge=4000, le=100000)
    gemini_max_output_tokens: int = Field(default=7000, ge=256, le=16000)
    openai_api_key: SecretStr = SecretStr("")
    openai_terra_enabled: bool = False
    openai_timeout_seconds: int = Field(default=60, ge=5, le=65)
    openai_max_output_tokens: int = Field(default=12000, ge=256, le=16000)
    ai_requests_per_minute: int = Field(default=20, ge=1, le=120)
    ai_max_requests_per_turn: int = Field(default=4, ge=1, le=4)
    max_file_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    max_rows: int = Field(default=20000, ge=1, le=100000)
    max_columns: int = Field(default=120, ge=1, le=300)
    max_expanded_bytes: int = Field(default=30 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    max_conversation_files: int = Field(default=12, ge=1, le=30)
    missing_value_markers: str = "NA,N/A,null,NaN,None,<NA>"
    # Decisiones explícitas por columna; no se deducen categorías ausentes por su nombre.
    missing_value_overrides: dict[str, list[str]] = Field(default_factory=dict)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("allowed_origins")
    @classmethod
    def exact_origins(cls, value: str) -> str:
        for origin in (part.strip() for part in value.split(",") if part.strip()):
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or "*" in origin
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError("ALLOWED_ORIGINS requiere orígenes HTTP(S) exactos, sin rutas ni comodines.")
        return value

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
