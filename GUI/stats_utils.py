"""
Shared statistical utilities for the SONLab FRET Tool.

Pure NumPy/SciPy helpers (no Qt) for group comparisons on per-cell data:
normality screening, Welch's ANOVA, Holm-Bonferroni correction and an
assumption-aware test picker that returns significance-bar comparisons plus a
human-readable report. Extracted so the FRET and Intensity tabs can share one
implementation.
"""

import warnings

import numpy as np
from scipy import stats
from itertools import combinations


def p_to_symbol(p):
    """Map a p-value to the conventional significance star string."""
    if p is None or not np.isfinite(p):
        return "ns"
    if p < 0.0001:
        return "****"
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def draw_sig(ax, x1, x2, y, text, h):
    """Draw a significance bracket between x1 and x2 at height y with cap height h."""
    ax.plot([x1, x1, x2, x2], [y, y + h, y + h, y], lw=1.0, c=ax.xaxis.label.get_color() or 'k')
    ax.text((x1 + x2) / 2, y + h, text, ha='center', va='bottom',
            color=ax.xaxis.label.get_color() or 'k')


def normality(arr, alpha=0.05):
    """Screen a group for normality with the Shapiro-Wilk test.

    Returns ``(is_normal, p_value, note)``. ``is_normal`` is ``False`` when
    normality cannot be established (n < 3, constant data or test failure) so the
    more conservative non-parametric branch is selected. Samples larger than 5000
    are treated as adequately normal because Shapiro-Wilk becomes unreliable /
    over-sensitive there. ``p_value`` is ``None`` when the test could not be run.
    """
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 3:
        return False, None, "n < 3 (cannot test)"
    if np.ptp(arr) == 0:
        return False, None, "constant values"
    if arr.size > 5000:
        return True, None, "n > 5000 (assumed normal)"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            p = float(stats.shapiro(arr).pvalue)
        if not np.isfinite(p):
            return False, None, "near-constant values"
        return (p > alpha), p, "Shapiro-Wilk"
    except Exception:
        return False, None, "test failed"


def welch_anova(groups):
    """One-way Welch's ANOVA (does not assume equal group variances).

    Implements the standard Welch (1951) formulation and returns ``(F, p)``.
    Groups with fewer than two observations or zero variance are dropped;
    ``(nan, nan)`` is returned when fewer than two usable groups remain.
    """
    arrs = [np.asarray(g, dtype=float) for g in groups]
    arrs = [a[np.isfinite(a)] for a in arrs]
    arrs = [a for a in arrs if a.size >= 2 and np.ptp(a) > 0]
    k = len(arrs)
    if k < 2:
        return float('nan'), float('nan')
    n = np.array([a.size for a in arrs], dtype=float)
    means = np.array([a.mean() for a in arrs])
    variances = np.array([a.var(ddof=1) for a in arrs])
    w = n / variances
    w_sum = w.sum()
    grand = (w * means).sum() / w_sum
    numerator = (w * (means - grand) ** 2).sum() / (k - 1)
    term = (((1.0 - w / w_sum) ** 2) / (n - 1.0)).sum()
    denominator = 1.0 + (2.0 * (k - 2) / (k ** 2 - 1.0)) * term
    f_stat = numerator / denominator
    df2 = (k ** 2 - 1.0) / (3.0 * term)
    p = float(stats.f.sf(f_stat, k - 1, df2))
    return float(f_stat), p


def holm_bonferroni(pvals):
    """Holm-Bonferroni step-down adjusted p-values.

    Controls the family-wise error rate like plain Bonferroni but is uniformly
    more powerful. Returns adjusted p-values in the original order, each capped at
    1.0 and kept monotonic.
    """
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * pvals[idx])
        adjusted[idx] = min(running, 1.0)
    return adjusted


