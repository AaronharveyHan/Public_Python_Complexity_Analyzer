"""Tests for backend.analyzer.metrics — line counting and file collection."""
import pytest
from pathlib import Path

from backend.analyzer.metrics import count_lines, collect_file_paths


class TestCountLines:
    def test_empty_string(self):
        m = count_lines("")
        assert m.loc == 0
        assert m.sloc == 0
        assert m.blank == 0
        assert m.comment == 0

    def test_single_code_line(self):
        m = count_lines("x = 1")
        assert m.loc == 1
        assert m.sloc == 1
        assert m.blank == 0
        assert m.comment == 0

    def test_blank_lines_counted(self):
        m = count_lines("\n\n\n")
        assert m.loc == 3
        assert m.blank == 3
        assert m.sloc == 0
        assert m.comment == 0

    def test_comment_only_lines(self):
        m = count_lines("# first\n# second")
        assert m.loc == 2
        assert m.comment == 2
        assert m.sloc == 0
        assert m.blank == 0

    def test_mixed_content(self):
        source = "x = 1\n# comment\n\ny = 2\n"
        m = count_lines(source)
        assert m.loc == 4
        assert m.sloc == 2
        assert m.blank == 1
        assert m.comment == 1

    def test_inline_comment_counts_as_sloc(self):
        # A line with code followed by a comment is still SLOC
        m = count_lines("x = 1  # inline comment")
        assert m.sloc == 1
        assert m.comment == 0

    def test_sloc_equals_loc_minus_blank_minus_comment(self):
        source = "a = 1\n# c\n\nb = 2\n\n# d\nc = 3"
        m = count_lines(source)
        assert m.sloc == m.loc - m.blank - m.comment

    def test_sloc_never_negative(self):
        m = count_lines("# only comments\n# everywhere")
        assert m.sloc == 0

    def test_whitespace_only_line_is_blank(self):
        m = count_lines("   \n\t\n")
        assert m.blank == 2
        assert m.sloc == 0


class TestCollectFilePaths:
    def test_collects_py_files(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")
        result = collect_file_paths(tmp_path)
        names = {p.name for p in result}
        assert names == {"a.py", "b.py"}

    def test_ignores_default_venv_dir(self, tmp_path):
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "lib.py").write_text("x = 1")
        (tmp_path / "app.py").write_text("y = 2")
        result = collect_file_paths(tmp_path)
        # Check by path components, not substring, to avoid false matches
        # against the pytest-generated tmp_path name (e.g. "…venv_dir0/…")
        assert all("venv" not in p.relative_to(tmp_path).parts for p in result)
        assert len(result) == 1

    def test_ignores_pycache(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "compiled.py").write_text("x = 1")
        (tmp_path / "real.py").write_text("y = 2")
        result = collect_file_paths(tmp_path)
        names = {p.name for p in result}
        assert "compiled.py" not in names
        assert "real.py" in names

    def test_custom_dirs_also_ignored(self, tmp_path):
        custom = tmp_path / "custom_ignore"
        custom.mkdir()
        (custom / "hidden.py").write_text("z = 3")
        (tmp_path / "visible.py").write_text("w = 4")
        result = collect_file_paths(tmp_path, ignore_dirs={"custom_ignore"})
        names = {p.name for p in result}
        assert "hidden.py" not in names
        assert "visible.py" in names

    def test_custom_dirs_merged_with_defaults(self, tmp_path):
        # Both custom AND default ignore dirs should be skipped
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "v.py").write_text("x = 1")
        custom = tmp_path / "mydir"
        custom.mkdir()
        (custom / "m.py").write_text("y = 2")
        (tmp_path / "keep.py").write_text("z = 3")
        result = collect_file_paths(tmp_path, ignore_dirs={"mydir"})
        names = {p.name for p in result}
        assert names == {"keep.py"}

    def test_ignores_egg_info_dirs(self, tmp_path):
        egg = tmp_path / "mypackage.egg-info"
        egg.mkdir()
        (egg / "PKG-INFO.py").write_text("x = 1")
        (tmp_path / "main.py").write_text("y = 2")
        result = collect_file_paths(tmp_path)
        names = {p.name for p in result}
        assert "PKG-INFO.py" not in names

    def test_empty_directory_returns_empty(self, tmp_path):
        result = collect_file_paths(tmp_path)
        assert result == []

    def test_nested_files_collected(self, tmp_path):
        sub = tmp_path / "pkg"
        sub.mkdir()
        (sub / "mod.py").write_text("x = 1")
        result = collect_file_paths(tmp_path)
        assert len(result) == 1
        assert result[0].name == "mod.py"

    def test_non_py_files_excluded(self, tmp_path):
        (tmp_path / "script.sh").write_text("#!/bin/bash")
        (tmp_path / "data.txt").write_text("hello")
        (tmp_path / "code.py").write_text("x = 1")
        result = collect_file_paths(tmp_path)
        assert len(result) == 1
        assert result[0].name == "code.py"
