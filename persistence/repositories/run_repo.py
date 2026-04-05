from typing import Optional, Dict, Any, List
from sqlalchemy import text
from sqlalchemy.engine import Engine


class RunRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create_run(self, scenario_id: str, preference_set_id: str, method: str, executed_by: str = "", engine_version: str = "core=0.1.0") -> str:
        sql = """
        INSERT INTO runs (scenario_id, preference_set_id, method, engine_version, executed_by)
        VALUES (:scenario_id, :preference_set_id, :method, :engine_version, :executed_by)
        RETURNING run_id::text AS run_id
        """
        with self.engine.begin() as conn:
            row = conn.execute(
                text(sql),
                {
                    "scenario_id": scenario_id,
                    "preference_set_id": preference_set_id,
                    "method": method,
                    "engine_version": engine_version,
                    "executed_by": executed_by,
                },
            ).mappings().first()
        return str(row["run_id"])

    def list_runs(self, scenario_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        sql = """
        SELECT run_id::text AS run_id, scenario_id::text AS scenario_id,
               preference_set_id::text AS preference_set_id, method, engine_version,
               executed_at, executed_by
        FROM runs
        WHERE scenario_id = :scenario_id
        ORDER BY executed_at DESC
        LIMIT :limit
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"scenario_id": scenario_id, "limit": limit}).mappings().all()
        return [dict(r) for r in rows]
