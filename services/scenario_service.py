from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class ScenarioData:
    alternative_ids: List[str]
    alternative_names: List[str]
    criterion_ids: List[str]
    criterion_names: List[str]
    directions: List[str]            # benefit/cost aligned with criterion order
    matrix: np.ndarray               # shape (m, n)
    weights: np.ndarray              # shape (n,)
    weight_by_criterion: Dict[str, float]


class ScenarioService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def load(self, scenario_id: str, preference_set_id: str) -> ScenarioData:
        with self.engine.begin() as conn:
            alts = conn.execute(
                text("""
                    SELECT alternative_id::text AS alternative_id, name
                    FROM alternatives
                    WHERE scenario_id = :sid
                    ORDER BY name
                """),
                {"sid": scenario_id},
            ).mappings().all()

            crits = conn.execute(
                text("""
                    SELECT criterion_id::text AS criterion_id, name, direction
                    FROM criteria
                    WHERE scenario_id = :sid
                    ORDER BY name
                """),
                {"sid": scenario_id},
            ).mappings().all()

            if not alts or not crits:
                raise ValueError("Need at least 1 alternative and 1 criterion.")

            measurements = conn.execute(
                text("""
                    SELECT alternative_id::text AS alternative_id,
                           criterion_id::text AS criterion_id,
                           value_num
                    FROM measurements
                    WHERE scenario_id = :sid
                """),
                {"sid": scenario_id},
            ).mappings().all()

            weights_rows = conn.execute(
                text("""
                    SELECT criterion_id::text AS criterion_id, weight
                    FROM criterion_weights
                    WHERE preference_set_id = :pid
                """),
                {"pid": preference_set_id},
            ).mappings().all()

        alt_ids = [a["alternative_id"] for a in alts]
        alt_names = [a["name"] for a in alts]
        crit_ids = [c["criterion_id"] for c in crits]
        crit_names = [c["name"] for c in crits]
        directions = [c["direction"] for c in crits]

        alt_index = {aid: i for i, aid in enumerate(alt_ids)}
        crit_index = {cid: j for j, cid in enumerate(crit_ids)}

        m = len(alt_ids)
        n = len(crit_ids)

        X = np.full((m, n), np.nan, dtype=float)
        for r in measurements:
            i = alt_index.get(r["alternative_id"])
            j = crit_index.get(r["criterion_id"])
            if i is None or j is None:
                continue
            X[i, j] = float(r["value_num"])

        weight_by_crit_id = {r["criterion_id"]: float(r["weight"]) for r in weights_rows}
        w = np.array([weight_by_crit_id.get(cid, 0.0) for cid in crit_ids], dtype=float)

        return ScenarioData(
            alternative_ids=alt_ids,
            alternative_names=alt_names,
            criterion_ids=crit_ids,
            criterion_names=crit_names,
            directions=directions,
            matrix=X,
            weights=w,
            weight_by_criterion={crit_names[i]: float(w[i]) for i in range(n)},
        )

    def validate(self, data: ScenarioData) -> Tuple[bool, List[str]]:
        issues: List[str] = []

        if np.isnan(data.matrix).any():
            missing = int(np.isnan(data.matrix).sum())
            issues.append(f"Matrix has {missing} missing cell(s). Fill all values in Step 2.")

        if (data.weights < 0).any():
            issues.append("Weights contain negative values. Only non-negative weights allowed.")

        s = float(data.weights.sum())
        if s <= 0:
            issues.append("Weights sum to 0. Provide positive weights in Step 2.")

        return (len(issues) == 0), issues
