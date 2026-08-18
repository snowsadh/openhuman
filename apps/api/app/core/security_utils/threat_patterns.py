import re
import unicodedata

MAX_SCAN_CHARS = 65_536

_FILLER = r"(?:\w+\s+){0,8}"

_PATTERNS: list[tuple[str, str, str]] = [
    (
        rf'ignore\s+{_FILLER}(previous|all|above|prior)\s+{_FILLER}instructions',
        "prompt_injection", "all",
    ),
    (r'system\s+prompt\s+override', "sys_prompt_override", "all"),
    (
        rf'disregard\s+{_FILLER}(your|all|any)\s+{_FILLER}(instructions|rules|guidelines)',
        "disregard_rules", "all",
    ),
    (
        rf'act\s+as\s+(if|though)\s+{_FILLER}you\s+{_FILLER}'
        rf'(have\s+no|don\'t\s+have)\s+{_FILLER}(restrictions|limits|rules)',
        "bypass_restrictions", "all",
    ),
    (
        r'<!--[^>]{0,512}(?:ignore|override|system|secret|hidden)[^>]{0,512}-->',
        "html_comment_injection", "all",
    ),
    (
        r'<\s*div\s+style\s*=\s*["\'][^>]{0,2048}display\s*:\s*none',
        "hidden_div", "all",
    ),
    (
        r'translate\s+[^\n]{0,512}\s+into\s+[^\n]{0,512}\s+and\s+(execute|run|eval)',
        "translate_execute", "all",
    ),
    (rf'do\s+not\s+{_FILLER}tell\s+{_FILLER}the\s+user', "deception_hide", "all"),

    (rf'you\s+are\s+{_FILLER}now\s+(?:a|an|the)\s+', "role_hijack", "context"),
    (rf'pretend\s+{_FILLER}(you\s+are|to\s+be)\s+', "role_pretend", "context"),
    (rf'output\s+{_FILLER}(system|initial)\s+prompt', "leak_system_prompt", "context"),
    (
        rf'(respond|answer|reply)\s+without\s+{_FILLER}(restrictions|limitations|filters|safety)',
        "remove_filters", "context",
    ),
    (
        rf'you\s+have\s+been\s+{_FILLER}(updated|upgraded|patched)\s+to',
        "fake_update", "context",
    ),
    (r'\bname\s+yourself\s+\w+', "identity_override", "context"),
    (
        r'forget\s+(?:everything|all)\s+(?:you\s+)?(?:know|learned)[^\n]{0,128}\b(?:obey|follow|do)\b',
        "forget_and_obey",
        "context",
    ),

    (r'register\s+(as\s+)?a?\s*node', "c2_node_registration", "context"),
    (r'(heartbeat|beacon|check[\s\-]?in)\s+(to|with)\s+', "c2_heartbeat", "context"),
    (r'pull\s+(down\s+)?(?:new\s+)?task(?:ing|s)?\b', "c2_task_pull", "context"),
    (r'connect\s+to\s+the\s+network\b', "c2_network_connect", "context"),
    (
        r'you\s+must\s+(?:\w+\s+){0,3}(register|connect|report|beacon)\b',
        "forced_action", "context",
    ),
    (r'only\s+use\s+one[\s\-]?liners?\b', "anti_forensic_oneliner", "context"),
    (
        rf'never\s+{_FILLER}(?:create|write)\s+{_FILLER}(?:script|file)\s+{_FILLER}disk',
        "anti_forensic_disk", "context",
    ),
    (
        r'unset\s+\w*(?:CLAUDE|CODEX|HERMES|AGENT|OPENAI|ANTHROPIC)\w*',
        "env_var_unset_agent", "context",
    ),

    (
        r'\b(?:cobalt\s*strike|sliver|havoc|mythic|metasploit|brainworm)\b',
        "known_c2_framework", "context",
    ),
    (r'\bc2\s+(?:server|channel|infrastructure|beacon)\b', "c2_explicit", "context"),
    (r'\bcommand\s+and\s+control\b', "c2_explicit_long", "context"),

    (
        r'curl\s+[^\n]{0,2048}\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)',
        "exfil_curl", "all",
    ),
    (
        r'wget\s+[^\n]{0,2048}\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)',
        "exfil_wget", "all",
    ),
    (
        r'cat\s+[^\n]{0,2048}(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)',
        "read_secrets", "all",
    ),
    (
        r'(send|post|upload|transmit)\s+[^\n]{0,2048}\s+(to|at)\s+https?://',
        "send_to_url", "strict",
    ),
    (
        rf'(include|output|print|share)\s+{_FILLER}'
        rf'(conversation|chat\s+history|previous\s+messages|full\s+context|'
        rf'entire\s+context)',
        "context_exfil", "strict",
    ),

    (r'authorized_keys', "ssh_backdoor", "strict"),
    (r'\$HOME/\.ssh|\~/\.ssh', "ssh_access", "strict"),
    (
        r'(update|modify|edit|write|change|append|add\s+to)\s+'
        r'[^\n]{0,2048}(?:AGENTS\.md|CLAUDE\.md|\.cursorrules|\.clinerules)',
        "agent_config_mod", "strict",
    ),

    (
        r'(?:api[_-]?key|token|secret|password)\s*[=:]\s*'
        r'["\'][A-Za-z0-9+/=_-]{20,}',
        "hardcoded_secret", "strict",
    ),
]

