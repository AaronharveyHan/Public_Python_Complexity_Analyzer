"""
Risk scoring per module.

Risk score (0–100) is a weighted combination of:
  - Normalized cyclomatic complexity   (40%)
  - Normalized LOC                     (30%)
  - High-CC function ratio             (20%)
  - Duplicate code ratio               (10%)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ModuleRisk:
    module_id: str
    file: str
    risk_score: float          # 0–100
    complexity_score: float
    size_score: float
    hcc_ratio: float           # fraction of high-CC functions
    dup_ratio: float           # fraction of duplicate functions
    grade: str                 # A/B/C/D/F


def _grade(score: float) -> str:
    if score < 20:  return "A"
    if score < 40:  return "B"
    if score < 60:  return "C"
    if score < 80:  return "D"
    return "F"


def _normalize(value: float, lo: float, hi: float) -> float:
    """Scale *value* to 0–100 between lo and hi."""
    if hi <= lo:
        return 0.0
    return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100))


def compute_risk_scores(file_infos: list[dict]) -> Dict[str, ModuleRisk]:
    """
    Compute per-module risk from the list of file info dicts produced by
    core.py.  Returns {module_id: ModuleRisk}.
    """
    if not file_infos:
        return {}

    # Global max values for normalization.
    # Use absolute floor caps so that a single-file project (where the one
    # file would otherwise always normalise to 100) is scored fairly against
    # known-good thresholds rather than against itself.
    all_cc_avg = [f.get("complexity_avg", 0) for f in file_infos]
    all_loc    = [f.get("loc", 0)            for f in file_infos]
    # CC floor: avg CC of 10 is already high; floor ensures meaningful scale
    max_cc_avg = max(max(all_cc_avg, default=0), 10.0)
    # LOC floor: 500 lines is a medium-sized module
    max_loc    = max(max(all_loc, default=0), 500)

    risks: Dict[str, ModuleRisk] = {}
    for fi in file_infos:
        mid      = fi.get("module_id", fi.get("relative_path", fi["path"]))
        cc_avg   = fi.get("complexity_avg", 0)
        loc      = fi.get("loc", 0)
        funcs    = fi.get("functions", [])
        n_funcs  = len(funcs)

        hcc_count = sum(1 for fn in funcs if fn.get("is_high_complexity"))
        dup_count = sum(1 for fn in funcs if fn.get("is_duplicate"))
        hcc_ratio = (hcc_count / n_funcs) if n_funcs else 0.0
        dup_ratio = (dup_count / n_funcs) if n_funcs else 0.0

        cc_score  = _normalize(cc_avg, 0, max_cc_avg)
        sz_score  = _normalize(loc, 0, max_loc)
        score = (
            0.40 * cc_score
            + 0.30 * sz_score
            + 0.20 * hcc_ratio * 100
            + 0.10 * dup_ratio * 100
        )
        risks[mid] = ModuleRisk(
            module_id        = mid,
            file             = fi.get("relative_path", fi["path"]),
            risk_score       = round(score, 1),
            complexity_score = round(cc_score, 1),
            size_score       = round(sz_score, 1),
            hcc_ratio        = round(hcc_ratio, 3),
            dup_ratio        = round(dup_ratio, 3),
            grade            = _grade(score),
        )
    return risks
