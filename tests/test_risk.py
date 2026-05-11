"""Tests for backend.analyzer.risk — normalization, grading, and risk scoring."""
import pytest

from backend.analyzer.risk import compute_risk_scores, _normalize, _grade


class TestNormalize:
    def test_lo_equals_hi_returns_zero(self):
        assert _normalize(5.0, 5.0, 5.0) == 0.0

    def test_value_at_lo_returns_zero(self):
        assert _normalize(0.0, 0.0, 100.0) == 0.0

    def test_value_at_hi_returns_hundred(self):
        assert _normalize(100.0, 0.0, 100.0) == 100.0

    def test_midpoint_returns_fifty(self):
        assert _normalize(50.0, 0.0, 100.0) == 50.0

    def test_clamps_below_zero(self):
        assert _normalize(-10.0, 0.0, 100.0) == 0.0

    def test_clamps_above_hundred(self):
        assert _normalize(200.0, 0.0, 100.0) == 100.0

    def test_proportional_scaling(self):
        result = _normalize(25.0, 0.0, 100.0)
        assert abs(result - 25.0) < 1e-9


class TestGrade:
    def test_a_below_20(self):
        assert _grade(0.0) == "A"
        assert _grade(19.9) == "A"

    def test_b_20_to_39(self):
        assert _grade(20.0) == "B"
        assert _grade(39.9) == "B"

    def test_c_40_to_59(self):
        assert _grade(40.0) == "C"
        assert _grade(59.9) == "C"

    def test_d_60_to_79(self):
        assert _grade(60.0) == "D"
        assert _grade(79.9) == "D"

    def test_f_80_and_above(self):
        assert _grade(80.0) == "F"
        assert _grade(100.0) == "F"


def _fi(mid, cc_avg=1.0, loc=10, funcs=None):
    return {
        "module_id": mid,
        "relative_path": f"{mid}.py",
        "path": f"/project/{mid}.py",
        "complexity_avg": cc_avg,
        "loc": loc,
        "functions": funcs or [],
    }


class TestComputeRiskScores:
    def test_empty_list_returns_empty(self):
        assert compute_risk_scores([]) == {}

    def test_all_modules_scored(self):
        fis = [_fi(f"mod{i}") for i in range(4)]
        scores = compute_risk_scores(fis)
        assert len(scores) == 4

    def test_scores_in_0_to_100_range(self):
        fis = [_fi("a", cc_avg=1.0, loc=10), _fi("b", cc_avg=15.0, loc=1000)]
        for risk in compute_risk_scores(fis).values():
            assert 0.0 <= risk.risk_score <= 100.0

    def test_grade_assigned(self):
        fis = [_fi("mod")]
        risk = compute_risk_scores(fis)["mod"]
        assert risk.grade in {"A", "B", "C", "D", "F"}

    def test_single_file_low_complexity_not_max_risk(self):
        # Before fix, a single file always got score ~70 due to self-normalisation.
        # With absolute floor caps (cc≥10, loc≥500), a tiny clean module stays low.
        fis = [_fi("clean", cc_avg=1.0, loc=10)]
        risk = compute_risk_scores(fis)["clean"]
        assert risk.risk_score < 30
        assert risk.grade in {"A", "B"}

    def test_high_cc_file_scores_higher_than_low_cc(self):
        fis = [_fi("low", cc_avg=1.0, loc=50), _fi("high", cc_avg=20.0, loc=50)]
        scores = compute_risk_scores(fis)
        assert scores["high"].risk_score > scores["low"].risk_score

    def test_large_file_scores_higher_than_small(self):
        fis = [_fi("small", cc_avg=1.0, loc=10), _fi("large", cc_avg=1.0, loc=2000)]
        scores = compute_risk_scores(fis)
        assert scores["large"].risk_score > scores["small"].risk_score

    def test_hcc_ratio_increases_score(self):
        high_fn = {"qualname": "bad", "is_high_complexity": True, "is_duplicate": False}
        low_fn  = {"qualname": "ok",  "is_high_complexity": False, "is_duplicate": False}
        fi_bad  = _fi("bad_mod", cc_avg=2.0, loc=50, funcs=[high_fn])
        fi_good = _fi("good_mod", cc_avg=2.0, loc=50, funcs=[low_fn])
        scores = compute_risk_scores([fi_bad, fi_good])
        assert scores["bad_mod"].risk_score > scores["good_mod"].risk_score

    def test_duplicate_ratio_increases_score(self):
        dup_fn  = {"qualname": "d", "is_high_complexity": False, "is_duplicate": True}
        norm_fn = {"qualname": "n", "is_high_complexity": False, "is_duplicate": False}
        fi_dup  = _fi("dup_mod",  cc_avg=2.0, loc=50, funcs=[dup_fn])
        fi_norm = _fi("norm_mod", cc_avg=2.0, loc=50, funcs=[norm_fn])
        scores = compute_risk_scores([fi_dup, fi_norm])
        assert scores["dup_mod"].risk_score > scores["norm_mod"].risk_score

    def test_result_contains_moduelrisk_fields(self):
        fis = [_fi("mod", cc_avg=3.0, loc=100)]
        risk = compute_risk_scores(fis)["mod"]
        assert hasattr(risk, "risk_score")
        assert hasattr(risk, "complexity_score")
        assert hasattr(risk, "size_score")
        assert hasattr(risk, "hcc_ratio")
        assert hasattr(risk, "dup_ratio")
        assert hasattr(risk, "grade")
