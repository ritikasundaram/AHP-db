# persistence/repositories/scenario_repo.py
from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


class ScenarioRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def create_scenario(self, decision_id: str, name: str, description: str = "", created_by: str = "") -> str:
        sql = """
        INSERT INTO scenarios (decision_id, name, description, created_by)
        VALUES (:decision_id, :name, :description, :created_by)
        RETURNING scenario_id::text AS scenario_id
        """
        with self.engine.begin() as conn:
            row = conn.execute(
                text(sql),
                {
                    "decision_id": decision_id,
                    "name": name,
                    "description": description,
                    "created_by": created_by,
                },
            ).mappings().first()
        return str(row["scenario_id"])

    def list_scenarios(self, decision_id: str, limit: int = 100) -> list[Dict[str, Any]]:
        sql = """
        SELECT scenario_id::text AS scenario_id, decision_id::text AS decision_id, name, description, created_at, created_by
        FROM scenarios
        WHERE decision_id = :decision_id
        ORDER BY created_at DESC
        LIMIT :limit
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"decision_id": decision_id, "limit": limit}).mappings().all()
        return [dict(r) for r in rows]

    def get_scenario(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        sql = """
        SELECT scenario_id::text AS scenario_id, decision_id::text AS decision_id, name, description, created_at, created_by
        FROM scenarios
        WHERE scenario_id = :scenario_id
        """
        with self.engine.begin() as conn:
            row = conn.execute(text(sql), {"scenario_id": scenario_id}).mappings().first()
        return dict(row) if row else None