INVISIBLE_CHARS = frozenset({
    '\u200b', '\u200c', '\u200d', '\u2060',
    '\u2062', '\u2063', '\u2064', '\ufeff',
    '\u202a', '\u202b', '\u202c', '\u202d', '\u202e',
    '\u2066', '\u2067', '\u2068', '\u2069',
})

_COMPILED: dict[str, list[tuple[re.Pattern, str]]] = {}


def _compile() -> None:
    global _COMPILED
    if _COMPILED:
        return

    all_patterns: list[tuple[re.Pattern, str]] = []
    context_patterns: list[tuple[re.Pattern, str]] = []
    strict_patterns: list[tuple[re.Pattern, str]] = []

    for pattern, pid, scope in _PATTERNS:
        compiled = re.compile(pattern, re.IGNORECASE)
        entry = (compiled, pid)
        if scope == "all":
            all_patterns.append(entry)
            context_patterns.append(entry)
            strict_patterns.append(entry)
        elif scope == "context":
            context_patterns.append(entry)
            strict_patterns.append(entry)
        elif scope == "strict":
            strict_patterns.append(entry)

    _COMPILED = {
        "all": all_patterns,
        "context": context_patterns,
        "strict": strict_patterns,
    }


_compile()


def scan_for_threats(content: str, scope: str = "context") -> list[str]:
    if not content:
        return []

    findings: list[str] = []
    content = content[:MAX_SCAN_CHARS]

    char_set = set(content)
    invisible_hits = char_set & INVISIBLE_CHARS
    for ch in invisible_hits:
        findings.append(f"invisible_unicode_U+{ord(ch):04X}")

    normalised = unicodedata.normalize("NFKC", content)

    patterns = _COMPILED.get(scope)
    if patterns is None:
        raise ValueError(f"scan_for_threats: unknown scope {scope!r}")
    for compiled, pid in patterns:
        if compiled.search(normalised):
            findings.append(pid)

    return findings


def first_threat_message(content: str, scope: str = "strict") -> str | None:
    findings = scan_for_threats(content, scope=scope)
    if not findings:
        return None
    pid = findings[0]
    if pid.startswith("invisible_unicode_"):
        codepoint = pid.replace("invisible_unicode_", "")
        return (
            f"Blocked: content contains invisible unicode character"
            f" {codepoint} (possible injection)."
        )
    return (
        f"Blocked: content matches threat pattern '{pid}'. "
        f"Content is injected into the system prompt and must not contain "
        f"injection or exfiltration payloads."
    )
