"""Tests for backend.analyzer.functions — extraction and duplicate detection."""
import ast
import pytest

from backend.analyzer.functions import (
    extract_functions,
    detect_duplicates,
    FunctionDetail,
    LONG_FUNC_THRESHOLD,
    HIGH_CC_THRESHOLD,
)


def _make_fn(
    qualname: str = "foo",
    file: str = "a.py",
    loc: int = 10,
    body_hash: str = "abc123",
) -> FunctionDetail:
    """Build a minimal FunctionDetail for duplicate-detection tests."""
    return FunctionDetail(
        name=qualname.split(".")[-1],
        qualname=qualname,
        file=file,
        line_start=1,
        line_end=loc,
        loc=loc,
        complexity=1,
        n_params=0,
        annotated_params=0,
        n_typeable_params=0,
        has_return_annotation=False,
        is_long=False,
        is_high_complexity=False,
        is_many_params=False,
        body_hash=body_hash,
    )


class TestExtractFunctions:
    def test_empty_source_returns_empty(self):
        assert extract_functions("", "test.py") == []

    def test_syntax_error_returns_empty(self):
        assert extract_functions("def foo(: pass", "test.py") == []

    def test_simple_function_extracted(self):
        src = "def foo():\n    pass"
        funcs = extract_functions(src, "test.py")
        assert len(funcs) == 1
        fn = funcs[0]
        assert fn.name == "foo"
        assert fn.qualname == "foo"
        assert fn.file == "test.py"

    def test_function_complexity_computed(self):
        src = "def foo():\n    pass"
        funcs = extract_functions(src, "test.py")
        assert funcs[0].complexity == 1

    def test_function_loc_computed(self):
        src = "def foo():\n    x = 1\n    return x"  # 3 lines
        funcs = extract_functions(src, "test.py")
        assert funcs[0].loc == 3

    def test_method_has_qualified_name(self):
        src = "class Foo:\n    def bar(self):\n        pass"
        funcs = extract_functions(src, "test.py")
        assert any(f.qualname == "Foo.bar" for f in funcs)

    def test_nested_function_qualified_name(self):
        src = (
            "def outer():\n"
            "    def inner():\n"
            "        pass\n"
        )
        funcs = extract_functions(src, "test.py")
        qualnames = {f.qualname for f in funcs}
        assert "outer" in qualnames
        assert "outer.inner" in qualnames

    def test_async_function_extracted(self):
        src = "async def fetch():\n    pass"
        funcs = extract_functions(src, "test.py")
        assert len(funcs) == 1
        assert funcs[0].name == "fetch"

    def test_multiple_functions(self):
        src = "def foo():\n    pass\n\ndef bar():\n    pass"
        funcs = extract_functions(src, "test.py")
        names = {f.name for f in funcs}
        assert names == {"foo", "bar"}

    def test_high_complexity_flag_set(self):
        branches = "\n    ".join(
            f"if x == {i}:\n        pass" for i in range(HIGH_CC_THRESHOLD)
        )
        src = f"def complex_fn(x):\n    {branches}"
        funcs = extract_functions(src, "test.py")
        assert funcs[0].is_high_complexity

    def test_normal_complexity_flag_not_set(self):
        src = "def simple(x):\n    return x + 1"
        funcs = extract_functions(src, "test.py")
        assert not funcs[0].is_high_complexity

    def test_long_function_flag_set(self):
        lines = "\n".join(f"    x_{i} = {i}" for i in range(LONG_FUNC_THRESHOLD))
        src = f"def long_fn():\n{lines}"
        funcs = extract_functions(src, "test.py")
        assert funcs[0].is_long

    def test_short_function_flag_not_set(self):
        src = "def short():\n    return 1"
        funcs = extract_functions(src, "test.py")
        assert not funcs[0].is_long

    def test_n_params_no_args(self):
        funcs = extract_functions("def foo():\n    pass", "t.py")
        assert funcs[0].n_params == 0

    def test_n_params_positional(self):
        funcs = extract_functions("def foo(a, b, c):\n    pass", "t.py")
        assert funcs[0].n_params == 3

    def test_n_params_includes_self(self):
        src = "class C:\n    def method(self, x, y):\n        pass"
        funcs = extract_functions(src, "t.py")
        fn = next(f for f in funcs if f.name == "method")
        assert fn.n_params == 3

    def test_n_params_vararg_and_kwarg(self):
        funcs = extract_functions("def foo(a, *args, **kwargs):\n    pass", "t.py")
        assert funcs[0].n_params == 3

    def test_n_params_kwonly(self):
        funcs = extract_functions("def foo(a, *, b, c):\n    pass", "t.py")
        assert funcs[0].n_params == 3

    def test_is_many_params_flag(self):
        funcs = extract_functions("def foo(a, b, c, d, e, f):\n    pass", "t.py")
        assert funcs[0].is_many_params

    def test_is_many_params_not_set_for_few(self):
        funcs = extract_functions("def foo(a, b):\n    pass", "t.py")
        assert not funcs[0].is_many_params

    def test_annotated_params_none_when_no_annotations(self):
        funcs = extract_functions("def foo(a, b):\n    pass", "t.py")
        assert funcs[0].annotated_params == 0

    def test_annotated_params_all_typed(self):
        funcs = extract_functions("def foo(a: int, b: str) -> bool:\n    pass", "t.py")
        fn = funcs[0]
        assert fn.annotated_params == 2
        assert fn.n_typeable_params == 2
        assert fn.has_return_annotation is True

    def test_self_excluded_from_typeable_params(self):
        src = "class C:\n    def method(self, x: int):\n        pass"
        funcs = extract_functions(src, "t.py")
        fn = next(f for f in funcs if f.name == "method")
        assert fn.n_typeable_params == 1
        assert fn.annotated_params == 1

    def test_cls_excluded_from_typeable_params(self):
        src = "class C:\n    @classmethod\n    def cm(cls, x):\n        pass"
        funcs = extract_functions(src, "t.py")
        fn = next(f for f in funcs if f.name == "cm")
        assert fn.n_typeable_params == 1
        assert fn.annotated_params == 0

    def test_partial_annotation(self):
        funcs = extract_functions("def foo(a: int, b):\n    pass", "t.py")
        fn = funcs[0]
        assert fn.annotated_params == 1
        assert fn.n_typeable_params == 2

    def test_return_annotation_detected(self):
        funcs = extract_functions("def foo() -> None:\n    pass", "t.py")
        assert funcs[0].has_return_annotation is True

    def test_no_return_annotation(self):
        funcs = extract_functions("def foo():\n    pass", "t.py")
        assert funcs[0].has_return_annotation is False

    def test_no_params_has_zero_typeable(self):
        funcs = extract_functions("def foo():\n    pass", "t.py")
        assert funcs[0].n_typeable_params == 0
        assert funcs[0].annotated_params == 0

    def test_body_hash_same_for_identical_source(self):
        src = "def foo():\n    x = 1\n    return x"
        f1 = extract_functions(src, "a.py")[0]
        f2 = extract_functions(src, "b.py")[0]
        assert f1.body_hash == f2.body_hash

    def test_body_hash_differs_for_different_source(self):
        f1 = extract_functions("def foo():\n    return 1", "a.py")[0]
        f2 = extract_functions("def foo():\n    return 2", "a.py")[0]
        assert f1.body_hash != f2.body_hash

    def test_pre_parsed_tree_accepted(self):
        src = "def foo():\n    pass"
        tree = ast.parse(src)
        funcs = extract_functions(src, "test.py", tree=tree)
        assert len(funcs) == 1

    def test_file_attribute_stored(self):
        src = "def foo():\n    pass"
        funcs = extract_functions(src, "pkg/module.py")
        assert funcs[0].file == "pkg/module.py"


