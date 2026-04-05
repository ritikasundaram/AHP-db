import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


class TopsisReadRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def get_distances(self, run_id: str) -> pd.DataFrame:
        sql = """
        SELECT a.name AS alternative, d.s_pos, d.s_neg, d.c_star
        FROM topsis_distances d
        JOIN alternatives a ON a.alternative_id = d.alternative_id
        WHERE d.run_id = :run_id
        ORDER BY d.c_star DESC
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"run_id": run_id}).mappings().all()
        return pd.DataFrame([dict(r) for r in rows])

    def get_ideals(self, run_id: str) -> pd.DataFrame:
        sql = """
        SELECT c.name AS criterion, i.pos_ideal, i.neg_ideal
        FROM topsis_ideals i
        JOIN criteria c ON c.criterion_id = i.criterion_id
        WHERE i.run_id = :run_id
        ORDER BY c.name
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"run_id": run_id}).mappings().all()
        return pd.DataFrame([dict(r) for r in rows])

    def get_matrix(self, run_id: str, which: str) -> pd.DataFrame:
        if which not in ("normalized", "weighted"):
            raise ValueError("which must be 'normalized' or 'weighted'")

        table = "topsis_normalized_values" if which == "normalized" else "topsis_weighted_values"

        sql = f"""
        SELECT a.name AS alternative, c.name AS criterion, v.value
        FROM {table} v
        JOIN alternatives a ON a.alternative_id = v.alternative_id
        JOIN criteria c ON c.criterion_id = v.criterion_id
        WHERE v.run_id = :run_id
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"run_id": run_id}).mappings().all()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame([dict(r) for r in rows])
        return df.pivot(index="alternative", columns="criterion", values="value")
