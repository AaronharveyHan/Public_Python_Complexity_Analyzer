"""Integration tests for backend.analyzer.core.analyze_project."""
import pytest
from pathlib import Path

from backend.analyzer.core import analyze_project


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


class TestAnalyzeProjectShape:
    def test_empty_project_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="No Python files"):
            analyze_project(tmp_path)

    def test_result_has_top_level_keys(self, tmp_path):
        _write(tmp_path / "main.py", "def hello():\n    return 'hi'")
        result = analyze_project(tmp_path)
        for key in ("summary", "files", "dependency_graph",
                    "top_complex_functions", "project_name", "project_path"):
            assert key in result, f"missing key: {key}"

    def test_project_name_is_directory_name(self, tmp_path):
        _write(tmp_path / "app.py", "x = 1")
        result = analyze_project(tmp_path)
        assert result["project_name"] == tmp_path.name

    def test_string_path_accepted(self, tmp_path):
        _write(tmp_path / "mod.py", "x = 1")
        result = analyze_project(str(tmp_path))
        assert "summary" in result

    def test_dependency_graph_has_required_keys(self, tmp_path):
        _write(tmp_path / "mod.py", "x = 1")
        graph = analyze_project(tmp_path)["dependency_graph"]
        assert "nodes" in graph
        assert "edges" in graph
        assert "cycles" in graph


class TestAnalyzeProjectSummary:
    def test_total_files_count(self, tmp_path):
        _write(tmp_path / "a.py", "def foo():\n    pass")
        _write(tmp_path / "b.py", "def bar():\n    pass")
        s = analyze_project(tmp_path)["summary"]
        assert s["total_files"] == 2

    def test_total_functions_count(self, tmp_path):
        _write(tmp_path / "a.py", "def foo():\n    pass")
        _write(tmp_path / "b.py", "def bar():\n    pass")
        s = analyze_project(tmp_path)["summary"]
        assert s["total_functions"] == 2

    def test_avg_complexity_simple_functions(self, tmp_path):
        _write(tmp_path / "a.py", "def foo():\n    pass")
        s = analyze_project(tmp_path)["summary"]
        assert s["avg_complexity"] == 1.0

    def test_high_complexity_functions_counted(self, tmp_path):
        branches = "\n    ".join(f"if x == {i}:\n        pass" for i in range(11))
        _write(tmp_path / "complex.py", f"def big(x):\n    {branches}")
        s = analyze_project(tmp_path)["summary"]
        assert s["high_complexity_functions"] >= 1

    def test_duplicate_functions_detected(self, tmp_path):
        body = (
            "def dup_fn():\n"
            "    a = 1\n"
            "    b = 2\n"
            "    c = 3\n"
            "    d = 4\n"
            "    return a + b + c + d\n"
        )
        _write(tmp_path / "x.py", body)
        _write(tmp_path / "y.py", body)
        s = analyze_project(tmp_path)["summary"]
        assert s["duplicate_functions"] >= 1

    def test_cycle_count_detected(self, tmp_path):
        _write(tmp_path / "a.py", "from b import foo\ndef foo(): pass")
        _write(tmp_path / "b.py", "from a import foo\ndef foo(): pass")
        s = analyze_project(tmp_path)["summary"]
        assert s["cycle_count"] >= 1

    def test_elapsed_seconds_present(self, tmp_path):
        _write(tmp_path / "mod.py", "x = 1")
        s = analyze_project(tmp_path)["summary"]
        assert s["elapsed_seconds"] >= 0


class TestAnalyzeProjectFiles:
    def test_each_file_has_risk_score(self, tmp_path):
        _write(tmp_path / "mod.py", "def fn():\n    pass")
        files = analyze_project(tmp_path)["files"]
        for fi in files:
            assert "risk_score" in fi
            assert "risk_grade" in fi

    def test_ignore_dirs_respected(self, tmp_path):
        skip = tmp_path / "skip_me"
        skip.mkdir()
        _write(skip / "hidden.py", "def secret(): pass")
        _write(tmp_path / "visible.py", "def public(): pass")
        files = analyze_project(tmp_path, ignore_dirs={"skip_me"})["files"]
        paths = [f["relative_path"] for f in files]
        assert not any("hidden" in p for p in paths)
        assert any("visible" in p for p in paths)

    def test_annotation_rate_in_file_info(self, tmp_path):
        _write(tmp_path / "mod.py", "def fn(a: int) -> bool:\n    return True")
        fi = analyze_project(tmp_path)["files"][0]
        assert "annotation_rate" in fi
        assert fi["annotation_rate"] == 1.0

    def test_annotation_rate_none_for_file_with_no_functions(self, tmp_path):
        _write(tmp_path / "mod.py", "X = 1")
        fi = analyze_project(tmp_path)["files"][0]
        assert fi["annotation_rate"] is None

    def test_fn_dict_has_annotation_fields(self, tmp_path):
        _write(tmp_path / "mod.py", "def fn(a: int, b) -> bool:\n    return True")
        fns = analyze_project(tmp_path)["files"][0]["functions"]
        fn  = fns[0]
        assert "annotated_params"      in fn
        assert "n_typeable_params"     in fn
        assert "has_return_annotation" in fn
        assert "annotation_coverage"   in fn
        assert fn["annotated_params"]      == 1
        assert fn["n_typeable_params"]     == 2
        assert fn["has_return_annotation"] is True


class TestAnnotationCoverageSummary:
    def test_annotation_coverage_in_summary(self, tmp_path):
        _write(tmp_path / "mod.py", "def fn():\n    pass")
        s = analyze_project(tmp_path)["summary"]
        assert "annotation_coverage" in s

    def test_fully_annotated_project_coverage_is_one(self, tmp_path):
        _write(tmp_path / "mod.py", "def fn(a: int) -> bool:\n    return True")
        s = analyze_project(tmp_path)["summary"]
        assert s["annotation_coverage"] == 1.0

    def test_unannotated_project_coverage_is_zero(self, tmp_path):
        _write(tmp_path / "mod.py", "def fn(a, b):\n    pass")
        s = analyze_project(tmp_path)["summary"]
        assert s["annotation_coverage"] == 0.0


class TestProgressCallback:
    def test_callback_invoked(self, tmp_path):
        _write(tmp_path / "app.py", "x = 1")
        calls = []
        analyze_project(tmp_path, progress_cb=lambda pct, msg: calls.append(pct))
        assert len(calls) > 0

    def test_last_progress_is_100(self, tmp_path):
        _write(tmp_path / "app.py", "x = 1")
        calls = []
        analyze_project(tmp_path, progress_cb=lambda pct, msg: calls.append(pct))
        assert calls[-1] == 100

    def test_progress_is_non_decreasing(self, tmp_path):
        _write(tmp_path / "a.py", "def foo():\n    pass")
        _write(tmp_path / "b.py", "def bar():\n    pass")
        calls = []
        analyze_project(tmp_path, progress_cb=lambda pct, msg: calls.append(pct))
        for i in range(1, len(calls)):
            assert calls[i] >= calls[i - 1], f"progress went backwards at step {i}"
