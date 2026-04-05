# persistence/repositories/ahp_repo.py
"""
Repository for all AHP-specific persistence operations.
Works with the ahp_* tables added via schema_ahp.sql.
"""

from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


class AHPRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    # ── Criteria judgments ────────────────────────────────────────────────────

    def save_criteria_judgments(
        self,
        preference_set_id: str,
        rows: List[Dict],  # [{criterion_i_id, criterion_j_id, judgment}]
    ) -> None:
        del_sql = "DELETE FROM ahp_criteria_judgments WHERE preference_set_id = :pref_id"
        ins_sql = """
        INSERT INTO ahp_criteria_judgments
               (preference_set_id, criterion_i_id, criterion_j_id, judgment)
        VALUES (:pref_id, :criterion_i_id, :criterion_j_id, :judgment)
        ON CONFLICT (preference_set_id, criterion_i_id, criterion_j_id)
           DO UPDATE SET judgment = EXCLUDED.judgment
        """
        payloads = [
            {
                "pref_id": preference_set_id,
                "criterion_i_id": r["criterion_i_id"],
                "criterion_j_id": r["criterion_j_id"],
                "judgment": float(r["judgment"]),
            }
            for r in rows
        ]
        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"pref_id": preference_set_id})
            if payloads:
                conn.execute(text(ins_sql), payloads)

    def load_criteria_judgments(self, preference_set_id: str) -> List[Dict]:
        sql = """
        SELECT criterion_i_id::text AS criterion_i_id,
               criterion_j_id::text AS criterion_j_id,
               judgment
        FROM ahp_criteria_judgments
        WHERE preference_set_id = :pref_id
        ORDER BY criterion_i_id, criterion_j_id
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"pref_id": preference_set_id}).mappings().all()
        return [dict(r) for r in rows]

    # ── Alternative judgments ─────────────────────────────────────────────────

    def save_alternative_judgments(
        self,
        preference_set_id: str,
        rows: List[Dict],  # [{criterion_id, alternative_i_id, alternative_j_id, judgment}]
    ) -> None:
        del_sql = """
        DELETE FROM ahp_alternative_judgments
        WHERE preference_set_id = :pref_id
        """
        ins_sql = """
        INSERT INTO ahp_alternative_judgments
               (preference_set_id, criterion_id, alternative_i_id, alternative_j_id, judgment)
        VALUES (:pref_id, :criterion_id, :alternative_i_id, :alternative_j_id, :judgment)
        ON CONFLICT (preference_set_id, criterion_id, alternative_i_id, alternative_j_id)
           DO UPDATE SET judgment = EXCLUDED.judgment
        """
        payloads = [
            {
                "pref_id": preference_set_id,
                "criterion_id": r["criterion_id"],
                "alternative_i_id": r["alternative_i_id"],
                "alternative_j_id": r["alternative_j_id"],
                "judgment": float(r["judgment"]),
            }
            for r in rows
        ]
        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"pref_id": preference_set_id})
            if payloads:
                conn.execute(text(ins_sql), payloads)

    def load_alternative_judgments(self, preference_set_id: str, criterion_id: str) -> List[Dict]:
        sql = """
        SELECT alternative_i_id::text AS alternative_i_id,
               alternative_j_id::text AS alternative_j_id,
               judgment
        FROM ahp_alternative_judgments
        WHERE preference_set_id = :pref_id AND criterion_id = :crit_id
        ORDER BY alternative_i_id, alternative_j_id
        """
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(sql), {"pref_id": preference_set_id, "crit_id": criterion_id}
            ).mappings().all()
        return [dict(r) for r in rows]

    # ── Run artifacts ─────────────────────────────────────────────────────────

    def save_run_artifacts(
        self,
        run_id: str,
        criteria_cr: float,
        lambda_max: float,
        n_criteria: int,
        mode: str,
    ) -> None:
        sql = """
        INSERT INTO ahp_run_artifacts (run_id, criteria_cr, lambda_max, n_criteria, mode)
        VALUES (:run_id, :criteria_cr, :lambda_max, :n_criteria, :mode)
        ON CONFLICT (run_id) DO UPDATE
           SET criteria_cr = EXCLUDED.criteria_cr,
               lambda_max  = EXCLUDED.lambda_max,
               n_criteria  = EXCLUDED.n_criteria,
               mode        = EXCLUDED.mode
        """
        with self.engine.begin() as conn:
            conn.execute(
                text(sql),
                {
                    "run_id": run_id,
                    "criteria_cr": float(criteria_cr),
                    "lambda_max": float(lambda_max),
                    "n_criteria": int(n_criteria),
                    "mode": mode,
                },
            )

    def get_run_artifacts(self, run_id: str) -> Optional[Dict]:
        sql = """
        SELECT run_id::text AS run_id, criteria_cr, lambda_max, n_criteria, mode
        FROM ahp_run_artifacts
        WHERE run_id = :run_id
        """
        with self.engine.begin() as conn:
            row = conn.execute(text(sql), {"run_id": run_id}).mappings().first()
        return dict(row) if row else None

    # ── Criterion priorities ──────────────────────────────────────────────────

    def replace_criterion_priorities(self, run_id: str, rows: List[Dict]) -> None:
        """rows: [{criterion_id, priority}]"""
        del_sql = "DELETE FROM ahp_criterion_priorities WHERE run_id = :run_id"
        ins_sql = """
        INSERT INTO ahp_criterion_priorities (run_id, criterion_id, priority)
        VALUES (:run_id, :criterion_id, :priority)
        """
        payloads = [
            {"run_id": run_id, "criterion_id": r["criterion_id"], "priority": float(r["priority"])}
            for r in rows
        ]
        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"run_id": run_id})
            if payloads:
                conn.execute(text(ins_sql), payloads)

    def get_criterion_priorities(self, run_id: str) -> pd.DataFrame:
        sql = """
        SELECT c.name AS criterion, acp.priority
        FROM ahp_criterion_priorities acp
        JOIN criteria c ON c.criterion_id = acp.criterion_id
        WHERE acp.run_id = :run_id
        ORDER BY acp.priority DESC
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"run_id": run_id}).mappings().all()
        return pd.DataFrame([dict(r) for r in rows])

    # ── Alternative priorities per criterion ──────────────────────────────────

    def replace_alternative_priorities(self, run_id: str, rows: List[Dict]) -> None:
        """rows: [{criterion_id, alternative_id, priority, cr}]"""
        del_sql = "DELETE FROM ahp_alternative_priorities WHERE run_id = :run_id"
        ins_sql = """
        INSERT INTO ahp_alternative_priorities
               (run_id, criterion_id, alternative_id, priority, cr)
        VALUES (:run_id, :criterion_id, :alternative_id, :priority, :cr)
        """
        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"run_id": run_id})
            if rows:
                conn.execute(text(ins_sql), rows)

    def get_alternative_priorities(self, run_id: str) -> pd.DataFrame:
        sql = """
        SELECT c.name AS criterion, a.name AS alternative,
               aap.priority, aap.cr
        FROM ahp_alternative_priorities aap
        JOIN criteria c ON c.criterion_id = aap.criterion_id
        JOIN alternatives a ON a.alternative_id = aap.alternative_id
        WHERE aap.run_id = :run_id
        ORDER BY c.name, aap.priority DESC
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"run_id": run_id}).mappings().all()
        return pd.DataFrame([dict(r) for r in rows])
