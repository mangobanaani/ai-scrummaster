from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Boot-time optional so the container starts before secrets are injected
    # (e.g. Vault-templated env in the fabric). Endpoints that need them fail
    # at request time instead of crashing the pod at startup.
    github_token: str = ""
    github_webhook_secret: str = ""
    api_key: str = ""

    # LLM backend: "ollama" (local docker compose) or "openai"
    # (any OpenAI-compatible gateway, e.g. a LiteLLM proxy).
    # Fabric deployments use the platform convention: LITELLM_* env vars
    # (base URL points at the agent's vault-proxy sidecar).
    llm_provider: str = "ollama"
    llm_base_url: str = Field(
        default="", validation_alias=AliasChoices("LLM_BASE_URL", "LITELLM_BASE_URL")
    )
    llm_api_key: str = Field(
        default="", validation_alias=AliasChoices("LLM_API_KEY", "LITELLM_API_KEY")
    )
    llm_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("LLM_MODEL", "LITELLM_MODEL"),
    )

    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:27b"
    mcp_server_url: str = "http://github-mcp:3000"
    log_level: str = "INFO"
    policies_path: str = "policies/rules.yaml"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
