"""Tests for backend.api.report — HTML report generation."""
import pytest
from backend.api.report import (
    generate_html_report,
    _esc, _risk_color, _cc_color, _grade_color, _grade,
    _kpi, _badge,
    _func_table_rows, _module_table_rows, _dup_table_rows, _long_table_rows,
)


# ── helpers ───────────────────────────────────────────────────────────────────

class TestEsc:
    def test_plain_string(self):
        assert _esc("hello") == "hello"

    def test_escapes_html_entities(self):
        escaped = _esc("<script>alert('xss')</script>")
        assert "<script>" not in escaped   # raw tag must not appear
        assert "&lt;" in escaped            # less-than is encoded
        assert _esc("<b>") == "&lt;b&gt;"
        assert _esc("a & b") == "a &amp; b"
        assert _esc('"quoted"') == "&quot;quoted&quot;"

    def test_none_becomes_dash(self):
        assert _esc(None) == "–"

    def test_number_becomes_string(self):
        assert _esc(42) == "42"
        assert _esc(3.14) == "3.14"


class TestRiskColor:
    def test_low_risk(self):
        assert _risk_color(0)  == "#16a34a"
        assert _risk_color(19) == "#16a34a"

    def test_medium_low(self):
        assert _risk_color(20) == "#65a30d"
        assert _risk_color(39) == "#65a30d"

    def test_medium(self):
        assert _risk_color(40) == "#ca8a04"
        assert _risk_color(59) == "#ca8a04"

    def test_high(self):
        assert _risk_color(60) == "#ea580c"
        assert _risk_color(79) == "#ea580c"

    def test_critical(self):
        assert _risk_color(80)  == "#dc2626"
        assert _risk_color(100) == "#dc2626"


class TestCcColor:
    def test_low(self):
        assert _cc_color(1) == "#16a34a"
        assert _cc_color(5) == "#16a34a"

    def test_medium(self):
        assert _cc_color(6)  == "#ca8a04"
        assert _cc_color(10) == "#ca8a04"

    def test_high(self):
        assert _cc_color(11) == "#ea580c"
        assert _cc_color(20) == "#ea580c"

    def test_critical(self):
        assert _cc_color(21) == "#dc2626"
        assert _cc_color(99) == "#dc2626"


class TestGrade:
    def test_all_grades(self):
        assert _grade(0)   == "A"
        assert _grade(19)  == "A"
        assert _grade(20)  == "B"
        assert _grade(39)  == "B"
        assert _grade(40)  == "C"
        assert _grade(59)  == "C"
        assert _grade(60)  == "D"
        assert _grade(79)  == "D"
        assert _grade(80)  == "F"
        assert _grade(100) == "F"


class TestGradeColor:
    def test_known_grades(self):
        assert _grade_color("A") == "#16a34a"
        assert _grade_color("B") == "#65a30d"
        assert _grade_color("C") == "#ca8a04"
        assert _grade_color("D") == "#ea580c"
        assert _grade_color("F") == "#dc2626"

    def test_unknown_grade_is_gray(self):
        assert _grade_color("") == "#6b7280"
        assert _grade_color(None) == "#6b7280"


class TestKpi:
    def test_contains_label_and_value(self):
        html = _kpi("Risk Score", 42.5, "#ff0000")
        assert "Risk Score" in html
        assert "42.5" in html
        assert "#ff0000" in html

    def test_optional_sub_included_when_provided(self):
        html = _kpi("Grade", "B", sub="Grade B")
        assert "Grade B" in html
        assert "kpi-sub" in html

    def test_no_sub_element_when_empty(self):
        html = _kpi("Files", 10)
        assert "kpi-sub" not in html

    def test_xss_in_label_escaped(self):
        html = _kpi("<script>", "x")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# ── table row builders ────────────────────────────────────────────────────────

def _make_func(**kwargs):
    defaults = {
        "qualname":           "module.func",
        "file":               "app.py",
        "line_start":         10,
        "loc":                20,
        "complexity":         5,
        "n_params":           2,
        "is_high_complexity": False,
        "is_long":            False,
        "is_duplicate":       False,
        "is_many_params":     False,
        "annotation_coverage": 1.0,
    }
    return {**defaults, **kwargs}


def _make_file(**kwargs):
    defaults = {
        "relative_path":  "app/module.py",
        "loc":            100,
        "sloc":           80,
        "n_functions":    5,
        "complexity_avg": 3.0,
        "complexity_max": 8,
        "risk_score":     25.0,
        "risk_grade":     "B",
        "annotation_rate": 0.75,
        "functions":      [],
    }
    return {**defaults, **kwargs}


