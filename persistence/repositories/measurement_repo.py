# persistence/repositories/measurement_repo.py
from typing import List, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


class MeasurementRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def load_matrix_ui(self, scenario_id: str) -> pd.DataFrame:
        """
        Returns a pivoted dataframe with index=alternative_name, columns=criterion_name, values=value_num
        """
        sql = """
        SELECT a.name AS alternative_name, c.name AS criterion_name, m.value_num
        FROM measurements m
        JOIN alternatives a ON a.alternative_id = m.alternative_id
        JOIN criteria c ON c.criterion_id = m.criterion_id
        WHERE m.scenario_id = :scenario_id
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"scenario_id": scenario_id}).mappings().all()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(r) for r in rows])
        return df.pivot(index="alternative_name", columns="criterion_name", values="value_num")

    def replace_all_for_scenario(
        self,
        scenario_id: str,
        alt_name_to_id: dict,
        crit_name_to_id: dict,
        matrix_ui: pd.DataFrame,
    ) -> None:
        """
        matrix_ui index: alternative names
        columns: criterion names
        """
        del_sql = "DELETE FROM measurements WHERE scenario_id = :scenario_id"
        ins_sql = """
        INSERT INTO measurements (scenario_id, alternative_id, criterion_id, value_num)
        VALUES (:scenario_id, :alternative_id, :criterion_id, :value_num)
        """

        payloads: List[dict] = []
        for alt_name in matrix_ui.index:
            for crit_name in matrix_ui.columns:
                val = matrix_ui.loc[alt_name, crit_name]
                payloads.append({
                    "scenario_id": scenario_id,
                    "alternative_id": alt_name_to_id[alt_name],
                    "criterion_id": crit_name_to_id[crit_name],
                    "value_num": float(val),
                })

        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"scenario_id": scenario_id})
            conn.execute(text(ins_sql), payloads)
