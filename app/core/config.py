from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Aplikasi
    ENV: Literal["development", "production", "test"] = "development"
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: str = "http://localhost:5173"
    TIMEZONE: str = "Asia/Jakarta"

    # Sesi / Auth
    JWT_SECRET: str = Field(min_length=32)
    JWT_EXPIRE_HOURS: int = 12
    COOKIE_NAME: str = "access_token"
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    ADMIN1_USERNAME: str = "admin1"
    ADMIN1_PASSWORD_HASH: str = ""
    ADMIN2_USERNAME: str = "admin2"
    ADMIN2_PASSWORD_HASH: str = ""

    # Upload
    MAX_UPLOAD_MB: int = 5

    # Cache (dipakai pada fase berikutnya)
    CACHE_TTL_SECONDS: int = 30

    # Google Sheets (dipakai pada fase berikutnya)
    GOOGLE_SERVICE_ACCOUNT_FILE: str = ""
    SPREADSHEET_ID: str = ""
    SPREADSHEET_URL: str = ""
    GEMINI_API_KEY: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def admins(self) -> dict[str, str]:
        """Peta username -> hash bcrypt. Akun dengan hash kosong dianggap nonaktif."""
        pairs = {
            self.ADMIN1_USERNAME: self.ADMIN1_PASSWORD_HASH,
            self.ADMIN2_USERNAME: self.ADMIN2_PASSWORD_HASH,
        }
        return {user: hashed for user, hashed in pairs.items() if user and hashed}

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