class TestFuncTableRows:
    def test_basic_row_contains_fields(self):
        html = _func_table_rows([_make_func(qualname="foo.bar", loc=15, complexity=7)])
        assert "foo.bar" in html
        assert "app.py"  in html
        assert "15"      in html
        assert "7"       in html

    def test_high_cc_badge_shown(self):
        html = _func_table_rows([_make_func(is_high_complexity=True)])
        assert "High CC" in html

    def test_long_badge_shown(self):
        html = _func_table_rows([_make_func(is_long=True)])
        assert "Long" in html

    def test_dup_badge_shown(self):
        html = _func_table_rows([_make_func(is_duplicate=True)])
        assert "Dup" in html

    def test_no_badges_for_clean_func(self):
        html = _func_table_rows([_make_func()])
        assert "High CC" not in html
        assert "Long"    not in html
        assert "Dup"     not in html

    def test_xss_in_qualname_escaped(self):
        html = _func_table_rows([_make_func(qualname="<script>alert(1)</script>")])
        assert "<script>" not in html

    def test_empty_list_returns_empty_string(self):
        assert _func_table_rows([]) == ""

    def test_multiple_rows(self):
        funcs = [_make_func(qualname=f"fn{i}") for i in range(3)]
        html = _func_table_rows(funcs)
        assert html.count("<tr>") == 3


class TestModuleTableRows:
    def test_sorted_by_risk_descending(self):
        files = [
            _make_file(relative_path="low.py",  risk_score=10.0),
            _make_file(relative_path="high.py", risk_score=90.0),
            _make_file(relative_path="med.py",  risk_score=50.0),
        ]
        html = _module_table_rows(files)
        assert html.index("high.py") < html.index("med.py") < html.index("low.py")

    def test_grade_badge_present(self):
        html = _module_table_rows([_make_file(risk_grade="A")])
        assert "A" in html

    def test_high_max_cc_colored_red(self):
        html = _module_table_rows([_make_file(complexity_max=15)])
        assert "#dc2626" in html

    def test_row_index_numbers(self):
        files = [_make_file(relative_path=f"f{i}.py") for i in range(3)]
        html  = _module_table_rows(files)
        assert "<td" in html  # basic sanity


class TestDupTableRows:
    def test_basic_dup_row(self):
        fn = _make_func(qualname="dup.func", file="b.py", duplicate_of="a.py::orig")
        fn["duplicate_of"] = "a.py::orig"
        html = _dup_table_rows([fn])
        assert "dup.func"  in html
        assert "a.py::orig" in html

    def test_empty_returns_empty(self):
        assert _dup_table_rows([]) == ""


class TestLongTableRows:
    def test_basic_long_row(self):
        fn = _make_func(qualname="big.func", loc=120, complexity=8)
        html = _long_table_rows([fn])
        assert "big.func" in html
        assert "120"      in html

    def test_empty_returns_empty(self):
        assert _long_table_rows([]) == ""


# ── full HTML report ──────────────────────────────────────────────────────────

def _minimal_result(**kwargs):
    base = {
        "project_name": "test_project",
        "project_path": "/tmp/test_project",
        "summary": {
            "total_files": 2,
            "failed_files": 0,
            "total_loc": 200,
            "total_sloc": 150,
            "total_functions": 5,
            "avg_complexity": 3.0,
            "max_complexity": 8,
            "high_complexity_functions": 0,
            "long_functions": 0,
            "duplicate_functions": 0,
            "duplicate_rate": 0.0,
            "annotation_coverage": 0.8,
            "cycle_count": 0,
            "risk_score": 25.0,
            "elapsed_seconds": 0.5,
        },
        "files": [],
        "failed_files": [],
        "top_complex_functions": [],
        "long_functions": [],
        "duplicate_functions": [],
        "dependency_graph": {"nodes": [], "edges": [], "cycles": []},
    }
    base.update(kwargs)
    return base


