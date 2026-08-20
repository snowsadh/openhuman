"""
Quick eval: measures how much AI-ism / markdown leakage survives the
formatter's cleanup step, using a fixed set of sample "raw" model outputs
representative of what gpt-4o-mini tends to produce without style guidance.

This does NOT call the live LLM or the real agent graph — it's a fast,
offline regression check against formatter.py's stripping functions
(_strip_ai_isms, _strip_unwanted_markdown) so you can run it in CI on every
change to formatter.py, output.py, or build_prompt.py's style block.

For a real signal on whether the *model* has stopped producing these
patterns in the first place (rather than whether the stripper catches them),
you still need to run actual conversations through the live pipeline and
sample the raw pre-formatter text. This script only tells you: "if the model
still produces X, does our cleanup catch it?"

Usage:
    python -m evals.eval_humanization
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_this_dir = Path(__file__).resolve().parent
_api_dir = _this_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

# Import the real stripping functions from formatter.py so this eval breaks
# if someone changes their behavior without updating the patterns below.
from app.agent.nodes.formatter import _strip_ai_isms, _strip_unwanted_markdown  # noqa: E402


# ---------------------------------------------------------------------------
# Detection patterns — used only to SCORE leakage, independent of the
# stripper's own patterns (so the eval doesn't just trivially agree with
# itself). Intentionally broader than formatter.py's anchored patterns.
# ---------------------------------------------------------------------------
LEAKAGE_PATTERNS = {
    "ai_self_reference": re.compile(
        r"\b(as an ai|i'?m an ai|i am an ai|as a language model|"
        r"i'?m (a |an )?(virtual )?assistant)\b", re.IGNORECASE
    ),
    "generic_signoff": re.compile(
        r"(is there anything else i can help|feel free to (ask|reach out)|"
        r"let me know if you (have|need))", re.IGNORECASE
    ),
    "conversation_recap": re.compile(
        r"^\s*\d+\.\s+you (said|asked|mentioned|told)", re.IGNORECASE | re.MULTILINE
    ),
    "markdown_table": re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE),
    "bold_label": re.compile(r"\*\*[^*]+\*\*"),
    "opening_filler": re.compile(
        r"^\s*(great|good) question[!.]?\s*", re.IGNORECASE
    ),
    "helpdesk_greeting": re.compile(
        r"\b(how (can|may) i (help|assist) you|what can i do for you)\b", re.IGNORECASE
    ),
    "robotic_emoji": re.compile(
        r"^\s*[👋😊🤖🎯]|[👋😊🤖🎯]\s*$", re.IGNORECASE | re.MULTILINE
    ),
}


@dataclass
class SampleResult:
    name: str
    raw_hits: dict[str, int] = field(default_factory=dict)
    cleaned_hits: dict[str, int] = field(default_factory=dict)


def score(text: str) -> dict[str, int]:
    return {name: len(pattern.findall(text)) for name, pattern in LEAKAGE_PATTERNS.items()}


def clean(text: str) -> str:
    text = _strip_ai_isms(text)
    text = _strip_unwanted_markdown(text)
    return text


# ---------------------------------------------------------------------------
# Sample raw outputs — representative of real gpt-4o-mini behavior seen in
# the "Problem Manifested" section of the original writeup. Add real
# production samples here over time (with PII stripped) for better coverage.
# ---------------------------------------------------------------------------
SAMPLES: dict[str, str] = {
    "support_policy_table": (
        "I'm Alex, an AI assistant for Acme Corp. Here's what I found in our "
        "records about **Acme Corp's policies**:\n\n"
        "| Policy | Detail |\n"
        "| --- | --- |\n"
        "| Refunds | 30 days |\n"
        "| Exchanges | 60 days |\n\n"
        "Is there anything else I can help you with?"
    ),
    "sales_recap": (
        "Great question! Let me recap what we've discussed:\n"
        "1. You said you're interested in the enterprise plan.\n"
        "2. You asked about pricing tiers.\n"
        "3. You mentioned a Q3 deadline.\n\n"
        "As an AI, I can't offer custom discounts, but I can connect you with sales."
    ),
    "hr_short_answer": (
        "As an AI assistant, I want to note that vacation requests should go "
        "through the HR portal. Feel free to ask if you have any other questions!"
    ),
    "legal_clean_already": (
        "That clause is fairly standard for a NDA, but the liability cap in "
        "section 4.2 looks lower than what we usually accept. Worth flagging "
        "to a human lawyer before signing."
    ),  # control sample — should already be clean, nothing to strip
    "general_code_answer": (
        "Here's a fix:\n\n"
        "```python\n"
        "def add(a, b):\n"
        "    return a + b\n"
        "```\n\n"
        "This should resolve the type error you were seeing."
    ),  # control sample — legitimate code block, must NOT be mangled
    "robotic_greeting_emoji_start": "👋 Hi there! How can I help you today?",
    "robotic_greeting_emoji_end": "Hi! How can I assist you today? 😊",
    "robotic_greeting_with_opinion": "That sounds interesting! What can I do for you today?",
}


def run() -> None:
    results: list[SampleResult] = []

    for name, raw in SAMPLES.items():
        cleaned = clean(raw)
        r = SampleResult(
            name=name,
            raw_hits=score(raw),
            cleaned_hits=score(cleaned),
        )
        results.append(r)

    total_raw = 0
    total_cleaned = 0

    print(f"{'sample':28} {'category':22} {'raw':>4} {'cleaned':>8}")
    print("-" * 66)
    for r in results:
        for category in LEAKAGE_PATTERNS:
            raw_n = r.raw_hits[category]
            clean_n = r.cleaned_hits[category]
            total_raw += raw_n
            total_cleaned += clean_n
            if raw_n or clean_n:
                flag = "  <- LEAKED" if clean_n > 0 else ""
                print(f"{r.name:28} {category:22} {raw_n:>4} {clean_n:>8}{flag}")

    print("-" * 66)
    caught = total_raw - total_cleaned
    pct = (caught / total_raw * 100) if total_raw else 100.0
    print(f"Total leakage instances: raw={total_raw}  after cleanup={total_cleaned}  "
          f"caught={caught} ({pct:.0f}%)")

    # Sanity check: control samples should be byte-identical (or near enough)
    # before/after, proving the stripper doesn't mangle legitimate content.
    for control_name in ("legal_clean_already", "general_code_answer"):
        raw = SAMPLES[control_name]
        cleaned = clean(raw)
        if raw.strip() != cleaned.strip():
            print(f"\n⚠️  WARNING: control sample '{control_name}' was modified by "
                  f"the stripper — check for false positives.")
            print(f"  before: {raw!r}")
            print(f"  after:  {cleaned!r}")


if __name__ == "__main__":
    run()
