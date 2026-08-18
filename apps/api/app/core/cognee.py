"""Cognee bootstrap — must be imported before any module that imports cognee."""

import os


def apply_cognee_config() -> None:
    """Set Cognee env vars from settings BEFORE cognee SDK is imported.

    Cognee reads os.environ at import time. If this isn't called first,
    Cognee initializes with empty/wrong config and won't work.
    """
    from app.core.config import settings

    llm_api_key = settings.cognee_llm_api_key or settings.openai_api_key
    llm_endpoint = settings.cognee_llm_endpoint or settings.openai_base_url
    
    llm_model = settings.cognee_llm_model
    if not settings.cognee_llm_api_key and settings.openai_model:
        # Cognee expects provider prefix in model name: "openai/model_name"
        llm_model = f"openai/{settings.openai_model}"

    embedding_api_key = getattr(settings, "cognee_embedding_api_key", None) or settings.cognee_llm_api_key or settings.openai_api_key
    embedding_endpoint = settings.cognee_embedding_endpoint or settings.openai_base_url
    
    embedding_model = settings.cognee_embedding_model
    if not settings.cognee_embedding_endpoint and settings.openai_model:
        # Use same model for embeddings if compatible, or keep default
        pass

    os.environ.setdefault("LLM_PROVIDER", settings.cognee_llm_provider)
    if llm_endpoint:
        os.environ["LLM_ENDPOINT"] = llm_endpoint
    if llm_api_key:
        os.environ["LLM_API_KEY"] = llm_api_key
    os.environ["LLM_MODEL"] = llm_model

    os.environ.setdefault("EMBEDDING_PROVIDER", settings.cognee_embedding_provider)
    if embedding_endpoint:
        os.environ["EMBEDDING_ENDPOINT"] = embedding_endpoint
    if embedding_api_key:
        os.environ["EMBEDDING_API_KEY"] = embedding_api_key
    os.environ.setdefault("EMBEDDING_MODEL", settings.cognee_embedding_model)

    os.environ.setdefault(
        "COGNEE_SKIP_CONNECTION_TEST",
        str(settings.cognee_skip_connection_test).lower(),
    )

    graph_provider = (
        os.environ.get("GRAPH_DATABASE_PROVIDER")
        or os.environ.get("VERCEL_GRAPH_DATABASE_PROVIDER")
    )
    if graph_provider == "neo4j":
        # Neo4j Aura and Neo4j Community do not support multi-database CREATE/DROP commands.
        # Enforcing backend access control forces per-dataset database creation, which fails on Aura.
        os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

    # Route all Cognee storage (SQLite system DB, LanceDB vectors, Kuzu graphs,
    # cache, logs) to the persistent volume so data survives deploys.
    data_dir = os.path.abspath(settings.cognee_data_dir)  # /app/cognee_data

    if os.environ.get("VERCEL") == "1":
        os.environ["SYSTEM_ROOT_DIRECTORY"] = "/tmp/cognee_system"
        os.environ["COGNEE_DATA_DIR"] = "/tmp/cognee_data"
    else:
        os.environ.setdefault("DATA_ROOT_DIRECTORY", os.path.join(data_dir, "data"))
        os.environ.setdefault("SYSTEM_ROOT_DIRECTORY", os.path.join(data_dir, "system"))
        os.environ.setdefault("CACHE_ROOT_DIRECTORY", os.path.join(data_dir, "cache"))
        os.environ.setdefault("COGNEE_LOGS_DIR", os.path.join(data_dir, "logs"))
        os.environ.setdefault("COGNEE_DATA_DIR", data_dir)

