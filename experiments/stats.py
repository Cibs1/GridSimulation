"""Statistical analysis of experiment results (ODD section 8).

All functions take the per-run results table written by run_experiments.py
(one row per scenario x seed).

Every scenario runs with the same seeds (common random numbers: same
households, weather year and outages), so results are paired by seed: each
seed is a block measured under every scenario. Comparisons therefore use
tests for repeated measures (Friedman, repeated-measures ANOVA, paired t and
Wilcoxon signed-rank with Holm's correction), not tests for independent groups.
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


def holm(pvalues):
    """Holm-Bonferroni adjusted p-values (NaN entries are left out and kept as NaN)."""
    p = np.asarray(pvalues, dtype=float)
    out = np.full_like(p, np.nan)
    ok = np.flatnonzero(~np.isnan(p))
    order = ok[np.argsort(p[ok])]
    m = len(order)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        out[idx] = min(1.0, running)
    return out


def identical(d, scale):
    """True if paired differences are zero up to float noise (equal by construction, nothing to test)."""
    d = np.asarray(d, dtype=float)
    return len(d) == 0 or np.abs(d).max() <= 1e-9 * max(1.0, abs(scale))


def compare(df, kpi, by="scenario", scenarios=None, seed="seed"):
    """Compare a KPI across scenarios measured on the same seeds (repeated measures).

    Returns (tests, pairs):
    - tests: one row with the Friedman test and Kendall's W (rank-based, the
      main test), the repeated-measures ANOVA with its Greenhouse-Geisser
      correction and partial eta squared, and the smallest Shapiro-Wilk p of
      the ANOVA residuals. If all scenarios give the same value for every seed
      (equal by construction), `identical` is True and no test is run.
    - pairs: every pair of scenarios with the mean paired difference a - b,
      its 95% CI, the difference as % of b's mean, and the paired t and
      Wilcoxon signed-rank p-values, raw and Holm-adjusted over the pairs.
    """
    names = scenarios or list(df[by].drop_duplicates())
    wide = (df[df[by].isin(names)].pivot(index=seed, columns=by, values=kpi)[names].dropna())
    x = wide.to_numpy(dtype=float)
    n, k = x.shape
    grand = x.mean() if x.size else np.nan
    same = all(identical(x[:, a] - x[:, b], grand) for a in range(k) for b in range(a + 1, k))

    tests = {"kpi": kpi, "n_seeds": n, "n_scenarios": k, "identical": same,
             "friedman_chi2": np.nan, "friedman_p": np.nan, "kendall_w": np.nan,
             "rm_anova_F": np.nan, "rm_anova_p": np.nan, "gg_epsilon": np.nan, "rm_anova_p_gg": np.nan,
             "partial_eta2": np.nan, "min_shapiro_p": np.nan}
    if not same and n > 1 and k > 1:
        if k >= 3:
            chi2, p = stats.friedmanchisquare(*x.T)
            tests.update(friedman_chi2=chi2, friedman_p=p, kendall_w=chi2 / (n * (k - 1)))
        # Repeated-measures ANOVA: scenario effect, seeds as blocks
        ss_scen = n * ((x.mean(axis=0) - grand) ** 2).sum()
        ss_seed = k * ((x.mean(axis=1) - grand) ** 2).sum()
        ss_err = ((x - grand) ** 2).sum() - ss_scen - ss_seed
        df1, df2 = k - 1, (k - 1) * (n - 1)
        if ss_err > 0:
            f = (ss_scen / df1) / (ss_err / df2)
            # Greenhouse-Geisser epsilon from the double-centred covariance of the scenarios
            c = np.eye(k) - 1 / k
            sc = c @ np.cov(x, rowvar=False) @ c
            eps = min(1.0, np.trace(sc) ** 2 / (df1 * (sc ** 2).sum())) if k > 2 else 1.0
            resid = x - x.mean(axis=0) - x.mean(axis=1, keepdims=True) + grand
            tests.update(rm_anova_F=f, rm_anova_p=stats.f.sf(f, df1, df2), gg_epsilon=eps,
                         rm_anova_p_gg=stats.f.sf(f, eps * df1, eps * df2),
                         partial_eta2=ss_scen / (ss_scen + ss_err),
                         min_shapiro_p=stats.shapiro(resid.ravel()).pvalue if np.ptp(resid) > 0 else np.nan)

    pairs = [paired(df, kpi, names[a], names[b], by=by, seed=seed) for a in range(k) for b in range(a + 1, k)]
    pairs = pd.DataFrame(pairs)
    if len(pairs):
        pairs["p_holm_t"] = holm(pairs["p_paired_t"])
        pairs["p_holm_wilcoxon"] = holm(pairs["p_wilcoxon"])
    return pd.DataFrame([tests]).set_index("kpi"), pairs


def paired(df, kpi, a, b, by="scenario", seed="seed"):
    """Paired comparison of scenario a vs b on the same seeds (common random numbers).

    Returns the mean difference a - b with its 95% CI and as % of b's mean,
    and the paired t-test and Wilcoxon signed-rank test p-values. When the
    differences are zero up to float noise (equal by construction) the
    p-values are NaN and `identical` is True.
    """
    x = df[df[by] == a].set_index(seed)[kpi]
    y = df[df[by] == b].set_index(seed)[kpi]
    d = (x - y).dropna()
    mean, half = ci95(d)
    base = y[d.index].mean()
    same = identical(d, base)
    return pd.Series({
        "a": a, "b": b, "kpi": kpi, "mean_diff": mean, "ci_low": mean - half, "ci_high": mean + half,
        "diff_pct": 100 * mean / abs(base) if base else np.nan, "identical": same,
        "p_paired_t": np.nan if same else stats.ttest_rel(x[d.index], y[d.index]).pvalue,
        "p_wilcoxon": np.nan if same else stats.wilcoxon(d).pvalue,
    })


# ---- compact tables for the notebook and slides ---------------------------------


def fmt_p(p):
    """p-value as text: '< 0.001' below 0.001, three decimals otherwise, '–' if not tested."""
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "–"
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def _num(v):
    """Three significant figures, whole numbers from 1,000 up."""
    if v is None or np.isnan(v):
        return "–"
    if abs(v) < 1e-9:
        return "0"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    return f"{v:.{max(0, 2 - int(np.floor(np.log10(abs(v)))))}f}"


def brief(table):
    """Short version of a results table, keeping only what a reader needs.

    - compare() tests: Friedman p and Kendall's W (0 = no effect, 1 = the
      scenarios always rank in the same order); scenarios equal by
      construction are labelled instead of tested.
    - pairs (from compare() or a list of paired() rows): difference a - b with
      its 95% CI and as a percentage, and one p-value: Wilcoxon signed-rank,
      Holm-adjusted over the rows of the table (computed here if missing).
    - any other table: p-value columns formatted, numbers rounded.
    The full tables (repeated-measures ANOVA, paired t, raw p-values) stay
    available from compare() and paired().
    """
    t = table.copy()
    if {"friedman_p", "kendall_w", "identical"} <= set(t.columns):
        out = pd.DataFrame(index=t.index)
        same = t["identical"].astype(bool)
        out["Friedman p"] = [("identical by construction" if s else fmt_p(p)) for s, p in zip(same, t["friedman_p"])]
        out["Kendall's W"] = [("–" if s or np.isnan(w) else f"{w:.2f}") for s, w in zip(same, t["kendall_w"])]
        return out
    if {"a", "b", "mean_diff"} <= set(t.columns):
        t = t.reset_index(drop=True)
        p = t["p_holm_wilcoxon"] if "p_holm_wilcoxon" in t else pd.Series(holm(t["p_wilcoxon"]))
        same = t["identical"].astype(bool) if "identical" in t else pd.Series(False, index=t.index)
        out = pd.DataFrame({"a": t["a"], "b": t["b"]})
        if "kpi" in t and t["kpi"].nunique() > 1:
            out["kpi"] = t["kpi"]
        out["difference (a − b)"] = t["mean_diff"].map(_num)
        out["95% CI"] = [f"[{_num(lo)}, {_num(hi)}]" for lo, hi in zip(t["ci_low"], t["ci_high"])]
        if "diff_pct" in t:
            out["difference %"] = t["diff_pct"].map(lambda v: "–" if np.isnan(v) else "0.0%" if abs(v) < 0.05 else f"{v:+.1f}%")
        out["p (Wilcoxon, Holm)"] = [("identical" if s else fmt_p(q)) for s, q in zip(same, p)]
        return out
    for c in t.columns:
        if c.startswith("p_") or c.endswith("_p"):
            t[c] = t[c].map(fmt_p)
        elif pd.api.types.is_float_dtype(t[c]):
            t[c] = t[c].map(_num)
    return t
