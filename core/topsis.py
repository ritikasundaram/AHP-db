# core/topsis.py
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np


@dataclass(frozen=True)
class TopsisArtifacts:
    normalized_matrix: np.ndarray  # r_ij
    weighted_matrix: np.ndarray    # v_ij
    pis: np.ndarray                # A*
    nis: np.ndarray                # A-
    s_pos: np.ndarray              # S*
    s_neg: np.ndarray              # S-
    c_star: np.ndarray             # C*


def compute_topsis(
    matrix: np.ndarray,
    weights: np.ndarray,
    directions: List[str],
) -> TopsisArtifacts:
    """
    matrix: shape (m, n)
    weights: shape (n,) must sum to 1 (or will behave as weighted scaling)
    directions: list of 'benefit' or 'cost', length n
    """
    if matrix.ndim != 2:
        raise ValueError("matrix must be 2D")
    m, n = matrix.shape
    if weights.shape != (n,):
        raise ValueError("weights must have shape (n,)")
    if len(directions) != n:
        raise ValueError("directions length must match number of criteria")

    denom = np.sqrt((matrix ** 2).sum(axis=0))
    denom = np.where(denom == 0, 1.0, denom)
    r = matrix / denom

    v = r * weights

    pis = np.zeros(n, dtype=float)
    nis = np.zeros(n, dtype=float)
    for j, d in enumerate(directions):
        col = v[:, j]
        if d == "benefit":
            pis[j] = np.max(col)
            nis[j] = np.min(col)
        elif d == "cost":
            pis[j] = np.min(col)
            nis[j] = np.max(col)
        else:
            raise ValueError("direction must be 'benefit' or 'cost'")

    s_pos = np.sqrt(((v - pis) ** 2).sum(axis=1))
    s_neg = np.sqrt(((v - nis) ** 2).sum(axis=1))
    c_star = s_neg / (s_pos + s_neg + 1e-12)

    return TopsisArtifacts(
        normalized_matrix=r,
        weighted_matrix=v,
        pis=pis,
        nis=nis,
        s_pos=s_pos,
        s_neg=s_neg,
        c_star=c_star,
    )
