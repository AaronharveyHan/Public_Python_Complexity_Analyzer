"""Tests for backend.analyzer.complexity — McCabe CC counting."""
import ast
import sys
import pytest

from backend.analyzer.complexity import _compute_cc, ComplexityInfo


def _func_node(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """Parse *source* and return the first function/async-function node."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise ValueError("No function definition found in source")


class TestBaseComplexity:
    def test_empty_function_is_one(self):
        src = "def foo():\n    pass"
        assert _compute_cc(_func_node(src)) == 1

    def test_only_return_is_one(self):
        src = "def foo():\n    return 42"
        assert _compute_cc(_func_node(src)) == 1

    def test_async_function_base_is_one(self):
        src = "async def foo():\n    pass"
        assert _compute_cc(_func_node(src)) == 1


class TestDecisionPoints:
    def test_if_adds_one(self):
        src = "def foo(x):\n    if x:\n        pass"
        assert _compute_cc(_func_node(src)) == 2

    def test_elif_counted_via_nested_if(self):
        # elif desugars to else: if …, so counts as an additional If node
        src = (
            "def foo(x):\n"
            "    if x == 1:\n"
            "        pass\n"
            "    elif x == 2:\n"
            "        pass\n"
        )
        assert _compute_cc(_func_node(src)) == 3

    def test_for_loop_adds_one(self):
        src = "def foo(items):\n    for x in items:\n        pass"
        assert _compute_cc(_func_node(src)) == 2

    def test_while_loop_adds_one(self):
        src = "def foo():\n    while True:\n        break"
        assert _compute_cc(_func_node(src)) == 2

    def test_except_handler_adds_one(self):
        src = (
            "def foo():\n"
            "    try:\n"
            "        pass\n"
            "    except Exception:\n"
            "        pass\n"
        )
        assert _compute_cc(_func_node(src)) == 2

    def test_multiple_except_handlers(self):
        src = (
            "def foo():\n"
            "    try:\n"
            "        pass\n"
            "    except ValueError:\n"
            "        pass\n"
            "    except TypeError:\n"
            "        pass\n"
        )
        assert _compute_cc(_func_node(src)) == 3

    def test_ternary_ifexp_adds_one(self):
        src = "def foo(x):\n    return 1 if x else 0"
        assert _compute_cc(_func_node(src)) == 2

    def test_assert_does_not_count(self):
        # assert is not a standard McCabe decision point
        src = "def foo(x):\n    assert x > 0\n    return x"
        assert _compute_cc(_func_node(src)) == 1


class TestBooleanOperators:
    def test_and_two_operands_adds_one(self):
        # a and b → BoolOp with 2 values → len - 1 = 1
        src = "def foo(a, b):\n    return a and b"
        assert _compute_cc(_func_node(src)) == 2

    def test_and_three_operands_adds_two(self):
        # a and b and c → BoolOp with 3 values → len - 1 = 2
        src = "def foo(a, b, c):\n    return a and b and c"
        assert _compute_cc(_func_node(src)) == 3

    def test_or_two_operands_adds_one(self):
        src = "def foo(a, b):\n    return a or b"
        assert _compute_cc(_func_node(src)) == 2

    def test_nested_bool_ops(self):
        # (a and b) or (c and d) → outer Or(2) + inner And(2) + inner And(2)
        # = 1 + 1 + 1 = 3 total bool edges; plus base 1 = 4
        src = "def foo(a, b, c, d):\n    return (a and b) or (c and d)"
        assert _compute_cc(_func_node(src)) == 4


class TestComprehensions:
    def test_list_comp_no_filter_adds_one(self):
        # [x for x in items] → comprehension(ifs=[]) → 1+0 = 1
        src = "def foo(items):\n    return [x for x in items]"
        assert _compute_cc(_func_node(src)) == 2

    def test_list_comp_one_filter_adds_two(self):
        # [x for x in items if x>0] → comprehension(ifs=[…]) → 1+1 = 2
        src = "def foo(items):\n    return [x for x in items if x > 0]"
        assert _compute_cc(_func_node(src)) == 3

    def test_list_comp_two_filters_adds_three(self):
        # [x for x in items if x>0 if x<100] → ifs=[…,…] → 1+2 = 3
        src = "def foo(items):\n    return [x for x in items if x > 0 if x < 100]"
        assert _compute_cc(_func_node(src)) == 4

    def test_generator_expression_counted(self):
        src = "def foo(items):\n    return sum(x for x in items)"
        assert _compute_cc(_func_node(src)) == 2


class TestCombinedComplexity:
    def test_multiple_decision_points(self):
        src = (
            "def foo(x, y):\n"
            "    if x:\n"
            "        for i in range(x):\n"
            "            if i > y:\n"
            "                pass\n"
            "    return x\n"
        )
        # base(1) + if(1) + for(1) + if(1) = 4
        assert _compute_cc(_func_node(src)) == 4

    def test_complex_function_exceeds_threshold(self):
        # Build a function whose CC is clearly above 10
        branches = "\n    ".join(
            f"if x == {i}:\n        pass" for i in range(11)
        )
        src = f"def big(x):\n    {branches}"
        cc = _compute_cc(_func_node(src))
        assert cc > 10


class TestAsyncDecisionPoints:
    def test_async_for_adds_one(self):
        src = (
            "async def foo(items):\n"
            "    async for x in items:\n"
            "        pass\n"
        )
        assert _compute_cc(_func_node(src)) == 2

    def test_async_for_with_if_body(self):
        # base(1) + async for(1) + if(1) = 3
        src = (
            "async def foo(items):\n"
            "    async for x in items:\n"
            "        if x:\n"
            "            pass\n"
        )
        assert _compute_cc(_func_node(src)) == 3

    def test_multiple_async_for_loops(self):
        src = (
            "async def foo(a, b):\n"
            "    async for x in a:\n"
            "        pass\n"
            "    async for y in b:\n"
            "        pass\n"
        )
        assert _compute_cc(_func_node(src)) == 3

    def test_async_for_equivalent_to_sync_for(self):
        sync_src  = "def foo(items):\n    for x in items:\n        pass\n"
        async_src = "async def foo(items):\n    async for x in items:\n        pass\n"
        assert _compute_cc(_func_node(sync_src)) == _compute_cc(_func_node(async_src))


@pytest.mark.skipif(sys.version_info < (3, 10), reason="match/case requires Python 3.10+")
class TestMatchStatement:
    def test_match_one_case(self):
        src = (
            "def foo(x):\n"
            "    match x:\n"
            "        case 1:\n"
            "            pass\n"
        )
        # base(1) + 1 case = 2
        assert _compute_cc(_func_node(src)) == 2

    def test_match_two_cases(self):
        src = (
            "def foo(x):\n"
            "    match x:\n"
            "        case 1:\n"
            "            pass\n"
            "        case 2:\n"
            "            pass\n"
        )
        # base(1) + 2 cases = 3
        assert _compute_cc(_func_node(src)) == 3

    def test_match_five_cases(self):
        cases = "\n".join(
            f"        case {i}:\n            pass" for i in range(5)
        )
        src = f"def foo(x):\n    match x:\n{cases}\n"
        assert _compute_cc(_func_node(src)) == 6  # base + 5

    def test_match_with_wildcard_case(self):
        src = (
            "def foo(x):\n"
            "    match x:\n"
            "        case 1:\n"
            "            pass\n"
            "        case _:\n"
            "            pass\n"
        )
        # wildcard is still a case arm
        assert _compute_cc(_func_node(src)) == 3

    def test_match_case_with_guard_bool_op(self):
        src = (
            "def foo(x, y):\n"
            "    match x:\n"
            "        case 1 if x > 0 and y > 0:\n"
            "            pass\n"
        )
        # base(1) + 1 case + 1 bool-op (and) = 3
        assert _compute_cc(_func_node(src)) == 3

    def test_match_plus_if_in_body(self):
        src = (
            "def foo(x):\n"
            "    match x:\n"
            "        case 1:\n"
            "            if x > 0:\n"
            "                pass\n"
            "        case 2:\n"
            "            pass\n"
        )
        # base(1) + 2 cases + 1 if = 4
        assert _compute_cc(_func_node(src)) == 4
