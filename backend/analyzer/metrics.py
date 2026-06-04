"""
File-level metrics: LOC, SLOC, blank lines, comment lines.
"""
from __future__ import annotations

import io
import token as _token
import tokenize as _tokenize
from pathlib import Path
from dataclasses import dataclass
from typing import List


@dataclass
class LineMetrics:
    loc: int = 0           # total lines
    sloc: int = 0          # source lines (non-empty, non-comment)
    blank: int = 0         # blank lines
    comment: int = 0       # comment-only lines


# Tokenize token types that carry no line-content signal.
_TOKENIZE_SKIP: frozenset[int] = frozenset({
    _token.NEWLINE, _token.NL, _token.INDENT,
    _token.DEDENT, _token.ENDMARKER, _tokenize.ENCODING,
})


def count_lines(source: str) -> LineMetrics:
    """Parse line metrics using tokenize for accurate COMMENT vs STRING classification.

    Naive text scanning misclassifies ``#``-prefixed lines inside triple-quoted
    strings as comment lines, understating SLOC.  Using tokenize.generate_tokens
    ensures only genuine COMMENT tokens reduce the comment count.
    """
    lines = source.splitlines()
    loc = len(lines)
    if loc == 0:
        return LineMetrics()

    has_code:    list[bool] = [False] * loc  # line touched by a non-comment token
    has_comment: list[bool] = [False] * loc  # line has a real COMMENT token

    try:
        for tok_type, _, (srow, _), (erow, _), _ in _tokenize.generate_tokens(
            io.StringIO(source).readline
        ):
            if tok_type in _TOKENIZE_SKIP:
                continue
            lo = srow - 1               # convert to 0-indexed
            hi = min(erow, loc)         # STRING tokens span multiple lines
            if tok_type == _token.COMMENT:
                for lno in range(lo, hi):
                    has_comment[lno] = True
            else:
                for lno in range(lo, hi):
                    has_code[lno] = True
        tokenized = True
    except _tokenize.TokenError:
        tokenized = False

    if not tokenized:
        # Graceful fallback for source that cannot be tokenized (e.g. syntax errors).
        blank = comment = 0
        for raw in lines:
            s = raw.strip()
            if not s:
                blank += 1
            elif s.startswith("#"):
                comment += 1
        return LineMetrics(loc=loc, sloc=max(loc - blank - comment, 0),
                           blank=blank, comment=comment)

    blank = comment = 0
    for i, raw in enumerate(lines):
        if not raw.strip() and not has_code[i]:
            # Visually blank AND not spanned by any token (e.g. a multiline
            # string whose interior contains an empty line is still SLOC).
            blank += 1
        elif has_comment[i] and not has_code[i]:
            comment += 1
    return LineMetrics(loc=loc, sloc=max(loc - blank - comment, 0),
                       blank=blank, comment=comment)


_DEFAULT_IGNORE: frozenset[str] = frozenset({
    "venv", ".venv", "env", ".env",
    ".git", "__pycache__", ".tox", ".mypy_cache",
    "node_modules", "dist", "build", ".pytest_cache",
    ".eggs",
})


def collect_file_paths(
    project_path: Path,
    ignore_dirs: set[str] | None = None,
    *,
    follow_symlinks: bool = False,
) -> List[Path]:
    """Recursively collect all .py files, skipping common noise directories.

    *ignore_dirs* is merged with (not a replacement for) the built-in defaults.

    By default, symlinks that point **outside the project root** are skipped:
    a ``.py`` symlink (or a symlinked directory) targeting e.g. ``/etc`` or a
    sibling of the project would otherwise be read and surfaced in the report,
    escaping the analysed tree (and the API's ``ALLOWED_BASE_DIR`` guard).
    Pass ``follow_symlinks=True`` to opt back into the unrestricted behaviour.
    """
    effective_ignore = _DEFAULT_IGNORE | set(ignore_dirs or [])
    root_real = project_path.resolve()
    files: List[Path] = []
    for p in sorted(project_path.rglob("*.py")):
        if any(part in effective_ignore for part in p.parts):
            continue
        if any(part.endswith(".egg-info") for part in p.parts):
            continue
        if not follow_symlinks:
            # Resolve symlinks and ensure the real target stays within the
            # project root. Confines analysis to the tree the caller asked for.
            try:
                real = p.resolve()
            except (OSError, RuntimeError):
                continue  # broken symlink or resolution loop
            if real != root_real and not real.is_relative_to(root_real):
                continue
        files.append(p)
    return files
