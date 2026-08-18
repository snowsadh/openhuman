def check_output(
    response: str, guardrail_config: dict | None = None
) -> tuple[bool, str | None]:
    """Check the LLM response against safety policies.

    Returns:
        tuple[bool, str | None]: (passed_validation, reason)
    """
    config = guardrail_config or {}

    # Hard-blocked: indicates actual system-prompt/instruction leakage, a
    # real safety concern — the whole response is discarded and replaced.
    hard_blocked_patterns = [
        "system prompt template",
    ]
    for pattern in hard_blocked_patterns:
        if pattern.lower() in response.lower():
            return False, f"Response contained restricted phrase: '{pattern}'"

    # Soft-flagged: stock AI-assistant phrasing ("as an AI", "according to
    # my instructions") that reads badly but isn't a leakage/safety issue.
    # These no longer fail the whole response — formatter_node's
    # _strip_ai_isms() cleans them out of the final text instead, so a
    # response isn't discarded just for one clunky sentence.

    # When citation requirements are enabled, verify the response provides
    # at least a minimal attribution signal.
    if config.get("require_citations", False):
        # Simple heuristic: look for source-like markers
        has_citation_marker = any(
            marker in response.lower()
            for marker in ["source:", "citation:", "according to", "from the"]
        )
        if not has_citation_marker and len(response) > 200:
            return False, (
                "Response is missing required citations. "
                "Please include sources for factual claims."
            )

    return True, None