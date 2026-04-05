# persistence/repositories/preference_repo.py
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


class PreferenceRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def get_or_create_preference_set(
        self,
        scenario_id: str,
        name: str = "Default Weights",
        pref_type: str = "direct",
        created_by: str = "",
    ) -> str:
        sel = """
        SELECT preference_set_id::text AS preference_set_id
        FROM preference_sets
        WHERE scenario_id = :scenario_id AND name = :name
        LIMIT 1
        """
        ins = """
        INSERT INTO preference_sets (scenario_id, type, name, status, created_by)
        VALUES (:scenario_id, :type, :name, 'active', :created_by)
        RETURNING preference_set_id::text AS preference_set_id
        """
        with self.engine.begin() as conn:
            row = conn.execute(text(sel), {"scenario_id": scenario_id, "name": name}).mappings().first()
            if row:
                return str(row["preference_set_id"])
            row2 = conn.execute(text(ins), {"scenario_id": scenario_id, "type": pref_type, "name": name, "created_by": created_by}).mappings().first()
            return str(row2["preference_set_id"])

    def load_weights_by_criterion_name(self, preference_set_id: str) -> Dict[str, float]:
        sql = """
        SELECT c.name AS criterion_name, cw.weight
        FROM criterion_weights cw
        JOIN criteria c ON c.criterion_id = cw.criterion_id
        WHERE cw.preference_set_id = :pref_id
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"pref_id": preference_set_id}).mappings().all()
        return {r["criterion_name"]: float(r["weight"]) for r in rows}

    def replace_weights(self, preference_set_id: str, crit_name_to_id: Dict[str, str], weights_by_name: Dict[str, float]) -> None:
        del_sql = "DELETE FROM criterion_weights WHERE preference_set_id = :pref_id"
        ins_sql = """
        INSERT INTO criterion_weights (preference_set_id, criterion_id, weight, weight_type, derived_from)
        VALUES (:pref_id, :criterion_id, :weight, 'raw', 'direct')
        """
        payloads = []
        for crit_name, crit_id in crit_name_to_id.items():
            w = float(weights_by_name.get(crit_name, 0.0))
            payloads.append({"pref_id": preference_set_id, "criterion_id": crit_id, "weight": w})

        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"pref_id": preference_set_id})
            conn.execute(text(ins_sql), payloads)
