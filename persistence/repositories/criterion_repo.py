# persistence/repositories/criterion_repo.py
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.engine import Engine


class CriterionRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def list_by_scenario(self, scenario_id: str) -> List[dict]:
        sql = """
        SELECT criterion_id::text AS criterion_id, name, direction, scale_type, unit, description, created_at
        FROM criteria
        WHERE scenario_id = :scenario_id
        ORDER BY name
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"scenario_id": scenario_id}).mappings().all()
        return [dict(r) for r in rows]

    def upsert_rows(self, scenario_id: str, rows: List[dict]) -> Dict[str, str]:
        """
        rows: [{name, direction, scale_type, unit, description}]
        Returns mapping name -> criterion_id
        """
        rows = [r for r in rows if str(r.get("name", "")).strip()]
        existing = self.list_by_scenario(scenario_id)
        name_to_id = {r["name"]: r["criterion_id"] for r in existing}

        insert_sql = """
        INSERT INTO criteria (scenario_id, name, direction, scale_type, unit, description)
        VALUES (:scenario_id, :name, :direction, :scale_type, :unit, :description)
        RETURNING criterion_id::text AS criterion_id
        """
        update_sql = """
        UPDATE criteria
        SET direction = :direction,
            scale_type = :scale_type,
            unit = :unit,
            description = :description
        WHERE scenario_id = :scenario_id AND name = :name
        """

        with self.engine.begin() as conn:
            for r in rows:
                name = str(r["name"]).strip()
                payload = {
                    "scenario_id": scenario_id,
                    "name": name,
                    "direction": str(r.get("direction", "benefit")).strip(),
                    "scale_type": str(r.get("scale_type", "ratio")).strip(),
                    "unit": (str(r.get("unit")).strip() if r.get("unit") is not None else None) or None,
                    "description": (str(r.get("description")).strip() if r.get("description") is not None else None) or None,
                }

                if name not in name_to_id:
                    row_db = conn.execute(text(insert_sql), payload).mappings().first()
                    name_to_id[name] = str(row_db["criterion_id"])
                else:
                    conn.execute(text(update_sql), payload)

        return name_to_id

    def delete_missing(self, scenario_id: str, keep_names: List[str]) -> None:
        keep_names = [n.strip() for n in keep_names if n and n.strip()]
        sql = """
        DELETE FROM criteria
        WHERE scenario_id = :scenario_id
          AND name <> ALL(:keep_names)
        """
        with self.engine.begin() as conn:
            conn.execute(text(sql), {"scenario_id": scenario_id, "keep_names": keep_names})
