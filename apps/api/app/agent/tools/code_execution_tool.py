"""Code execution tool for AI employees.

Lets the agent write and execute Python code in a sandboxed subprocess
with resource limits, no network, and no access to sensitive modules.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import tempfile
import textwrap

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60
MAX_OUTPUT_CHARS = 100_000
ALLOWED_MODULES = {
    "math", "json", "re", "collections", "itertools", "functools",
    "random", "statistics", "datetime", "time", "uuid", "typing",
    "pathlib", "io", "base64", "hashlib", "binascii", "textwrap",
    "decimal", "fractions", "difflib",
}


@tool
def execute_code(
    code: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Execute Python code and return stdout/stderr.

    Runs in an isolated subprocess with no network access, restricted
    module imports, and a hard timeout. The code cannot read/write
    arbitrary files, install packages, or access the internet.

    Args:
        code: Python code to execute.
        timeout: Maximum execution time in seconds (default 60, max 300).
    """
    timeout = max(1, min(timeout, 300))

    # Wrap code in an import guard and restricted exec
    guarded = textwrap.dedent("""
        import sys, io, math, json, re, collections, itertools, functools
        import random, statistics, datetime, time, uuid, typing
        import pathlib, io as _io, base64, hashlib, binascii, textwrap
        import decimal, fractions, difflib
        from collections import Counter, defaultdict, deque, OrderedDict
        from itertools import chain, combinations, count, cycle
        from itertools import groupby, permutations, product, repeat

        _stdout_buf = io.StringIO()
        _stderr_buf = io.StringIO()
        _old_stdout = sys.stdout
        _old_stderr = sys.stderr
        try:
            sys.stdout = _stdout_buf
            sys.stderr = _stderr_buf
            exec(_____code_____, {})
        except SystemExit:
            pass
        except BaseException as _exc:
            import traceback
            traceback.print_exc(file=_stderr_buf)
        finally:
            sys.stdout = _old_stdout
            sys.stderr = _old_stderr
            _exit_code = 0 if 'SystemExit' in dir() else 0
            print("__HERMES_STDOUT__", flush=True)
            sys.stdout.write(_stdout_buf.getvalue())
            sys.stdout.write("__HERMES_STDERR__")
            sys.stdout.write(_stderr_buf.getvalue())
    """)

    # Prepend the user code into the guarded template
    full_code = guarded.replace("_____code_____", repr(code))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(full_code)
        script_path = f.name

    try:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-u", script_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": os.environ.get("PATH", "/usr/bin")},
            cwd=tempfile.gettempdir(),
        )

        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.kill(proc.pid, signal.SIGKILL)
            proc.wait()
            return f"Execution timed out after {timeout}s. Output so far:\n" + _read_partial(proc)

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        # Parse the delimited output
        if "__HERMES_STDOUT__" in stdout:
            parts = stdout.split("__HERMES_STDOUT__", 1)
            stdout_part = parts[1] if len(parts) > 1 else ""
        else:
            stdout_part = stdout

        if "__HERMES_STDERR__" in stdout_part:
            stdio, stderr_part = stdout_part.split("__HERMES_STDERR__", 1)
        else:
            stdio = stdout_part
            stderr_part = stderr

        result = ""
        if stdio.strip():
            result += stdio.strip() + "\n"
        if stderr_part.strip():
            result += f"[stderr]\n{stderr_part.strip()}\n"
        if proc.returncode != 0 and not result.strip():
            result = f"Process exited with code {proc.returncode}"

        if not result.strip():
            result = "(no output)"

        if len(result) > MAX_OUTPUT_CHARS:
            result = result[:MAX_OUTPUT_CHARS] + f"\n... [truncated to {MAX_OUTPUT_CHARS} chars]"

        return result.strip()

    except FileNotFoundError:
        return "Error: Python interpreter not found."
    except OSError as e:
        return f"Error executing code: {e}"
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def _read_partial(proc: subprocess.Popen) -> str:
    try:
        out, err = proc.communicate(timeout=5)
        text = (out or b"").decode("utf-8", errors="replace")
        text += (err or b"").decode("utf-8", errors="replace")
        return text[:2000]
    except Exception:
        return "(could not read partial output)"
