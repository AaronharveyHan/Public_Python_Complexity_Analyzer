"""
Function-level analysis: extraction, line count, classification.
"""
from __future__ import annotations

import ast
import hashlib
import os
from dataclasses import dataclass
from typing import List

# Override via environment variables to match your team's coding standards.
LONG_FUNC_THRESHOLD:   int = int(os.environ.get("LONG_FUNC_THRESHOLD",   "50"))
HIGH_CC_THRESHOLD:     int = int(os.environ.get("HIGH_CC_THRESHOLD",     "10"))
MANY_PARAMS_THRESHOLD: int = int(os.environ.get("MANY_PARAMS_THRESHOLD",  "5"))


@dataclass
class FunctionDetail:
    name: str
    qualname: str
    file: str                  # relative path
    line_start: int
    line_end: int
    loc: int                   # line_end - line_start + 1
    complexity: int
    n_params: int              # total parameter count
    annotated_params: int      # params with type annotations (excl. self/cls)
    n_typeable_params: int     # total params excl. self/cls (annotation target)
    has_return_annotation: bool
    is_long: bool
    is_high_complexity: bool
    is_many_params: bool       # param count exceeds MANY_PARAMS_THRESHOLD
    body_hash: str             # for duplicate detection
    is_duplicate: bool = False
    duplicate_of: str = ""     # qualname of original


def _extract_body_source(source_lines: list[str],
                         node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    start = node.lineno - 1
    end   = getattr(node, "end_lineno", node.lineno)
    return "\n".join(source_lines[start:end])


def _hash_body(body: str) -> str:
    # Normalize whitespace before hashing to catch reformatted copies
    normalized = " ".join(body.split())
    return hashlib.md5(normalized.encode()).hexdigest()


class _FuncExtractor(ast.NodeVisitor):
    def __init__(self, source: str, rel_path: str) -> None:
        self._lines  = source.splitlines()
        self._path   = rel_path
        self._prefix: list[str] = []
        self.functions: list[FunctionDetail] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._prefix.append(node.name)
        self.generic_visit(node)
        self._prefix.pop()

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        from .complexity import _compute_cc  # avoid circular at module level

        qualname  = ".".join(self._prefix + [node.name])
        end       = getattr(node, "end_lineno", node.lineno)
        loc       = end - node.lineno + 1
        cc        = _compute_cc(node)
        body_src  = _extract_body_source(self._lines, node)
        body_hash = _hash_body(body_src)
        n_params  = (
            len(node.args.args)
            + len(node.args.posonlyargs)
            + len(node.args.kwonlyargs)
            + (1 if node.args.vararg  else 0)
            + (1 if node.args.kwarg   else 0)
        )

        # Annotation coverage: exclude self/cls from typeable targets
        all_args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
        if node.args.vararg:
            all_args = all_args + [node.args.vararg]
        if node.args.kwarg:
            all_args = all_args + [node.args.kwarg]
        typeable   = all_args[1:] if all_args and all_args[0].arg in ("self", "cls") else all_args
        n_typeable = len(typeable)
        annotated  = sum(1 for a in typeable if a.annotation is not None)
        has_return = node.returns is not None

        self.functions.append(FunctionDetail(
            name                 = node.name,
            qualname             = qualname,
            file                 = self._path,
            line_start           = node.lineno,
            line_end             = end,
            loc                  = loc,
            complexity           = cc,
            n_params             = n_params,
            annotated_params     = annotated,
            n_typeable_params    = n_typeable,
            has_return_annotation= has_return,
            is_long              = loc >= LONG_FUNC_THRESHOLD,
            is_high_complexity   = cc >= HIGH_CC_THRESHOLD,
            is_many_params       = n_params > MANY_PARAMS_THRESHOLD,
            body_hash            = body_hash,
        ))
        self._prefix.append(node.name)
        self.generic_visit(node)
        self._prefix.pop()

    visit_FunctionDef      = _visit_func
    visit_AsyncFunctionDef = _visit_func


def extract_functions(
    source: str,
    rel_path: str,
    tree: ast.AST | None = None,
) -> list[FunctionDetail]:
    """Parse *source* and return a FunctionDetail for every function/method.

    If *tree* is provided (pre-parsed AST) it is used directly, saving a
    redundant ``ast.parse`` call when the caller already holds the tree.
    """
    if tree is None:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
    extractor = _FuncExtractor(source, rel_path)
    extractor.visit(tree)
    return extractor.functions


def detect_duplicates(all_functions: list[FunctionDetail]) -> list[FunctionDetail]:
    """
    Mark duplicates in-place (same normalized body hash).
    The first occurrence keeps is_duplicate=False; subsequent ones are marked.
    Short trivial functions (loc <= 5) are excluded.
    """
    seen: dict[str, str] = {}   # hash → qualname of first occurrence
    for fn in all_functions:
        if fn.loc <= 5:
            continue
        if fn.body_hash in seen:
            fn.is_duplicate  = True
            fn.duplicate_of  = seen[fn.body_hash]
        else:
            seen[fn.body_hash] = f"{fn.file}::{fn.qualname}"
    return all_functions
