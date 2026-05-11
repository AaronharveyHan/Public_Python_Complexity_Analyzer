"""
Main orchestrator for the complexity analysis engine.

Usage:
    from backend.analyzer import analyze_project
    result = analyze_project("/path/to/project", progress_cb=lambda p, msg: ...)
"""
from __future__ import annotations

import ast
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .metrics      import collect_file_paths, count_lines
from .functions    import extract_functions, detect_duplicates, FunctionDetail
from .dependencies import (
    parse_imports, build_dependency_graph,
    graph_to_json, _module_id,
)
from .risk         import compute_risk_scores


ProgressCB = Callable[[int, str], None]


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def _fn_annotation_rate(fn: FunctionDetail) -> float:
    total = fn.n_typeable_params + 1  # +1 for return slot
    done  = fn.annotated_params + (1 if fn.has_return_annotation else 0)
    return round(done / total, 3) if total else 1.0


def _fn_to_dict(fn: FunctionDetail) -> dict:
    return {
        "name":                  fn.name,
        "qualname":              fn.qualname,
        "file":                  fn.file,
        "line_start":            fn.line_start,
        "line_end":              fn.line_end,
        "loc":                   fn.loc,
        "complexity":            fn.complexity,
        "n_params":              fn.n_params,
        "annotated_params":      fn.annotated_params,
        "n_typeable_params":     fn.n_typeable_params,
        "has_return_annotation": fn.has_return_annotation,
        "annotation_coverage":   _fn_annotation_rate(fn),
        "is_long":               fn.is_long,
        "is_high_complexity":    fn.is_high_complexity,
        "is_many_params":        fn.is_many_params,
        "is_duplicate":          fn.is_duplicate,
        "duplicate_of":          fn.duplicate_of,
    }


# ── main entry point ──────────────────────────────────────────────────────────

