"""Tests for the statistical helpers in experiments/stats.py. Run from the repo root with: python -m pytest"""

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from experiments.stats import compare, holm, paired


def results(values):
    """Long table (scenario, seed, kpi) from {scenario: values per seed}."""
    return pd.DataFrame([{"scenario": s, "seed": i, "kpi": v}
                         for s, vals in values.items() for i, v in enumerate(vals)])


def test_holm_matches_hand_calculation():
    assert holm([0.01, 0.04, 0.03, np.nan]) == pytest.approx([0.03, 0.06, 0.06, np.nan], nan_ok=True)
    assert np.all(holm([0.5, 0.9]) <= 1.0)


def test_identical_scenarios_are_flagged_not_tested():
    base = np.linspace(100, 200, 30)
    t, pairs = compare(results({"a": base, "b": base + 1e-12, "c": base - 1e-12}), "kpi")
    assert t["identical"].iloc[0]
    assert np.isnan(t["friedman_p"].iloc[0]) and np.isnan(t["rm_anova_p"].iloc[0])
    assert pairs["identical"].all() and pairs["p_holm_t"].isna().all()


def test_paired_tests_see_a_small_shift_that_independent_tests_miss():
    """Same seeds in every scenario: a large seed effect and a small, consistent scenario shift."""
    rng = np.random.default_rng(0)
    seed_effect = rng.normal(0, 100, 30)
    data = {s: 1000 + seed_effect + shift + rng.normal(0, 1, 30) for s, shift in [("a", 0), ("b", 3), ("c", 6)]}
    t, pairs = compare(results(data), "kpi")
    assert t["friedman_p"].iloc[0] < 1e-6 and t["rm_anova_p_gg"].iloc[0] < 1e-6
    assert (pairs["p_holm_wilcoxon"] < 0.01).all()
    assert stats.kruskal(*data.values()).pvalue > 0.5  # treating scenarios as independent groups hides it


def test_paired_difference_and_percentage():
    df = results({"a": [110, 120, 130], "b": [100, 100, 100]})
    r = paired(df, "kpi", "a", "b")
    assert r["mean_diff"] == pytest.approx(20) and r["diff_pct"] == pytest.approx(20)
    assert not r["identical"]


def test_brief_keeps_one_p_value_and_formats_it():
    from experiments.stats import brief, fmt_p
    assert fmt_p(1e-20) == "< 0.001" and fmt_p(0.0204) == "0.020" and fmt_p(float("nan")) == "–"
    rng = np.random.default_rng(1)
    base = rng.normal(100, 10, 30)
    t, pairs = compare(results({"a": base, "b": base + 5 + rng.normal(0, 1, 30), "c": base}), "kpi")
    short = brief(pairs)
    assert list(short.columns) == ["a", "b", "difference (a − b)", "95% CI", "difference %", "p (Wilcoxon, Holm)"]
    assert short.loc[1, "p (Wilcoxon, Holm)"] == "identical"  # a vs c
    assert list(brief(t).columns) == ["Friedman p", "Kendall's W"]