class TestDetectDuplicates:
    def test_no_duplicates_when_hashes_differ(self):
        fns = [
            _make_fn("foo", "a.py", 10, "hash_a"),
            _make_fn("bar", "b.py", 10, "hash_b"),
        ]
        detect_duplicates(fns)
        assert not any(f.is_duplicate for f in fns)

    def test_second_occurrence_marked_duplicate(self):
        fns = [
            _make_fn("foo", "a.py", 10, "same"),
            _make_fn("bar", "b.py", 10, "same"),
        ]
        detect_duplicates(fns)
        assert not fns[0].is_duplicate
        assert fns[1].is_duplicate

    def test_duplicate_of_set_to_first_occurrence(self):
        fns = [
            _make_fn("foo", "a.py", 10, "same"),
            _make_fn("bar", "b.py", 10, "same"),
        ]
        detect_duplicates(fns)
        assert fns[1].duplicate_of == "a.py::foo"

    def test_trivial_functions_excluded(self):
        # loc <= 5 → skip duplicate check
        fns = [
            _make_fn("foo", "a.py", 5, "same"),
            _make_fn("bar", "b.py", 5, "same"),
        ]
        detect_duplicates(fns)
        assert not any(f.is_duplicate for f in fns)

    def test_loc_6_is_eligible_for_duplicate(self):
        fns = [
            _make_fn("foo", "a.py", 6, "same"),
            _make_fn("bar", "b.py", 6, "same"),
        ]
        detect_duplicates(fns)
        assert fns[1].is_duplicate

    def test_three_copies_all_after_first_marked(self):
        fns = [
            _make_fn("foo", "a.py", 10, "same"),
            _make_fn("bar", "b.py", 10, "same"),
            _make_fn("baz", "c.py", 10, "same"),
        ]
        detect_duplicates(fns)
        assert not fns[0].is_duplicate
        assert fns[1].is_duplicate
        assert fns[2].is_duplicate

    def test_real_source_duplicate_detected(self):
        src = (
            "def dup_fn():\n"
            "    a = 1\n"
            "    b = 2\n"
            "    c = 3\n"
            "    d = 4\n"
            "    return a + b + c + d\n"
        )
        fns_a = extract_functions(src, "a.py")
        fns_b = extract_functions(src, "b.py")
        detect_duplicates(fns_a + fns_b)
        assert fns_b[0].is_duplicate

    def test_whitespace_difference_still_duplicate(self):
        # Hash normalizes whitespace, so indentation differences shouldn't matter
        src1 = "def foo():\n    x = 1\n    return x"
        src2 = "def foo():\n    x  =  1\n    return  x"  # extra spaces
        fns_a = extract_functions(src1, "a.py")
        fns_b = extract_functions(src2, "b.py")
        # Both hashes normalize whitespace, so they match
        assert fns_a[0].body_hash == fns_b[0].body_hash
