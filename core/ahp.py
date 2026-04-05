# core/ahp.py
"""
Pure AHP (Analytic Hierarchy Process) engine.
Implements Saaty's eigenvector method with consistency checking.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

# Saaty's Random Consistency Index table
RI_TABLE: Dict[int, float] = {
    1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12,
    6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49,
}

SAATY_LABELS: Dict[int, str] = {
    1: "Equal importance",
    2: "Weak",
    3: "Moderate importance",
    4: "Moderate plus",
    5: "Strong importance",
    6: "Strong plus",
    7: "Very strong importance",
    8: "Very, very strong",
    9: "Extreme importance",
}


@dataclass(frozen=True)
class AHPResult:
    priority_vector: np.ndarray   # normalised eigenvector (priority weights)
    lambda_max: float             # principal eigenvalue
    ci: float                     # consistency index
    cr: float                     # consistency ratio
    normalized_matrix: np.ndarray # column-normalised matrix


@dataclass(frozen=True)
class AHPArtifacts:
    """Full AHP computation output for a run."""
    # Criteria level
    crit_result: AHPResult
    crit_names: List[str]

    # Alternative level (one AHPResult per criterion, keyed by criterion name)
    alt_results: Dict[str, AHPResult]   # crit_name -> AHPResult over alternatives
    alt_names: List[str]

    # Final composite scores
    final_scores: np.ndarray             # shape (m,)  — one score per alternative


def _build_matrix_from_upper(upper: List[float], n: int) -> np.ndarray:
    """Construct full pairwise matrix from upper-triangle values."""
    m = np.ones((n, n), dtype=float)
    idx = 0
    for i in range(n):
        for j in range(i + 1, n):
            v = float(upper[idx])
            m[i, j] = v
            m[j, i] = 1.0 / v
            idx += 1
    return m


def compute_priority(matrix: np.ndarray) -> AHPResult:
    """
    Compute AHP priorities using the arithmetic mean of columns method
    (equivalent to approximate eigenvector).

    matrix: square positive reciprocal matrix, shape (n, n)
    """
    n = matrix.shape[0]
    if n == 1:
        return AHPResult(
            priority_vector=np.array([1.0]),
            lambda_max=1.0,
            ci=0.0,
            cr=0.0,
            normalized_matrix=np.array([[1.0]]),
        )

    col_sums = matrix.sum(axis=0)
    col_sums = np.where(col_sums == 0, 1.0, col_sums)
    norm = matrix / col_sums
    pv = norm.mean(axis=1)

    # Consistency
    weighted = matrix @ pv
    lambdas = weighted / np.where(pv == 0, 1e-12, pv)
    lmax = float(lambdas.mean())
    ci = (lmax - n) / (n - 1) if n > 1 else 0.0
    ri = RI_TABLE.get(n, 1.49)
    cr = ci / ri if ri > 0 else 0.0

    return AHPResult(
        priority_vector=pv,
        lambda_max=lmax,
        ci=ci,
        cr=cr,
        normalized_matrix=norm,
    )


def matrix_from_upper(upper: List[float], n: int) -> np.ndarray:
    """Public helper: build full matrix from upper-triangle list."""
    return _build_matrix_from_upper(upper, n)


def upper_size(n: int) -> int:
    """Number of unique upper-triangle pairs for an n×n matrix."""
    return n * (n - 1) // 2


def run_full_ahp(
    crit_upper: List[float],
    crit_names: List[str],
    alt_upper_by_crit: Dict[str, List[float]],
    alt_names: List[str],
) -> AHPArtifacts:
    """
    Full AHP (criteria + alternatives pairwise).

    crit_upper           : upper-triangle values for criteria pairwise matrix
    crit_names           : ordered list of criterion names
    alt_upper_by_crit    : {crit_name: upper-triangle values for alternatives}
    alt_names            : ordered list of alternative names
    """
    nc = len(crit_names)
    na = len(alt_names)

    crit_mat = _build_matrix_from_upper(crit_upper, nc)
    crit_res = compute_priority(crit_mat)

    alt_results: Dict[str, AHPResult] = {}
    alt_score_matrix = np.zeros((na, nc))

    for j, cname in enumerate(crit_names):
        upper = alt_upper_by_crit.get(cname, [1.0] * upper_size(na))
        if len(upper) != upper_size(na):
            upper = [1.0] * upper_size(na)
        amat = _build_matrix_from_upper(upper, na)
        ares = compute_priority(amat)
        alt_results[cname] = ares
        alt_score_matrix[:, j] = ares.priority_vector

    final_scores = alt_score_matrix @ crit_res.priority_vector

    return AHPArtifacts(
        crit_result=crit_res,
        crit_names=crit_names,
        alt_results=alt_results,
        alt_names=alt_names,
        final_scores=final_scores,
    )


def run_hybrid_ahp(
    crit_upper: List[float],
    crit_names: List[str],
    performance_matrix: np.ndarray,
    alt_names: List[str],
    directions: List[str],
) -> AHPArtifacts:
    """
    Hybrid AHP: AHP-derived criteria weights × normalised performance matrix.
    This is used when numeric performance data is available instead of
    alternative-level pairwise judgements.

    performance_matrix: shape (m, n), m = alternatives, n = criteria
    directions        : list of 'benefit' or 'cost', length n
    """
    nc = len(crit_names)
    na = len(alt_names)

    crit_mat = _build_matrix_from_upper(crit_upper, nc)
    crit_res = compute_priority(crit_mat)

    # Normalise performance matrix per criterion (vector normalisation)
    norm_mat = np.zeros_like(performance_matrix, dtype=float)
    for j in range(nc):
        col = performance_matrix[:, j].astype(float)
        if directions[j] == "cost":
            col = np.where(col == 0, 1e-12, 1.0 / col)
        denom = np.sqrt((col ** 2).sum())
        norm_mat[:, j] = col / denom if denom > 0 else col

    # Build synthetic AHPResult per criterion from normalised column
    alt_results: Dict[str, AHPResult] = {}
    alt_score_matrix = np.zeros((na, nc))

    for j, cname in enumerate(crit_names):
        col = norm_mat[:, j]
        s = col.sum()
        pv = col / s if s > 0 else np.ones(na) / na
        alt_results[cname] = AHPResult(
            priority_vector=pv,
            lambda_max=float(na),
            ci=0.0,
            cr=0.0,
            normalized_matrix=norm_mat,
        )
        alt_score_matrix[:, j] = pv

    final_scores = alt_score_matrix @ crit_res.priority_vector

    return AHPArtifacts(
        crit_result=crit_res,
        crit_names=crit_names,
        alt_results=alt_results,
        alt_names=alt_names,
        final_scores=final_scores,
    )
