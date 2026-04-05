from typing import Dict, List
from sqlalchemy import text
from sqlalchemy.engine import Engine


class TopsisRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def save_run_config(self, run_id: str, normalization: str = "vector", distance: str = "euclidean") -> None:
        sql = """
        INSERT INTO topsis_run_config (run_id, normalization, distance)
        VALUES (:run_id, :normalization, :distance)
        ON CONFLICT (run_id) DO UPDATE SET normalization = EXCLUDED.normalization, distance = EXCLUDED.distance
        """
        with self.engine.begin() as conn:
            conn.execute(text(sql), {"run_id": run_id, "normalization": normalization, "distance": distance})

    def replace_normalized(self, run_id: str, rows: List[dict]) -> None:
        del_sql = "DELETE FROM topsis_normalized_values WHERE run_id = :run_id"
        ins_sql = """
        INSERT INTO topsis_normalized_values (run_id, alternative_id, criterion_id, value)
        VALUES (:run_id, :alternative_id, :criterion_id, :value)
        """
        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"run_id": run_id})
            if rows:
                conn.execute(text(ins_sql), rows)

    def replace_weighted(self, run_id: str, rows: List[dict]) -> None:
        del_sql = "DELETE FROM topsis_weighted_values WHERE run_id = :run_id"
        ins_sql = """
        INSERT INTO topsis_weighted_values (run_id, alternative_id, criterion_id, value)
        VALUES (:run_id, :alternative_id, :criterion_id, :value)
        """
        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"run_id": run_id})
            if rows:
                conn.execute(text(ins_sql), rows)

    def replace_ideals(self, run_id: str, rows: List[dict]) -> None:
        del_sql = "DELETE FROM topsis_ideals WHERE run_id = :run_id"
        ins_sql = """
        INSERT INTO topsis_ideals (run_id, criterion_id, pos_ideal, neg_ideal)
        VALUES (:run_id, :criterion_id, :pos_ideal, :neg_ideal)
        """
        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"run_id": run_id})
            if rows:
                conn.execute(text(ins_sql), rows)

    def replace_distances(self, run_id: str, rows: List[dict]) -> None:
        del_sql = "DELETE FROM topsis_distances WHERE run_id = :run_id"
        ins_sql = """
        INSERT INTO topsis_distances (run_id, alternative_id, s_pos, s_neg, c_star)
        VALUES (:run_id, :alternative_id, :s_pos, :s_neg, :c_star)
        """
        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"run_id": run_id})
            if rows:
                conn.execute(text(ins_sql), rows)
