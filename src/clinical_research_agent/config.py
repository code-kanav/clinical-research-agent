from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_core.language_models import BaseChatModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Provider selection: "anthropic" | "gemini" | "vertex"
    llm_provider: Literal["anthropic", "gemini", "vertex"] = "vertex"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # Google Gemini AI Studio (legacy — use vertex instead)
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_judge_model: str = "gemini-2.5-flash"

    # Vertex AI — auth via ADC (~/.config/gcloud/application_default_credentials.json)
    gcp_project_id: str = ""
    gcp_location: str = "us-central1"
    gcp_model: str = "gemini-2.5-flash"

    # Search APIs
    ncbi_api_key: str = ""
    semantic_scholar_api_key: str = ""

    # LangSmith tracing
    langchain_api_key: str = ""
    langchain_project: str = "clinical-research-agent"

    # Disk cache
    cache_dir: str = ".cache"
    cache_ttl_seconds: int = 604800  # 7 days; 0 = disabled

    # Eval judge model (overrides provider-specific default when set explicitly)
    judge_model: str = ""

    # Debug
    debug: bool = False

    def effective_judge_model(self) -> str:
        if self.judge_model:
            return self.judge_model
        return self.gcp_model if self.llm_provider == "vertex" else self.gemini_judge_model

    def active_model(self) -> str:
        """Return the model name currently in use."""
        if self.llm_provider == "vertex":
            return self.gcp_model
        if self.llm_provider == "gemini":
            return self.gemini_model
        return self.anthropic_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_llm(settings: Settings | None = None) -> BaseChatModel:
    """Return a LangChain BaseChatModel for the configured provider.

    vertex  — ChatVertexAI via ADC; set GCP_PROJECT_ID + GCP_LOCATION in .env.
    gemini  — ChatGoogleGenerativeAI via AI Studio API key (legacy).
    anthropic — ChatAnthropic via API key.
    """
    if settings is None:
        settings = get_settings()

    if settings.llm_provider == "vertex":
        from langchain_google_vertexai import ChatVertexAI  # type: ignore[import-untyped]
        if not settings.gcp_project_id:
            raise ValueError("Set GCP_PROJECT_ID in .env to use the vertex provider.")
        return ChatVertexAI(  # type: ignore[return-value]
            model_name=settings.gcp_model,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )

    if settings.llm_provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "Google GenAI extras not installed. "
                "Run: pip install 'clinical-research-agent[gemini]'"
            ) from exc
        if not settings.google_api_key:
            raise ValueError("Set GOOGLE_API_KEY in .env to use the Gemini provider.")
        return ChatGoogleGenerativeAI(  # type: ignore[return-value]
            model=settings.gemini_model,
            google_api_key=settings.google_api_key,  # type: ignore[arg-type]
        )

    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
        )

    raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r}")


def get_judge_llm(settings: Settings | None = None) -> BaseChatModel:
    """Return a cheaper model for LLM-as-judge eval calls."""
    if settings is None:
        settings = get_settings()

    judge = settings.effective_judge_model()

    if settings.llm_provider == "vertex":
        from langchain_google_vertexai import ChatVertexAI  # type: ignore[import-untyped]
        return ChatVertexAI(  # type: ignore[return-value]
            model_name=judge,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )

    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore[import-untyped]
        return ChatGoogleGenerativeAI(  # type: ignore[return-value]
            model=judge,
            google_api_key=settings.google_api_key,  # type: ignore[arg-type]
        )

    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model=judge,
        api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
    )
