# services/topsis_service.py
"""
TOPSIS Service — orchestrates TOPSIS computation and persistence.
Mirrors the AHPService pattern for consistency.
"""

from sqlalchemy.engine import Engine

from core.topsis import compute_topsis
from persistence.repositories.topsis_repo import TopsisRepo
from persistence.repositories.result_repo import ResultRepo
from persistence.repositories.run_repo import RunRepo
from services.scenario_service import ScenarioData


class TopsisService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.run_repo = RunRepo(engine)
        self.result_repo = ResultRepo(engine)
        self.topsis_repo = TopsisRepo(engine)

    def run_and_persist(
        self,
        scenario_id: str,
        preference_set_id: str,
        executed_by: str,
        data: ScenarioData,
    ) -> str:
        """
        Runs TOPSIS, persists all artifacts, and returns the run_id.
        """
        m = len(data.alternative_ids)
        n = len(data.criterion_ids)

        # Normalise weights to sum to 1
        w = data.weights.copy()
        s = float(w.sum())
        if s > 0:
            w = w / s

        artifacts = compute_topsis(
            matrix=data.matrix.astype(float),
            weights=w,
            directions=data.directions,
        )

        # ── Persist run ──────────────────────────────────────────────────────
        run_id = self.run_repo.create_run(
            scenario_id=scenario_id,
            preference_set_id=preference_set_id,
            method="topsis",
            executed_by=executed_by,
        )

        # Run config
        self.topsis_repo.save_run_config(run_id)

        # Normalized values
        norm_rows = [
            {
                "run_id": run_id,
                "alternative_id": data.alternative_ids[i],
                "criterion_id": data.criterion_ids[j],
                "value": float(artifacts.normalized_matrix[i, j]),
            }
            for i in range(m)
            for j in range(n)
        ]
        self.topsis_repo.replace_normalized(run_id, norm_rows)

        # Weighted values
        weighted_rows = [
            {
                "run_id": run_id,
                "alternative_id": data.alternative_ids[i],
                "criterion_id": data.criterion_ids[j],
                "value": float(artifacts.weighted_matrix[i, j]),
            }
            for i in range(m)
            for j in range(n)
        ]
        self.topsis_repo.replace_weighted(run_id, weighted_rows)

        # Ideals (PIS / NIS)
        ideal_rows = [
            {
                "run_id": run_id,
                "criterion_id": data.criterion_ids[j],
                "pos_ideal": float(artifacts.pis[j]),
                "neg_ideal": float(artifacts.nis[j]),
            }
            for j in range(n)
        ]
        self.topsis_repo.replace_ideals(run_id, ideal_rows)

        # Distances
        dist_rows = [
            {
                "run_id": run_id,
                "alternative_id": data.alternative_ids[i],
                "s_pos": float(artifacts.s_pos[i]),
                "s_neg": float(artifacts.s_neg[i]),
                "c_star": float(artifacts.c_star[i]),
            }
            for i in range(m)
        ]
        self.topsis_repo.replace_distances(run_id, dist_rows)

        # Final scores → result_scores table (shared with AHP)
        alt_id_to_score = {
            data.alternative_ids[i]: float(artifacts.c_star[i])
            for i in range(m)
        }
        self.result_repo.replace_scores(run_id, alt_id_to_score)

        return run_id
