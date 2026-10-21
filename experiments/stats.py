"""Statistical analysis of experiment results (ODD section 8).

All functions take the per-run results table written by run_experiments.py
(one row per scenario x seed).
"""

import numpy as np
import pandas as pd
from scipy import stats


def ci95(x):
    """Mean and half-width of the 95% t confidence interval."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return np.mean(x) if len(x) else np.nan, np.nan
    return x.mean(), stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / np.sqrt(len(x))


def summary(df, kpis, by="scenario"):
    """Mean ± 95% CI half-width of each KPI per scenario, in the scenario order of `df`."""
    rows = {}
    for name, g in df.groupby(by, sort=False):
        row = {}
        for k in kpis:
            m, h = ci95(g[k])
            row[(k, "mean")], row[(k, "ci95")] = m, h
        rows[name] = row
    out = pd.DataFrame(rows).T
    out.columns = pd.MultiIndex.from_tuples(out.columns)
    out.index.name = by
    return out


def replication_check(df, kpis, by="scenario"):
    """Largest relative CI half-width (half-width / |mean|) of each KPI over all scenarios.

    Answers whether 30 replications give narrow enough intervals. Scenarios
    whose mean is ~0 (e.g. savings of the no-community reference) are skipped.
    """
    s = summary(df, kpis, by)
    out = {}
    for k in kpis:
        mean, half = s[(k, "mean")].astype(float), s[(k, "ci95")].astype(float)
        rel = (half / mean.abs())[mean.abs() > 1e-6]
        out[k] = {"max_rel_halfwidth": rel.max(), "worst_scenario": rel.idxmax() if len(rel) else None}
    return pd.DataFrame(out).T


def compare(df, kpi, by="scenario", scenarios=None):
    """Compare a KPI across scenarios: assumption checks, one-way ANOVA, Kruskal-Wallis and Tukey HSD.

    Returns (tests, pairs): a one-row summary of the omnibus tests and a table
    of Tukey HSD pairwise comparisons (difference of means, 95% CI, p-value).
    """
    names = scenarios or list(df[by].drop_duplicates())
    groups = [df.loc[df[by] == n, kpi].dropna().to_numpy() for n in names]

    shapiro_p = [stats.shapiro(g).pvalue if np.ptp(g) > 0 else np.nan for g in groups]
    tests = {
        "kpi": kpi,
        "min_shapiro_p": np.nanmin(shapiro_p) if not np.all(np.isnan(shapiro_p)) else np.nan,
        "levene_p": stats.levene(*groups).pvalue,
        "anova_F": np.nan, "anova_p": np.nan,
        "kruskal_H": np.nan, "kruskal_p": np.nan,
    }
    if np.ptp(np.concatenate(groups)) > 0:
        tests["anova_F"], tests["anova_p"] = stats.f_oneway(*groups)
        tests["kruskal_H"], tests["kruskal_p"] = stats.kruskal(*groups)

    tukey = stats.tukey_hsd(*groups)
    ci = tukey.confidence_interval(0.95)
    pairs = [
        {"a": names[i], "b": names[j], "mean_diff": groups[i].mean() - groups[j].mean(),
         "ci_low": ci.low[i, j], "ci_high": ci.high[i, j], "p_tukey": tukey.pvalue[i, j]}
        for i in range(len(names)) for j in range(i + 1, len(names))
    ]
    return pd.DataFrame([tests]).set_index("kpi"), pd.DataFrame(pairs)


def paired(df, kpi, a, b, by="scenario"):
    """Paired comparison of scenario a vs b on the same seeds (common random numbers).

    Returns the mean difference a - b with its 95% CI, the paired t-test and
    the Wilcoxon signed-rank test p-values.
    """
    x = df[df[by] == a].set_index("seed")[kpi]
    y = df[df[by] == b].set_index("seed")[kpi]
    d = (x - y).dropna()
    mean, half = ci95(d)
    nonzero = np.ptp(d) > 0 or d.abs().sum() > 0
    return pd.Series({
        "a": a, "b": b, "kpi": kpi, "mean_diff": mean, "ci_low": mean - half, "ci_high": mean + half,
        "p_paired_t": stats.ttest_rel(x[d.index], y[d.index]).pvalue if nonzero else np.nan,
        "p_wilcoxon": stats.wilcoxon(d).pvalue if nonzero else np.nan,
    })
