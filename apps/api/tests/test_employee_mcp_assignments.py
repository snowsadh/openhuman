from app.employees.templates import get_template

EXPECTED_ASSIGNMENTS = {
    "hr": {"slack", "gmail", "google-calendar", "notion", "web_search"},
    "sales": {"slack", "gmail", "google-calendar", "hubspot", "web_search", "canva"},
    "support": {"slack", "gmail", "zendesk", "notion", "web_search"},
    "general": {
        "slack",
        "google-calendar",
        "github",
        "notion",
        "n8n",
        "web_search",
        "canva",
    },
    "legal-compliance": {"slack", "gmail", "notion", "web_search"},
}


def test_first_ten_mcp_assignments_are_role_scoped() -> None:
    for employee_type, expected in EXPECTED_ASSIGNMENTS.items():
        assigned = set(get_template(employee_type).allowed_mcp_servers)
        assert assigned == expected
        assert "*" not in assigned


def test_suggested_connectors_match_runtime_assignments() -> None:
    for employee_type in EXPECTED_ASSIGNMENTS:
        template = get_template(employee_type)
        assert set(template.suggested_mcp_servers) == set(template.allowed_mcp_servers)
