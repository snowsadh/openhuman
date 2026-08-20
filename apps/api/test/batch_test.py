#!/usr/bin/env python3
"""
Batch test all seed AI employees against a suite of questions.

Seeds a temporary SQLite database once, then runs every employee × every
question through the full LangGraph agent graph, printing compact comparison
tables so you can eyeball response style, AI-isms, and human-likeness across
employees at a glance.

Usage::

    # Run all questions against all employees
    python -m test.batch_test

    # Run a subset of questions (matches text in the question string)
    python -m test.batch_test --questions "Hi" "Policies" "summary"

    # Run a subset of employees (matches specialization slug)
    python -m test.batch_test --employees hr support

    # Show raw LLM output (before formatter cleanup) alongside final response
    python -m test.batch_test --show-raw

    # Quiet mode — only print responses, no per-question headers
    python -m test.batch_test --quiet
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path
from textwrap import dedent
from uuid import UUID

# ---------------------------------------------------------------------------
# Path setup — ensure `app` is importable and .env is loaded
# ---------------------------------------------------------------------------
_this_dir = Path(__file__).resolve().parent
_api_dir = _this_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

_env_path = _api_dir / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)


from langchain_core.messages import HumanMessage  # noqa: E402

from app.agent.build import build_graph  # noqa: E402
from app.agent.tools.executor import BUILT_IN_TOOLS  # noqa: E402
from app.employees.templates import get_template  # noqa: E402
from test.fixtures import (  # noqa: E402
    SEED_EMPLOYEES,
    SEED_EMPLOYEE_IDS,
    setup_test_db,
)
from test.mcp_helpers import resolve_mcp_tools  # noqa: E402

# ---------------------------------------------------------------------------
# AI-ism detection patterns (independent of formatter.py's stripper) used
# ONLY to flag leakage in the summary, not to modify responses.
# ---------------------------------------------------------------------------
_AI_ISM_DETECT = re.compile(
    r"(as an ai\b|i'?m (an? )?(ai |virtual )?assistant"
    r"|is there anything else i can help"
    r"|feel free to (ask|reach out)"
    r"|let me know if you (have|need)"
    r"|^\s*\d+\.\s+you (said|asked|mentioned|told|noted)"
    r"|^\s*\|.*\|\s*$"
    r"|good question[!.]?\s)",
    re.IGNORECASE | re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Default question suite
# ---------------------------------------------------------------------------
DEFAULT_QUESTIONS: list[str] = [
    "Hi there!",
    "Who are you?",
    "Tell me about yourself",
    "What policies do you have?",
    "Can you summarize our conversation so far?",
    "What tools do you have access to?",
    "Tell me something interesting",
]

EMPLOYEE_LABELS: dict[str, str] = {
    "hr_specialist": "Alex (HR)",
    "sales_rep": "Blake (Sales)",
    "support_agent": "Casey (Support)",
    "general": "Drew (General)",
}

# ---------------------------------------------------------------------------
# Graph builder (mirrors cli.py's _get_or_build_graph)
# ---------------------------------------------------------------------------


async def _get_or_build_graph(session, employee_id: UUID):
    from sqlalchemy import select as sa_select
    from app.employees.models import Employee

    emp = await session.scalar(
        sa_select(Employee).where(Employee.id == employee_id)
    )
    if emp is None:
        return build_graph(list(BUILT_IN_TOOLS)), list(BUILT_IN_TOOLS)

    template = get_template(emp.specialization or "general")
    mcp_tools: list = []
    if template.allowed_mcp_servers and emp.org_id:
        mcp_tools = await resolve_mcp_tools(
            session, emp.org_id, employee_id, template.allowed_mcp_servers
        )

    all_tools = list(BUILT_IN_TOOLS) + mcp_tools
    return build_graph(all_tools), all_tools


# ---------------------------------------------------------------------------
# Run a single employee × question
# ---------------------------------------------------------------------------


async def run_one(
    session_factory,
    employee_id: UUID,
    specialization: str,
    question: str,
    thread_id: str,
) -> dict:
    """Invoke the graph and return result metadata."""
    result = {
        "specialization": specialization,
        "question": question,
        "response": "",
        "raw_response": "",
        "tool_rounds": 0,
        "elapsed": 0.0,
        "error": None,
        "input_blocked": False,
        "block_reason": None,
        "guardrail_passed": True,
        "ai_ism_count": 0,
    }

    initial_state = {
        "messages": [HumanMessage(content=question)],
        "platform": "api",
        "employee_id": str(employee_id),
        "tool_round": 0,
    }

    async with session_factory() as session:
        graph, all_tools = await _get_or_build_graph(session, employee_id)

        config = {
            "configurable": {
                "db": session,
                "employee_id": str(employee_id),
                "all_tools": all_tools,
                "thread_id": thread_id,
                "platform": "api",
            }
        }

        t0 = time.monotonic()
        try:
            state = await graph.ainvoke(initial_state, config=config)
        except Exception as exc:
            result["elapsed"] = time.monotonic() - t0
            result["error"] = str(exc)
            return result
        result["elapsed"] = time.monotonic() - t0

        result["response"] = state.get("response", "") or ""
        result["raw_response"] = state.get("raw_response", "") or ""
        result["tool_rounds"] = state.get("tool_round", 0)
        result["input_blocked"] = state.get("input_blocked", False)
        result["block_reason"] = state.get("block_reason")
        result["guardrail_passed"] = state.get("output_guardrail_passed", True)
        result["ai_ism_count"] = len(_AI_ISM_DETECT.findall(result["response"]))

    return result


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

_SEP = "─" * 70


def print_question_header(q_num: int, total: int, question: str) -> None:
    print()
    print("═" * 70)
    print(f"  Q{q_num}/{total}: {question}")
    print("═" * 70)


def print_result_row(
    label: str,
    result: dict,
    show_raw: bool = False,
    quiet: bool = False,
) -> None:
    response = result["response"] or "<no response>"
    raw = result["raw_response"] or ""
    tool_str = f"🔧{result['tool_rounds']}rnd" if result["tool_rounds"] else "   "
    time_str = f"{result['elapsed']:.1f}s"

    flags = []
    if result["input_blocked"]:
        flags.append("🛡️BLOCKED")
    if not result["guardrail_passed"]:
        flags.append("🚫GUARDRAIL")
    if result["ai_ism_count"]:
        flags.append(f"🤖{result['ai_ism_count']}ai")
    if result["error"]:
        flags.append(f"❌{result['error'][:40]}")
    flag_str = f"  ({', '.join(flags)})" if flags else ""

    first_line = response.split("\n")[0] if response else "<no response>"
    rest = response.split("\n")[1:] if response else []

    if quiet:
        print(f"  {first_line}")
    else:
        print(f"  {label:<22s} {tool_str} {time_str}{flag_str}")
        print(f"  {'':22s} {first_line}")
        for line in rest:
            print(f"  {'':22s} {line}")
        if show_raw and raw and raw != response:
            print(f"  {'':22s} ── raw: {raw[:200]}")
        print()


def print_summary(all_results: list[dict]) -> None:
    """Print a final summary of AI-ism leakage per employee."""
    print(_SEP)
    print("  SUMMARY — AI-ism leakage (responses that still contain")
    print("  stock AI phrasing after the formatter cleanup)")
    print(_SEP)

    # Group by specialization
    by_spec: dict[str, list[dict]] = {}
    for r in all_results:
        by_spec.setdefault(r["specialization"], []).append(r)

    any_leaks = False
    for spec, rows in by_spec.items():
        label = EMPLOYEE_LABELS.get(spec, spec)
        leaking = [r for r in rows if r["ai_ism_count"] > 0]
        if not leaking:
            print(f"  ✅ {label:<22s} clean")
        else:
            any_leaks = True
            print(f"  ⚠️  {label:<22s} {len(leaking)}/{len(rows)} responses with AI-isms:")
            for r in leaking:
                snippet = r["response"].replace("\n", " ")[:80]
                print(f"  {'':22s}   Q: {r['question'][:40]}")
                print(f"  {'':22s}   R: {snippet}")

    if not any_leaks:
        print()
        print("  🎉 All responses clean — no AI-isms detected after formatter.")
    print()


# ---------------------------------------------------------------------------
# Interactive mode — live chat with AI-ism analysis
# ---------------------------------------------------------------------------


async def print_interactive_result(
    label: str,
    result: dict,
) -> None:
    """Print a single interactive response with AI-ism breakdown."""
    response = result["response"] or "<no response>"
    raw = result["raw_response"] or ""
    tool_str = f" 🔧{result['tool_rounds']}rnd" if result["tool_rounds"] else ""
    time_str = f" {result['elapsed']:.1f}s"

    ai_count = result["ai_ism_count"]
    ai_str = f" 🤖{ai_count} AI-isms" if ai_count else " ✅ clean"

    print(f"\n  ── {label}{tool_str}{time_str}{ai_str} ──")
    if result["error"]:
        print(f"  ❌ {result['error']}")
    else:
        print(f"  {response}")
    if raw and raw != response:
        print(f"  ── raw (before formatter): {raw[:300]}")
    print()


async def _resolve_employees(employees: list[str] | None) -> list[str]:
    """Resolve employee slugs with partial/alias matching."""
    available_slugs = {cfg["specialization"] for cfg in SEED_EMPLOYEES}
    if employees is None:
        return list(EMPLOYEE_LABELS.keys())
    resolved: list[str] = []
    for e in employees:
        if e in available_slugs:
            resolved.append(e)
            continue
        matches = [s for s in available_slugs if e.lower() in s.lower()]
        if len(matches) == 1:
            resolved.append(matches[0])
        elif len(matches) > 1:
            print(f"⚠️  '{e}' matches multiple: {matches} — skipping")
        else:
            print(f"⚠️  '{e}' matches no employees — skipping")
    if not resolved:
        print("❌ No valid employees selected. Available:", ", ".join(sorted(available_slugs)))
        sys.exit(1)
    return resolved


def _pick_employee() -> str | None:
    """Print a menu and return the chosen specialization slug."""
    available = [cfg["specialization"] for cfg in SEED_EMPLOYEES]
    print("\n📋 Employees:\n")
    for i, spec in enumerate(available, 1):
        label = EMPLOYEE_LABELS.get(spec, spec)
        print(f"  {i}. {label}")
    print(f"  {len(available)+1}. all (cycle through all)")
    print()
    choice = input(f"Pick [1-{len(available)+1}, default=4]: ").strip() or "4"
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(available):
            return available[idx]
        if idx == len(available):
            return None  # all
    except (ValueError, IndexError):
        pass
    return available[-1]


async def _interactive(
    employees: list[str] | None = None,
) -> None:
    """Interactive chat loop with employee selection and AI-ism analysis."""
    print("🤖 OpenHuman Agent Batch Test — Interactive Mode\n")

    engine, session_factory, ids = await setup_test_db(":memory:")

    if employees:
        resolved = await _resolve_employees(employees)
    else:
        spec = _pick_employee()
        resolved = [spec] if spec else [cfg["specialization"] for cfg in SEED_EMPLOYEES]

    thread_ids = {spec: f"interactive:{spec}" for spec in resolved}
    labels = [EMPLOYEE_LABELS.get(s, s) for s in resolved]
    print(f"\n🎯 Employees: {', '.join(labels)}")
    print('Type your message (or "quit"/"exit"/"q" to stop,')
    print(' "switch" to change employee, "clear" to reset threads).\n')

    try:
        while True:
            message = input("🧑 You → ").strip()
            if not message:
                continue
            if message.lower() in ("quit", "exit", "q"):
                print("👋 Goodbye!")
                break
            if message.lower() == "switch":
                spec = _pick_employee()
                if spec is None:
                    resolved[:] = [cfg["specialization"] for cfg in SEED_EMPLOYEES]
                else:
                    resolved[:] = [spec]
                thread_ids.clear()
                thread_ids.update({s: f"interactive:{s}" for s in resolved})
                labels = [EMPLOYEE_LABELS.get(s, s) for s in resolved]
                print(f"\n🎯 Switched to: {', '.join(labels)}\n")
                continue
            if message.lower() == "clear":
                thread_ids.clear()
                thread_ids.update({s: f"interactive:{s}" for s in resolved})
                print("🧹 Threads reset.\n")
                continue

            for spec in resolved:
                eid = ids[spec]
                label = EMPLOYEE_LABELS.get(spec, spec)
                result = await run_one(
                    session_factory, eid, spec, message, thread_ids[spec]
                )
                await print_interactive_result(label, result)

    except (KeyboardInterrupt, EOFError):
        print("\n👋 Goodbye!")
    finally:
        try:
            await engine.dispose()
        except (asyncio.CancelledError, Exception):
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_batch(
    employees: list[str] | None = None,
    questions: list[str] | None = None,
    show_raw: bool = False,
    quiet: bool = False,
    interactive: bool = False,
) -> None:
    if interactive:
        await _interactive(employees=employees)
        return

    employees = await _resolve_employees(employees)
    questions = questions or DEFAULT_QUESTIONS

    print(f"🧪 Batch testing {len(employees)} employee(s) × {len(questions)} question(s)")
    print(f"   Model: {os.getenv('OPENAI_MODEL', 'gpt-4o-mini')}")
    print(f"   Employees: {', '.join(EMPLOYEE_LABELS[e] for e in employees)}")
    print()

    # Seed DB once
    print("🔧 Seeding test database … ", end="", flush=True)
    engine, session_factory, ids = await setup_test_db(":memory:")
    print("done.")

    all_results: list[dict] = []
    total = len(employees) * len(questions)
    completed = 0

    t_start = time.monotonic()

    for q_idx, question in enumerate(questions, 1):
        if not quiet:
            print_question_header(q_idx, len(questions), question)

        for spec in employees:
            eid = ids[spec]
            thread_id = f"batch:{spec}:{q_idx}"

            result = await run_one(
                session_factory, eid, spec, question, thread_id
            )
            all_results.append(result)
            completed += 1

            if not quiet:
                label = EMPLOYEE_LABELS.get(spec, spec)
                print_result_row(label, result, show_raw=show_raw, quiet=quiet)

        # Progress
        pct = completed / total * 100
        elapsed = time.monotonic() - t_start
        print(f"  ⏱️  {completed}/{total} ({pct:.0f}%) — {elapsed:.1f}s elapsed")
        if not quiet:
            print(_SEP)

    total_elapsed = time.monotonic() - t_start

    print()
    print("═" * 70)
    print(f"  ✅ DONE — {completed} invocations in {total_elapsed:.1f}s")
    print("═" * 70)

    print_summary(all_results)

    await engine.dispose()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch test AI employees against a question suite.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent("""\
        Examples:
          python -m test.batch_test
          python -m test.batch_test --employees hr support
          python -m test.batch_test --questions "Hi" "Policies" --show-raw
          python -m test.batch_test --quiet
          python -m test.batch_test -i
          python -m test.batch_test -i --employees support
        """),
    )
    parser.add_argument(
        "--employees", "-e",
        type=str,
        nargs="*",
        default=None,
        help="Specialization slugs to test (default: all). "
             f"Options: {', '.join(EMPLOYEE_LABELS)}",
    )
    parser.add_argument(
        "--questions", "-q",
        type=str,
        nargs="*",
        default=None,
        help="Question text to test. If given, only questions whose text "
             "contains the given substring(s) are run.",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Show raw LLM output (before formatter cleanup) next to final response.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-question headers and stats; just print responses.",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive chat mode with live AI-ism analysis per response.",
    )
    args = parser.parse_args()

    try:
        if args.interactive:
            asyncio.run(run_batch(
                employees=args.employees,
                interactive=True,
            ))
            return

        questions = DEFAULT_QUESTIONS
        if args.questions:
            questions = [q for q in DEFAULT_QUESTIONS if any(
                kw.lower() in q.lower() for kw in args.questions
            )]
            if not questions:
                print("❌ No questions matched your filters.")
                print(f"   Available questions: {DEFAULT_QUESTIONS}")
                sys.exit(1)

        asyncio.run(run_batch(
            employees=args.employees,
            questions=questions,
            show_raw=args.show_raw,
            quiet=args.quiet,
        ))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