def compute_significance_comparisons(box_data, labels=None, data_note=None):
    """Pick statistically appropriate tests for significance bars.

    Returns ``(comparisons, report)`` where ``comparisons`` is a list of
    ``(i, j, p_adjusted)`` tuples (indices into ``box_data``) and ``report`` is a
    plain-text summary of the data characteristics and the tests performed.

    The test family is chosen from the data rather than assumed:

    * Every group is screened for normality (Shapiro-Wilk).
    * If **all** groups look normal, the parametric family is used: Welch's
      t-test for pairs and, for >2 groups, Welch's ANOVA as the omnibus test.
    * If **any** group departs from normality, the non-parametric family is used:
      Mann-Whitney U for pairs and Kruskal-Wallis as the omnibus test.
    * For >2 groups the omnibus test gates the post-hoc comparisons and the
      pairwise p-values are adjusted with Holm-Bonferroni.
    """
    valid = [(idx, np.asarray(d, dtype=float)[np.isfinite(np.asarray(d, dtype=float))])
             for idx, d in enumerate(box_data) if d is not None and len(d) > 0]
    valid = [(idx, arr) for idx, arr in valid if arr.size > 0]

    def name_of(idx):
        if labels is not None and 0 <= idx < len(labels):
            return str(labels[idx])
        return f"Group {idx + 1}"

    if len(valid) < 2:
        return [], ("Not enough groups with data for statistical testing "
                    "(at least two non-empty groups are required).")

    group_info = []
    all_normal = True
    for idx, arr in valid:
        is_norm, shp_p, note = normality(arr)
        all_normal = all_normal and is_norm
        group_info.append({
            "name": name_of(idx), "n": int(arr.size),
            "mean": float(np.mean(arr)),
            "sd": float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0,
            "median": float(np.median(arr)),
            "q1": float(np.percentile(arr, 25)), "q3": float(np.percentile(arr, 75)),
            "normal": is_norm, "shapiro_p": shp_p, "note": note,
        })
    parametric = all_normal

    levene_p = None
    try:
        if len(valid) >= 2 and all(arr.size >= 2 for _, arr in valid):
            levene_p = float(stats.levene(*[arr for _, arr in valid], center='median').pvalue)
    except Exception:
        levene_p = None

    def pair_p(a, b):
        if a.size < 2 or b.size < 2:
            return float('nan')
        try:
            if parametric:
                return float(stats.ttest_ind(a, b, equal_var=False).pvalue)
            return float(stats.mannwhitneyu(a, b, alternative='two-sided').pvalue)
        except Exception:
            return float('nan')

    pair_test = "Welch's t-test (unequal variance)" if parametric else "Mann-Whitney U"
    comparisons = []
    report_pairs = []
    omnibus_name = None
    omnibus_p = None
    correction = "none (single comparison)"

    if len(valid) == 2:
        (i, a), (j, b) = valid
        p = pair_p(a, b)
        if np.isfinite(p):
            comparisons = [(i, j, min(p, 1.0))]
            report_pairs.append((name_of(i), name_of(j), min(p, 1.0)))
    else:
        correction = "Holm-Bonferroni"
        arrays = [arr for _, arr in valid]
        try:
            if parametric:
                omnibus_name = "Welch's ANOVA"
                _, omnibus_p = welch_anova(arrays)
            else:
                omnibus_name = "Kruskal-Wallis"
                omnibus_p = float(stats.kruskal(*arrays).pvalue)
        except Exception:
            omnibus_p = float('nan')

        if omnibus_p is not None and np.isfinite(omnibus_p) and omnibus_p < 0.05:
            pairs = list(combinations(valid, 2))
            raw = [pair_p(a, b) for (_, a), (_, b) in pairs]
            finite = [(k, p) for k, p in enumerate(raw) if np.isfinite(p)]
            if finite:
                adjusted = holm_bonferroni([p for _, p in finite])
                adj_by_pair = {k: av for (k, _), av in zip(finite, adjusted)}
                for k, ((i, _a), (j, _b)) in enumerate(pairs):
                    if k in adj_by_pair:
                        comparisons.append((i, j, adj_by_pair[k]))
                        report_pairs.append((name_of(i), name_of(j), adj_by_pair[k]))

    report = format_stats_report(
        group_info, parametric, levene_p, pair_test, omnibus_name,
        omnibus_p, correction, report_pairs, data_note=data_note)
    return comparisons, report


def format_stats_report(group_info, parametric, levene_p, pair_test,
                        omnibus_name, omnibus_p, correction, report_pairs,
                        data_note=None):
    """Build the plain-text statistical summary shown in the info dialog."""
    def fmt_p(p):
        if p is None or (isinstance(p, float) and not np.isfinite(p)):
            return "n/a"
        return f"{p:.2e}" if p < 1e-3 else f"{p:.4f}"

    lines = []
    lines.append("STATISTICAL SUMMARY OF THE VISUALIZED DATA")
    lines.append("=" * 50)
    lines.append("")
    if data_note:
        lines.append(data_note)
        lines.append("")
    lines.append("Per-group characteristics")
    lines.append("-" * 50)
    for g in group_info:
        shp = "" if g["shapiro_p"] is None else f", Shapiro p={fmt_p(g['shapiro_p'])}"
        lines.append(f"• {g['name']}")
        lines.append(f"    n = {g['n']}   mean = {g['mean']:.3g}   SD = {g['sd']:.3g}")
        lines.append(f"    median = {g['median']:.3g}   IQR = [{g['q1']:.3g}, {g['q3']:.3g}]")
        lines.append(f"    normal: {'yes' if g['normal'] else 'no'} ({g['note']}{shp})")
    lines.append("")
    lines.append("Assumption checks")
    lines.append("-" * 50)
    lines.append(f"• Normality (Shapiro-Wilk, α=0.05): "
                 f"{'all groups normal' if parametric else 'at least one group non-normal'}")
    if levene_p is not None:
        eq = "equal" if levene_p > 0.05 else "unequal"
        lines.append(f"• Equal variances (Levene, median-centered): "
                     f"p={fmt_p(levene_p)} → variances likely {eq}")
    else:
        lines.append("• Equal variances (Levene): not available")
    lines.append("")
    lines.append("Tests performed")
    lines.append("-" * 50)
    if parametric:
        lines.append("• Family: parametric (data consistent with normality)")
    else:
        lines.append("• Family: non-parametric (rank-based; robust to non-normality)")
    lines.append(f"• Pairwise test: {pair_test}")
    if omnibus_name is not None:
        lines.append(f"• Omnibus test: {omnibus_name}, p={fmt_p(omnibus_p)}"
                     + ("  → significant; post-hoc reported"
                        if (omnibus_p is not None and np.isfinite(omnibus_p) and omnibus_p < 0.05)
                        else "  → not significant; post-hoc suppressed"))
    lines.append(f"• Multiple-comparison correction: {correction}")
    lines.append("")
    lines.append("Pairwise results")
    lines.append("-" * 50)
    if report_pairs:
        for a, b, p in report_pairs:
            lines.append(f"• {a} vs {b}: p={fmt_p(p)} {p_to_symbol(p)}")
    else:
        lines.append("• No pairwise comparisons reported "
                     "(single group, or omnibus test not significant).")
    lines.append("")
    lines.append("Significance symbols: **** p<1e-4, *** p<1e-3, ** p<0.01, * p<0.05, ns = not significant")
    return "\n".join(lines)
