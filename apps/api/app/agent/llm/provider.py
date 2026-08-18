from langchain_openai import ChatOpenAI

from app.core.config import settings


def get_llm(tools: list | None = None) -> ChatOpenAI:
    """Initialize a ChatOpenAI instance, optionally bound to tools.

    Uses settings from app.core.config.
    """
    api_key = settings.openai_api_key or "dummy-key"
    llm = ChatOpenAI(
        api_key=api_key,
        base_url=settings.openai_base_url or None,
        model=settings.openai_model,
        temperature=0.7,
    )
    if tools:
        return llm.bind_tools(tools)  # type: ignore[return-value]
    return llm
