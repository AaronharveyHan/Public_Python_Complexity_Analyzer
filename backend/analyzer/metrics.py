"""
File-level metrics: LOC, SLOC, blank lines, comment lines.
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import List


@dataclass
class LineMetrics:
    loc: int = 0           # total lines
    sloc: int = 0          # source lines (non-empty, non-comment)
    blank: int = 0         # blank lines
    comment: int = 0       # comment-only lines


def count_lines(source: str) -> LineMetrics:
    """Parse line metrics from raw source text."""
    lines = source.splitlines()
    loc = len(lines)
    blank = 0
    comment = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            blank += 1
        elif stripped.startswith("#"):
            comment += 1
    sloc = max(loc - blank - comment, 0)
    return LineMetrics(loc=loc, sloc=sloc, blank=blank, comment=comment)


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
