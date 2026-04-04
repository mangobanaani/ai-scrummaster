from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    github_token: str
    github_webhook_secret: str
    api_key: str
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:7b"
    mcp_server_url: str = "http://github-mcp:3000"
    log_level: str = "INFO"
    policies_path: str = "policies/rules.yaml"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def _get_settings() -> Settings:
    return Settings()


class _SettingsProxy:
    """Lazy proxy that defers Settings instantiation until first attribute access."""

    def __getattr__(self, name: str):
        return getattr(_get_settings(), name)


settings = _SettingsProxy()
