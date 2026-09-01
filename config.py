from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    environment: str = "development"
    log_level: str = "INFO"
    expose_docs: bool = True
    qwen_api_key: str | None = None
    qwen_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    qwen_text_model: str = "qwen-flash"
    qwen_vision_model: str = "qwen3-vl-plus"
    qwen_timeout_seconds: float = 90.0
    api_auth_token: str | None = None
    request_timeout_seconds: float = 25.0
    maximum_redirects: int = 4
    maximum_response_bytes: int = 2_000_000
    maximum_upload_bytes: int = 8_000_000
    minimum_source_text_chars: int = 80
    user_agent: str = "PinchmealRecipeImporter/1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
