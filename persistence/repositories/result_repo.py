from typing import Dict, List
from sqlalchemy import text
from sqlalchemy.engine import Engine


class ResultRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def replace_scores(self, run_id: str, alt_id_to_score: Dict[str, float]) -> None:
        del_sql = "DELETE FROM result_scores WHERE run_id = :run_id"
        ins_sql = """
        INSERT INTO result_scores (run_id, alternative_id, score, rank)
        VALUES (:run_id, :alternative_id, :score, :rank)
        """
        sorted_items = sorted(alt_id_to_score.items(), key=lambda kv: kv[1], reverse=True)

        payloads: List[dict] = []
        for idx, (alt_id, score) in enumerate(sorted_items, start=1):
            payloads.append(
                {"run_id": run_id, "alternative_id": alt_id, "score": float(score), "rank": int(idx)}
            )

        with self.engine.begin() as conn:
            conn.execute(text(del_sql), {"run_id": run_id})
            if payloads:
                conn.execute(text(ins_sql), payloads)

    def get_scores_with_names(self, run_id: str) -> List[dict]:
        sql = """
        SELECT a.name AS alternative_name, rs.score, rs.rank
        FROM result_scores rs
        JOIN alternatives a ON a.alternative_id = rs.alternative_id
        WHERE rs.run_id = :run_id
        ORDER BY rs.rank ASC
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"run_id": run_id}).mappings().all()
        return [dict(r) for r in rows]