class TestGenerateHtmlReport:
    def test_returns_valid_html(self):
        html = generate_html_report(_minimal_result())
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_project_name_in_title(self):
        html = generate_html_report(_minimal_result())
        assert "test_project" in html

    def test_kpi_cards_present(self):
        html = generate_html_report(_minimal_result())
        assert "Risk Score"  in html
        assert "Total Files" in html
        assert "Avg CC"      in html

    def test_grade_badge_rendered(self):
        html = generate_html_report(_minimal_result())
        # risk_score=25 → grade B
        assert ">B<" in html

    def test_no_cycles_section_when_empty(self):
        html = generate_html_report(_minimal_result())
        assert "Circular Dependencies" not in html

    def test_cycles_section_shown_when_present(self):
        result = _minimal_result()
        result["dependency_graph"] = {
            "nodes": [], "edges": [],
            "cycles": [["mod_a", "mod_b"]],
        }
        html = generate_html_report(result)
        assert "Circular Dependencies" in html
        assert "mod_a" in html

    def test_no_dup_section_when_empty(self):
        html = generate_html_report(_minimal_result())
        assert "Duplicate Functions" not in html

    def test_dup_section_shown(self):
        fn = _make_func(qualname="dup.fn")
        fn["duplicate_of"] = "orig.fn"
        result = _minimal_result(duplicate_functions=[fn])
        html = generate_html_report(result)
        assert "Duplicate Functions" in html
        assert "dup.fn" in html

    def test_no_long_section_when_empty(self):
        html = generate_html_report(_minimal_result())
        assert "Long Functions" not in html

    def test_long_section_shown(self):
        fn = _make_func(qualname="big.fn", loc=200)
        result = _minimal_result(long_functions=[fn])
        html = generate_html_report(result)
        assert "Long Functions" in html
        assert "big.fn" in html

    def test_failed_files_section_shown(self):
        result = _minimal_result(failed_files=[
            {"path": "broken.py", "reason": "syntax_error", "detail": "line 5: invalid syntax"}
        ])
        html = generate_html_report(result)
        assert "Skipped Files" in html
        assert "broken.py"    in html
        assert "syntax_error" in html

    def test_no_failed_section_when_empty(self):
        html = generate_html_report(_minimal_result())
        assert "Skipped Files" not in html

    def test_truncation_notice_shown_for_large_dup_list(self):
        fns = [_make_func(qualname=f"fn{i}") for i in range(35)]
        for fn in fns:
            fn["duplicate_of"] = "orig"
        result = _minimal_result(duplicate_functions=fns)
        html = generate_html_report(result)
        assert "Showing first 30 of 35" in html

    def test_no_truncation_notice_for_small_list(self):
        fns = [_make_func(qualname=f"fn{i}") for i in range(5)]
        for fn in fns:
            fn["duplicate_of"] = "orig"
        result = _minimal_result(duplicate_functions=fns)
        html = generate_html_report(result)
        assert "Showing first" not in html

    def test_xss_in_project_name_escaped(self):
        result = _minimal_result(project_name='<script>alert("xss")</script>')
        html = generate_html_report(result)
        assert '<script>alert("xss")</script>' not in html
        assert "&lt;script&gt;" in html

    def test_chart_data_script_safe(self):
        # Closing-tag sequence must be escaped to avoid breaking <script> block
        result = _minimal_result()
        result["files"] = [_make_file(relative_path="</script>evil.py")]
        html = generate_html_report(result)
        assert "</script>evil" not in html

    def test_echarts_cdn_script_included(self):
        html = generate_html_report(_minimal_result())
        assert "echarts" in html

    def test_print_stylesheet_included(self):
        html = generate_html_report(_minimal_result())
        assert "@media print" in html

    def test_type_coverage_kpi_shown(self):
        html = generate_html_report(_minimal_result())
        assert "Type Coverage" in html

    def test_type_coverage_percentage_rendered(self):
        result = _minimal_result()
        result["summary"]["annotation_coverage"] = 0.75
        html = generate_html_report(result)
        assert "75%" in html

    def test_no_untyped_section_when_all_annotated(self):
        result = _minimal_result()
        result["files"] = [_make_file(functions=[_make_func(annotation_coverage=1.0)])]
        html = generate_html_report(result)
        assert "Unannotated Functions" not in html

    def test_untyped_section_shown_when_present(self):
        fn = _make_func(qualname="bare.func", annotation_coverage=0)
        result = _minimal_result()
        result["files"] = [_make_file(functions=[fn])]
        html = generate_html_report(result)
        assert "Unannotated Functions" in html
        assert "bare.func" in html

    def test_untyped_sorted_by_params_descending(self):
        fn_few  = _make_func(qualname="few_params",  n_params=1, annotation_coverage=0)
        fn_many = _make_func(qualname="many_params", n_params=5, annotation_coverage=0)
        result = _minimal_result()
        result["files"] = [_make_file(functions=[fn_few, fn_many])]
        html = generate_html_report(result)
        assert html.index("many_params") < html.index("few_params")

    def test_no_types_badge_in_func_row(self):
        html = _func_table_rows([_make_func(annotation_coverage=0)])
        assert "No Types" in html

    def test_no_types_badge_absent_when_annotated(self):
        html = _func_table_rows([_make_func(annotation_coverage=1.0)])
        assert "No Types" not in html

    def test_annot_column_in_module_row(self):
        html = _module_table_rows([_make_file(annotation_rate=0.6)])
        assert "60%" in html

    def test_annot_column_none_shows_dash(self):
        html = _module_table_rows([_make_file(annotation_rate=None)])
        assert "–" in html
