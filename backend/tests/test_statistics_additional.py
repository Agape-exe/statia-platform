import base64
import math

import pytest
from scipy import stats
from test_statistics import job_for

from app.services.statistics.engine import calculate


def ranked_job(method, groups):
    lines = ["cantidad,estrato"]
    for name, values in groups.items():
        lines.extend(f"{value},{name}" for value in values)
    return job_for(("\n".join(lines) + "\n").encode(), "group_comparison", [method])


def test_mann_whitney_analytical_without_ties():
    result, _ = calculate(ranked_job("mann_whitney", {"A": [1, 2, 3], "B": [4, 5, 6]}))
    computed = result["components"][0]["statistics"]
    assert result["status"] == "completed"
    assert computed["U"] == 0
    assert computed["rank_biserial"] == -1
    # Normal asintótica con continuidad; U=0, E(U)=4.5, Var(U)=5.25.
    expected = math.erfc((4.5 - 0.5) / math.sqrt(5.25) / math.sqrt(2))
    assert computed["p"] == pytest.approx(expected, rel=1e-12)


def test_kruskal_analytical():
    result, _ = calculate(ranked_job("kruskal", {"A": [1, 2, 3], "B": [4, 5, 6], "C": [7, 8, 9]}))
    computed = result["components"][0]["statistics"]
    assert computed["H"] == pytest.approx(7.2, abs=1e-12)
    assert computed["df"] == 2
    assert computed["p"] == pytest.approx(math.exp(-3.6), rel=1e-12)
    assert computed["effect_global"] is None


def association_job(method, counts):
    lines = ["cantidad,otra"]
    for i, row in enumerate(counts):
        for j, count in enumerate(row):
            lines.extend([f"fila{i},col{j}"] * count)
    job = job_for(("\n".join(lines) + "\n").encode(), "inferential", [method])
    # El helper de correlación conserva dos medidas con nombres arbitrarios.
    job["plan"]["variables"] = [
        job["plan"]["variables"][0],
        {"file_id": job["files"][0]["id"], "sheet": "tabla", "column": "otra", "role": "predictor"},
    ]
    job["specification"]["decisions"] = [
        {"variable": v, "statistical_type": "nominal"} for v in job["plan"]["variables"]
    ]
    return job


def test_chi_square_and_cramers_v_analytic():
    result, _ = calculate(association_job("chi_square", [[10, 20], [30, 40]]))
    computed = result["components"][0]["statistics"]
    assert computed["chi2"] == pytest.approx(50 / 63, rel=1e-12)
    assert computed["df"] == 1
    assert computed["cramers_v"] == pytest.approx(math.sqrt(1 / 126), rel=1e-12)
    assert computed["p"] == pytest.approx(math.erfc(math.sqrt(25 / 63)), rel=1e-12)
    assert computed["expected_min"] == 12


def test_fisher_against_hypergeometric_enumeration_and_small_expected_warning():
    job = association_job("fisher_exact", [[1, 9], [11, 3]])
    result, _ = calculate(job)
    computed = result["components"][0]["statistics"]
    probabilities = [math.comb(12, k) * math.comb(12, 10 - k) / math.comb(24, 10) for k in range(11)]
    exact_p = sum(p for p in probabilities if p <= probabilities[1] + 1e-15)
    assert computed["p"] == pytest.approx(exact_p, rel=1e-12)
    assert computed["odds_ratio"] == pytest.approx(1 / 33, rel=1e-12)
    warned, _ = calculate(association_job("chi_square", [[1, 1], [1, 2]]))
    assert any(a["status"] == "violated" for a in warned["components"][0]["assumptions"])
    assert any("Fisher" in warning for warning in warned["components"][0]["warnings"])


def paired_job(method, a, b, ids=None):
    ids = ids or list(range(len(a)))
    data = ("u,v,par\n" + "\n".join(f"{x},{y},{i}" for x, y, i in zip(a, b, ids)) + "\n").encode()
    job = job_for(data, "paired_comparison", [method])
    fid = job["files"][0]["id"]
    variables = [
        {"file_id": fid, "sheet": "tabla", "column": c, "role": role}
        for c, role in [("u", "outcome"), ("v", "outcome"), ("par", "pair_id")]
    ]
    job["plan"]["variables"] = variables
    job["specification"]["decisions"] = [
        {"variable": v, "statistical_type": "identifier" if v["role"] == "pair_id" else "continuous"} for v in variables
    ]
    job["specification"]["components"][0]["design"] = "paired"
    return job


def test_paired_t_analytic_and_reference_ci():
    a, b = [1, 3, 6, 8, 10], [0, 1, 2, 4, 5]
    result, _ = calculate(paired_job("paired_t", a, b))
    computed = result["components"][0]["statistics"]
    assert computed["difference"] == pytest.approx(3.2, rel=1e-12)
    assert computed["t"] == pytest.approx(3.2 / math.sqrt(2.7 / 5), rel=1e-12)
    assert computed["df"] == 4
    assert computed["cohen_dz"] == pytest.approx(3.2 / math.sqrt(2.7), rel=1e-12)
    expected = stats.ttest_rel(a, b)
    assert computed["p"] == pytest.approx(expected.pvalue, rel=1e-12)
    assert computed["difference_ci"]["low"] == pytest.approx(expected.confidence_interval(0.95).low, rel=1e-12)


def test_pair_id_required_unique_and_complete_pairs_only():
    job = paired_job("paired_t", [1, 3, 6, 8, 10], [0, 1, 2, 4, 5], [1, 1, 2, 3, 4])
    result, _ = calculate(job)
    assert result["status"] == "failed"
    assert "repetido" in result["components"][0]["error"]
    job = paired_job("paired_t", [1, 3, 6, 8, 10], [0, 1, 2, 4, 5])
    data = base64.b64decode(job["files"][0]["data"]).replace(b"3,1,1", b"3,,1")
    job["files"][0]["data"] = base64.b64encode(data).decode()
    result, _ = calculate(job)
    assert result["components"][0]["sample"]["used"] == 4
    assert result["components"][0]["sample"]["excluded_missing"] == 1


def test_wilcoxon_analytical_and_zero_handling():
    differences = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    result, _ = calculate(paired_job("wilcoxon", differences, [0] * 10))
    computed = result["components"][0]["statistics"]
    assert computed["W"] == 0
    # W+=55, media 27.5, var=10*11*21/24; corrección hacia la media de 0.5.
    p = math.erfc((27.5 - 0.5) / math.sqrt(10 * 11 * 21 / 24) / math.sqrt(2))
    assert computed["p"] == pytest.approx(p, rel=1e-12)
    result, _ = calculate(paired_job("wilcoxon", [0] + differences, [0] * 11))
    assert result["components"][0]["statistics"]["zero_differences"] == 1
    assert result["components"][0]["statistics"]["nonzero_pairs"] == 10


def test_posthoc_welch_holm_prespecified_and_individual_ci():
    job = ranked_job("welch_anova", {"A": [1, 2, 3], "B": [2, 4, 6, 8], "C": [3, 6, 9, 12, 15]})
    job["specification"]["components"][0]["posthoc"] = "welch_holm"
    result, _ = calculate(job)
    computed = result["components"][0]["statistics"]
    pairs = computed["posthoc"]
    assert len(pairs) == 3
    assert pairs[0]["p"] == pytest.approx(0.09991286431180087, rel=1e-12)
    for pair in pairs:
        assert pair["p_holm"] >= pair["p"]
        assert pair["hedges_df"] in {5, 6, 7}
    assert "familia" in result["components"][0]["tables"][0]["title"]