def analyze_project(
    project_path: str | Path,
    ignore_dirs: set[str] | None = None,
    progress_cb: ProgressCB | None = None,
) -> dict:
    """
    Analyse a Python project and return a comprehensive result dict.

    Parameters
    ----------
    project_path : path to the project root
    ignore_dirs  : directory names to skip (adds to defaults)
    progress_cb  : optional callback(percent: int, message: str)
    """
    root = Path(project_path).resolve()
    t_start = time.time()

    def _progress(pct: int, msg: str) -> None:
        if progress_cb:
            progress_cb(pct, msg)

    _progress(0, "Starting analysis…")

    # ── 1. Collect files ─────────────────────────────────────────────────────
    _progress(5, "Collecting Python files…")
    files = collect_file_paths(root, ignore_dirs)
    n_files = len(files)
    if n_files == 0:
        raise ValueError(f"No Python files found in {root}")

    # ── 2. Per-file analysis ──────────────────────────────────────────────────
    _progress(10, f"Analysing {n_files} files…")
    file_infos: list[dict] = []
    imports_map: dict[str, list[str]] = {}
    all_functions: list[FunctionDetail] = []
    failed_files: list[dict] = []

    for idx, fpath in enumerate(files):
        pct = 10 + int(60 * idx / n_files)
        rel = str(fpath.relative_to(root))
        _progress(pct, f"Parsing {rel}")

        source = _safe_read(fpath)
        if source is None:
            failed_files.append({"path": rel, "reason": "read_error"})
            continue

        # Parse the AST once and reuse across all analysis steps.
        try:
            tree: ast.AST | None = ast.parse(source)
        except SyntaxError as exc:
            failed_files.append({
                "path":   rel,
                "reason": "syntax_error",
                "detail": f"line {exc.lineno}: {exc.msg}",
            })
            tree = None

        mid     = _module_id(fpath, root)
        lm      = count_lines(source)
        funcs   = extract_functions(source, rel, tree=tree)
        imports = parse_imports(source, tree=tree, module_id=mid)
        cc_list = [fn.complexity for fn in funcs]

        # Per-file annotation rate: average across all functions
        fn_rates = [_fn_annotation_rate(fn) for fn in funcs]
        file_annot_rate = round(sum(fn_rates) / len(fn_rates), 3) if fn_rates else None

        imports_map[mid] = imports
        all_functions.extend(funcs)

        fi: dict = {
            "path":            str(fpath),
            "relative_path":   rel,
            "module_id":       mid,
            "loc":             lm.loc,
            "sloc":            lm.sloc,
            "blank":           lm.blank,
            "comment":         lm.comment,
            "functions":       [_fn_to_dict(fn) for fn in funcs],
            "n_functions":     len(funcs),
            "n_classes":       _count_classes(tree),
            "imports":         imports,
            "complexity_avg":  round(sum(cc_list) / len(cc_list), 2) if cc_list else 0,
            "complexity_max":  max(cc_list, default=0),
            "annotation_rate": file_annot_rate,
            "risk_score":      0.0,   # filled later
        }
        file_infos.append(fi)

    # ── 3. Duplicate detection (cross-file) ───────────────────────────────────
    _progress(72, "Detecting duplicate functions…")
    detect_duplicates(all_functions)
    # Refresh is_duplicate in file_infos from updated all_functions
    fn_lookup: dict[str, bool] = {
        f"{fn.file}::{fn.qualname}": fn.is_duplicate for fn in all_functions
    }
    for fi in file_infos:
        for fn_dict in fi["functions"]:
            key = f"{fi['relative_path']}::{fn_dict['qualname']}"
            fn_dict["is_duplicate"] = fn_lookup.get(key, False)

    # ── 4. Risk scoring ───────────────────────────────────────────────────────
    _progress(78, "Computing risk scores…")
    risks = compute_risk_scores(file_infos)
    risk_map: dict[str, float] = {}
    for fi in file_infos:
        mid = fi["module_id"]
        if mid in risks:
            r = risks[mid]
            fi["risk_score"]       = r.risk_score
            fi["risk_grade"]       = r.grade
            fi["complexity_score"] = r.complexity_score
            fi["size_score"]       = r.size_score
            risk_map[mid]          = r.risk_score

    # ── 5. Dependency graph ───────────────────────────────────────────────────
    _progress(85, "Building dependency graph…")
    G, cycles = build_dependency_graph(files, root, imports_map)
    dep_graph  = graph_to_json(G, cycles, risk_map)

    # ── 6. Top lists ──────────────────────────────────────────────────────────
    _progress(92, "Building top-N lists…")
    all_fn_dicts = [_fn_to_dict(fn) for fn in all_functions]

    top_complex_funcs = sorted(
        all_fn_dicts, key=lambda f: f["complexity"], reverse=True
    )[:10]
    top_large_files = sorted(
        file_infos, key=lambda f: f["loc"], reverse=True
    )[:10]
    long_functions = [
        f for f in all_fn_dicts if f["is_long"]
    ]
    long_functions.sort(key=lambda f: f["loc"], reverse=True)

    duplicate_funcs = [
        f for f in all_fn_dicts if f["is_duplicate"]
    ]

    # ── 7. Summary ────────────────────────────────────────────────────────────
    total_loc   = sum(f["loc"]   for f in file_infos)
    total_sloc  = sum(f["sloc"]  for f in file_infos)
    cc_all      = [fn.complexity for fn in all_functions]
    n_high_cc   = sum(1 for fn in all_functions if fn.is_high_complexity)
    n_long      = sum(1 for fn in all_functions if fn.is_long)
    n_dup       = sum(1 for fn in all_functions if fn.is_duplicate)
    dup_rate    = round(n_dup / len(all_functions), 3) if all_functions else 0

    file_rates   = [fi["annotation_rate"] for fi in file_infos if fi["annotation_rate"] is not None]
    annot_cov    = round(sum(file_rates) / len(file_rates), 3) if file_rates else 0.0

    overall_risk = round(
        sum(r.risk_score for r in risks.values()) / len(risks) if risks else 0, 1
    )

    summary = {
        "total_files":              n_files,
        "failed_files":             len(failed_files),
        "total_loc":                total_loc,
        "total_sloc":               total_sloc,
        "total_functions":          len(all_functions),
        "avg_complexity":           round(sum(cc_all) / len(cc_all), 2) if cc_all else 0,
        "max_complexity":           max(cc_all, default=0),
        "high_complexity_functions": n_high_cc,
        "long_functions":           n_long,
        "duplicate_functions":      n_dup,
        "duplicate_rate":           dup_rate,
        "annotation_coverage":      annot_cov,
        "cycle_count":              len(cycles),
        "risk_score":               overall_risk,
        "elapsed_seconds":          round(time.time() - t_start, 2),
    }

    _progress(100, "Analysis complete.")

    return {
        "project_path":          str(root),
        "project_name":          root.name,
        "summary":               summary,
        "files":                 file_infos,
        "failed_files":          failed_files,
        "dependency_graph":      dep_graph,
        "top_complex_functions": top_complex_funcs,
        "top_large_files":       [_trim_file(f) for f in top_large_files],
        "long_functions":        long_functions[:20],
        "duplicate_functions":   duplicate_funcs[:20],
    }


# ── helpers ───────────────────────────────────────────────────────────────────

def _count_classes(tree: ast.AST | None) -> int:
    if tree is None:
        return 0
    return sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))


def _trim_file(fi: dict) -> dict:
    """Return a lightweight version of file_info (omit full function list)."""
    return {k: v for k, v in fi.items() if k != "functions"}
