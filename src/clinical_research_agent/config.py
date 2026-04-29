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

    # Provider selection: "anthropic" | "gemini" | "vertexai"
    llm_provider: Literal["anthropic", "gemini", "vertexai"] = "anthropic"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # Google Gemini API (AI Studio key — AIzaSy...)
    google_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    gemini_judge_model: str = "gemini-2.5-flash-lite"  # cheaper model for eval judge calls

    # Vertex AI (optional — requires `pip install 'clinical-research-agent[vertex]'`)
    vertex_project_id: str = ""
    vertex_location: str = "us-central1"
    vertex_model: str = "gemini-1.5-pro"

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
        if self.llm_provider == "gemini":
            return self.gemini_judge_model
        return "claude-haiku-4-5-20251001"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_llm(settings: Settings | None = None) -> BaseChatModel:
    """Return a LangChain BaseChatModel for the configured provider.

    All agents call this — swap provider via LLM_PROVIDER in .env.
    Anthropic and Gemini are fully working implementations.
    Vertex AI is scaffolded (set VERTEX_PROJECT_ID to enable).
    """
    if settings is None:
        settings = get_settings()

    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
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

    if settings.llm_provider == "vertexai":
        try:
            from langchain_google_vertexai import ChatVertexAI  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "Vertex AI extras not installed. "
                "Run: pip install 'clinical-research-agent[vertex]'"
            ) from exc
        if not settings.vertex_project_id:
            raise ValueError(
                "Vertex client scaffolded — set VERTEX_PROJECT_ID and VERTEX_LOCATION to enable."
            )
        return ChatVertexAI(  # type: ignore[return-value]
            model=settings.vertex_model,
            project=settings.vertex_project_id,
            location=settings.vertex_location,
        )

    raise ValueError(f"Unknown LLM provider: {settings.llm_provider!r}")


def get_judge_llm(settings: Settings | None = None) -> BaseChatModel:
    """Return a cheaper model for LLM-as-judge eval calls.

    Uses gemini-1.5-flash (Gemini provider) or claude-haiku (Anthropic).
    """
    if settings is None:
        settings = get_settings()

    judge = settings.effective_judge_model()

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
