"""
AST-based cyclomatic complexity (McCabe).

Complexity = 1 + number of decision points in a function/method.
Decision points: if, elif (counted via test), for, async for, while,
                 except handler, ternary (IfExp), boolean operators
                 (and/or add N-1 edges), comprehension conditions,
                 match/case arms (Python 3.10+).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass
class ComplexityInfo:
    name: str
    qualname: str          # e.g. "ClassName.method_name"
    line_start: int
    line_end: int
    complexity: int
    is_method: bool = False


class _CCVisitor(ast.NodeVisitor):
    """Count decision edges inside a function body."""

    def __init__(self) -> None:
        self.count = 1  # base complexity

    # ── hard decision points ──────────────────────────────────────────────
    def visit_If(self, node: ast.If) -> None:
        self.count += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.count += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.count += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.count += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.count += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        # ternary: a if cond else b
        self.count += 1
        self.generic_visit(node)

    # ── boolean short-circuit: each extra operand = +1 edge ──────────────
    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.count += len(node.values) - 1
        self.generic_visit(node)

    # ── comprehension filters ─────────────────────────────────────────────
    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.count += 1 + len(node.ifs)
        self.generic_visit(node)

    # ── match/case (Python 3.10+) ─────────────────────────────────────────
    def visit_Match(self, node: ast.Match) -> None:  # type: ignore[attr-defined]
        # Each case arm is a decision point, analogous to elif.
        # Guards (case X if cond:) are visited by generic_visit and counted
        # if they contain bool operators or nested conditions.
        self.count += len(node.cases)
        self.generic_visit(node)


def _compute_cc(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    v = _CCVisitor()
    v.visit(func_node)
    return v.count


