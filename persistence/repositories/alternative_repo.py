# persistence/repositories/alternative_repo.py
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


class AlternativeRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def list_by_scenario(self, scenario_id: str) -> List[dict]:
        sql = """
        SELECT alternative_id::text AS alternative_id, name, description, created_at
        FROM alternatives
        WHERE scenario_id = :scenario_id
        ORDER BY name
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"scenario_id": scenario_id}).mappings().all()
        return [dict(r) for r in rows]

    def upsert_by_names(self, scenario_id: str, names: List[str]) -> Dict[str, str]:
        """
        Ensures alternatives exist for given names. Returns mapping name -> alternative_id.
        """
        names = [n.strip() for n in names if n and n.strip()]
        if not names:
            return {}

        existing = self.list_by_scenario(scenario_id)
        name_to_id = {r["name"]: r["alternative_id"] for r in existing}

        insert_sql = """
        INSERT INTO alternatives (scenario_id, name)
        VALUES (:scenario_id, :name)
        RETURNING alternative_id::text AS alternative_id
        """
        with self.engine.begin() as conn:
            for name in names:
                if name in name_to_id:
                    continue
                row = conn.execute(text(insert_sql), {"scenario_id": scenario_id, "name": name}).mappings().first()
                name_to_id[name] = str(row["alternative_id"])

        return name_to_id

    def delete_missing(self, scenario_id: str, keep_names: List[str]) -> None:
        keep_names = [n.strip() for n in keep_names if n and n.strip()]
        sql = """
        DELETE FROM alternatives
        WHERE scenario_id = :scenario_id
          AND name <> ALL(:keep_names)
        """
        with self.engine.begin() as conn:
            conn.execute(text(sql), {"scenario_id": scenario_id, "keep_names": keep_names})
