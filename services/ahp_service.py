# services/ahp_service.py
"""
AHP Service — orchestrates AHP computation and persistence.
Supports two modes:
  - 'full'   : criteria pairwise + alternative pairwise per criterion
  - 'hybrid' : criteria pairwise + numeric performance matrix (auto-normalised)
"""

from typing import Dict, List

import numpy as np
from sqlalchemy.engine import Engine

from core.ahp import run_full_ahp, run_hybrid_ahp, upper_size
from persistence.repositories.ahp_repo import AHPRepo
from persistence.repositories.result_repo import ResultRepo
from persistence.repositories.run_repo import RunRepo
from services.scenario_service import ScenarioData


class AHPService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.run_repo = RunRepo(engine)
        self.result_repo = ResultRepo(engine)
        self.ahp_repo = AHPRepo(engine)

    def run_and_persist(
        self,
        scenario_id: str,
        preference_set_id: str,
        executed_by: str,
        data: ScenarioData,
        crit_upper: List[float],
        alt_upper_by_crit: Dict[str, List[float]],
        mode: str = "hybrid",  # 'full' or 'hybrid'
    ) -> str:
        """
        Runs AHP, persists all artifacts, and returns the run_id.

        data              : ScenarioData loaded by ScenarioService
        crit_upper        : upper-triangle judgments for criteria pairwise matrix
        alt_upper_by_crit : {crit_name: upper-triangle judgments} — used in 'full' mode
        mode              : 'full' (pairwise alternatives) or 'hybrid' (numeric matrix)
        """
        nc = len(data.criterion_names)
        na = len(data.alternative_names)

        # Pad / trim crit_upper to correct size
        expected_crit = upper_size(nc)
        if len(crit_upper) != expected_crit:
            crit_upper = (list(crit_upper) + [1.0] * expected_crit)[:expected_crit]

        if mode == "full":
            artifacts = run_full_ahp(
                crit_upper=crit_upper,
                crit_names=data.criterion_names,
                alt_upper_by_crit=alt_upper_by_crit,
                alt_names=data.alternative_names,
            )
        else:
            artifacts = run_hybrid_ahp(
                crit_upper=crit_upper,
                crit_names=data.criterion_names,
                performance_matrix=data.matrix.astype(float),
                alt_names=data.alternative_names,
                directions=data.directions,
            )

        # ── Persist run ──────────────────────────────────────────────────────
        run_id = self.run_repo.create_run(
            scenario_id=scenario_id,
            preference_set_id=preference_set_id,
            method="ahp",
            executed_by=executed_by,
        )

        # Run-level artifacts
        self.ahp_repo.save_run_artifacts(
            run_id=run_id,
            criteria_cr=artifacts.crit_result.cr,
            lambda_max=artifacts.crit_result.lambda_max,
            n_criteria=nc,
            mode=mode,
        )

        # Criterion priorities
        crit_prio_rows = [
            {
                "criterion_id": data.criterion_ids[j],
                "priority": float(artifacts.crit_result.priority_vector[j]),
            }
            for j in range(nc)
        ]
        self.ahp_repo.replace_criterion_priorities(run_id, crit_prio_rows)

        # Alternative priorities per criterion
        alt_prio_rows = []
        for j, cname in enumerate(data.criterion_names):
            ares = artifacts.alt_results.get(cname)
            if ares is None:
                continue
            for i in range(na):
                alt_prio_rows.append(
                    {
                        "run_id": run_id,
                        "criterion_id": data.criterion_ids[j],
                        "alternative_id": data.alternative_ids[i],
                        "priority": float(ares.priority_vector[i]),
                        "cr": float(ares.cr),
                    }
                )
        self.ahp_repo.replace_alternative_priorities(run_id, alt_prio_rows)

        # Final composite scores → result_scores table (shared with TOPSIS)
        alt_id_to_score = {
            data.alternative_ids[i]: float(artifacts.final_scores[i])
            for i in range(na)
        }
        self.result_repo.replace_scores(run_id, alt_id_to_score)

        return run_id
