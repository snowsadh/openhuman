"""Tests for code_execution_tool module."""

from __future__ import annotations


class TestExecuteCode:
    def test_simple_print(self):
        from app.agent.tools.code_execution_tool import execute_code

        result = execute_code.invoke({"code": "print('hello world')"})
        assert "hello world" in result

    def test_math(self):
        from app.agent.tools.code_execution_tool import execute_code

        result = execute_code.invoke({"code": "print(2 ** 10)"})
        assert "1024" in result

    def test_stdout_and_stderr(self):
        from app.agent.tools.code_execution_tool import execute_code

        result = execute_code.invoke(
            {"code": "import sys; sys.stderr.write('err msg'); print('out msg')"}
        )
        assert "out msg" in result
        assert "err msg" in result

    def test_syntax_error(self):
        from app.agent.tools.code_execution_tool import execute_code

        result = execute_code.invoke({"code": "def broken("})
        assert "SyntaxError" in result or "syntax" in result.lower()

    def test_exception_handled(self):
        from app.agent.tools.code_execution_tool import execute_code

        result = execute_code.invoke({"code": "1/0"})
        assert "ZeroDivisionError" in result

    def test_timeout_enforced(self):
        from app.agent.tools.code_execution_tool import execute_code

        result = execute_code.invoke({"code": "import time; time.sleep(10)", "timeout": 2})
        assert "timed out" in result.lower()

    def test_no_output(self):
        from app.agent.tools.code_execution_tool import execute_code

        result = execute_code.invoke({"code": "x = 42"})
        assert "no output" in result.lower()
