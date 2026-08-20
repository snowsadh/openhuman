"""Tests for file_tools module."""

from __future__ import annotations

import os
import tempfile

# =============================================================================
# file_read
# =============================================================================


class TestFileRead:
    def test_reads_text_file(self):
        from app.agent.tools.file_tools import file_read

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            fpath = f.name
        try:
            result = file_read.invoke({"path": fpath})
            assert "1|line1" in result
            assert "2|line2" in result
            assert "3|line3" in result
        finally:
            os.unlink(fpath)

    def test_pagination(self):
        from app.agent.tools.file_tools import file_read

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for i in range(1, 101):
                f.write(f"line{i}\n")
            fpath = f.name
        try:
            result = file_read.invoke({"path": fpath, "offset": 10, "limit": 3})
            assert "10|line10" in result
            assert "11|line11" in result
            assert "12|line12" in result
            assert not result.startswith("1|line1")
        finally:
            os.unlink(fpath)

    def test_file_not_found(self):
        from app.agent.tools.file_tools import file_read

        result = file_read.invoke({"path": "/nonexistent/file.txt"})
        assert "not found" in result.lower()

    def test_binary_extension_rejected(self):
        from app.agent.tools.file_tools import file_read

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            fpath = f.name
        try:
            result = file_read.invoke({"path": fpath})
            assert "binary" in result.lower()
        finally:
            os.unlink(fpath)

    def test_large_file_limit(self):
        from app.agent.tools.file_tools import file_read

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("x" * (60 * 1024 * 1024))
            fpath = f.name
        try:
            result = file_read.invoke({"path": fpath})
            assert "exceeds" in result.lower()
        finally:
            os.unlink(fpath)

    def test_truncated_hint(self):
        from app.agent.tools.file_tools import file_read

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for i in range(100):
                f.write(f"line{i}\n")
            fpath = f.name
        try:
            result = file_read.invoke({"path": fpath, "offset": 1, "limit": 10})
            assert "continue" in result.lower()
        finally:
            os.unlink(fpath)


# =============================================================================
# file_write
# =============================================================================


class TestFileWrite:
    def test_writes_new_file(self):
        from app.agent.tools.file_tools import file_write

        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "test.txt")
            result = file_write.invoke({"path": fpath, "content": "hello world"})
            assert "success" in result.lower()
            assert os.path.isfile(fpath)
            assert open(fpath).read() == "hello world"

    def test_creates_parent_dirs(self):
        from app.agent.tools.file_tools import file_write

        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "a", "b", "c", "test.txt")
            result = file_write.invoke({"path": fpath, "content": "nested"})
            assert "success" in result.lower()
            assert os.path.isfile(fpath)

    def test_refuses_sensitive_path(self):
        from app.agent.tools.file_tools import file_write

        result = file_write.invoke({"path": "/etc/hacked.conf", "content": "evil"})
        assert "refusing" in result.lower()


# =============================================================================
# file_search
# =============================================================================


class TestFileSearch:
    def test_finds_matches(self):
        from app.agent.tools.file_tools import file_search

        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "test.py")
            with open(fpath, "w") as f:
                f.write("def hello():\n    pass\n\ndef world():\n    pass\n")
            result = file_search.invoke({"pattern": "def ", "path": tmp})
            assert "hello" in result
            assert "world" in result
            assert "2 match" in result

    def test_no_matches(self):
        from app.agent.tools.file_tools import file_search

        with tempfile.TemporaryDirectory() as tmp:
            fpath = os.path.join(tmp, "test.txt")
            with open(fpath, "w") as f:
                f.write("nothing here")
            result = file_search.invoke({"pattern": "ZZZZ", "path": tmp})
            assert "no matches" in result.lower()

    def test_file_glob_filter(self):
        from app.agent.tools.file_tools import file_search

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.py"), "w") as f:
                f.write("found")
            with open(os.path.join(tmp, "b.txt"), "w") as f:
                f.write("found")
            result = file_search.invoke({"pattern": "found", "path": tmp, "file_glob": "*.py"})
            assert "a.py" in result
            assert "b.txt" not in result

    def test_max_results(self):
        from app.agent.tools.file_tools import file_search

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "test.txt"), "w") as f:
                for i in range(100):
                    f.write(f"match line {i}\n")
            result = file_search.invoke({"pattern": "match", "path": tmp, "max_results": 5})
            lines = result.strip().split("\n")
            match_count = sum(1 for line in lines if line.strip().startswith("  "))
            assert match_count <= 5


# =============================================================================
# file_patch
# =============================================================================


class TestFilePatch:
    def test_replaces_text(self):
        from app.agent.tools.file_tools import file_patch

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world\nfoo bar\n")
            fpath = f.name
        try:
            result = file_patch.invoke({
                "path": fpath,
                "old_string": "hello world",
                "new_string": "HELLO WORLD",
            })
            assert "success" in result.lower()
            assert open(fpath).read() == "HELLO WORLD\nfoo bar\n"
        finally:
            os.unlink(fpath)

    def test_replace_all(self):
        from app.agent.tools.file_tools import file_patch

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("a\nb\na\n")
            fpath = f.name
        try:
            result = file_patch.invoke({
                "path": fpath,
                "old_string": "a",
                "new_string": "x",
                "replace_all": True,
            })
            assert "success" in result.lower()
            assert open(fpath).read() == "x\nb\nx\n"
        finally:
            os.unlink(fpath)

    def test_old_string_not_found(self):
        from app.agent.tools.file_tools import file_patch

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\n")
            fpath = f.name
        try:
            result = file_patch.invoke({
                "path": fpath,
                "old_string": "NONEXISTENT",
                "new_string": "x",
            })
            assert "not found" in result.lower()
        finally:
            os.unlink(fpath)

    def test_refuses_sensitive_path(self):
        from app.agent.tools.file_tools import file_patch

        result = file_patch.invoke({
            "path": "/etc/shadow",
            "old_string": "root",
            "new_string": "x",
        })
        assert "refusing" in result.lower()


# =============================================================================
# file_delete
# =============================================================================


class TestFileDelete:
    def test_deletes_file(self):
        from app.agent.tools.file_tools import file_delete

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            fpath = f.name
        assert os.path.isfile(fpath)
        result = file_delete.invoke({"path": fpath})
        assert "success" in result.lower()
        assert not os.path.isfile(fpath)

    def test_file_not_found(self):
        from app.agent.tools.file_tools import file_delete

        result = file_delete.invoke({"path": "/nonexistent/file.txt"})
        assert "not found" in result.lower()

    def test_not_a_file(self):
        from app.agent.tools.file_tools import file_delete

        with tempfile.TemporaryDirectory() as tmp:
            result = file_delete.invoke({"path": tmp})
            assert "not a file" in result.lower()

    def test_refuses_sensitive_path(self):
        from app.agent.tools.file_tools import file_delete

        result = file_delete.invoke({"path": "/etc/passwd"})
        assert "refusing" in result.lower()
