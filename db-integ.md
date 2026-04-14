# Database Integration Documentation

This document provides a detailed overview of how the MCDA (Multi-Criteria Decision Analysis) tool integrates with PostgreSQL for data persistence.

---

## Table of Contents

1. [Overview](#overview)
2. [Technology Stack](#technology-stack)
3. [Configuration](#configuration)
4. [Database Schema](#database-schema)
5. [Architecture Layers](#architecture-layers)
6. [Engine Module](#engine-module)
7. [Repository Pattern](#repository-pattern)
8. [Service Layer](#service-layer)
9. [Transaction Management](#transaction-management)
10. [Migrations](#migrations)
11. [Data Flow Examples](#data-flow-examples)

---

## Overview

The application uses a **layered architecture** for database access:

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit UI (app/)                      │
├─────────────────────────────────────────────────────────────┤
│                   Service Layer (services/)                 │
├─────────────────────────────────────────────────────────────┤
│              Repository Layer (persistence/repositories/)   │
├─────────────────────────────────────────────────────────────┤
│                 Engine Module (persistence/engine.py)       │
├─────────────────────────────────────────────────────────────┤
│                       PostgreSQL Database                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| **Database** | PostgreSQL | 14+ |
| **ORM/Driver** | SQLAlchemy | 2.0.46 |
| **Python Driver** | psycopg2-binary | 2.9.11 |
| **Extensions** | pgcrypto | Built-in |

Key dependencies from `requirements.txt`:
```
SQLAlchemy==2.0.46
psycopg2-binary==2.9.11
```

---

## Configuration

### Environment Variables

Database connection is configured via the `DATABASE_URL` environment variable.

**`.env.example`:**
```
DATABASE_URL=postgresql://user:password@localhost:5432/mcda_db
```

### Loading Configuration

The `persistence/engine.py` module handles configuration loading:

```python
def load_env():
    root = Path(__file__).resolve().parents[1]  # project root
    env_path = root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())
```

**Key points:**
- Automatically loads `.env` from project root
- Uses `os.environ.setdefault()` to avoid overwriting existing env vars
- Supports comments (`#`) and empty lines

---

## Database Schema

The schema is defined in `schema/schema.sql` and uses PostgreSQL-specific features.

### Core Tables

| Table | Purpose |
|-------|---------|
| `decisions` | Top-level decision projects |
| `scenarios` | Analysis scenarios within a decision |
| `alternatives` | Options being evaluated |
| `criteria` | Evaluation criteria |
| `measurements` | Performance matrix values |
| `preference_sets` | Weight configuration sets |
| `criterion_weights` | Individual criterion weights |
| `runs` | Execution records |
| `result_scores` | Final rankings |

### TOPSIS-Specific Tables

| Table | Purpose |
|-------|---------|
| `topsis_run_config` | Normalization/distance method config |
| `topsis_normalized_values` | Normalized decision matrix |
| `topsis_weighted_values` | Weighted normalized matrix |
| `topsis_ideals` | Positive/negative ideal solutions |
| `topsis_distances` | Distance calculations and C* scores |

### VFT-Specific Tables

| Table | Purpose |
|-------|---------|
| `value_functions` | Value function definitions |
| `value_function_points` | Piecewise linear function points |
| `vft_run_config` | VFT run configuration |
| `vft_criterion_utilities` | Raw → utility mappings |
| `vft_weighted_utilities` | Weighted utility values |

### AHP-Specific Tables

| Table | Purpose |
|-------|---------|
| `ahp_criteria_judgments` | Pairwise comparisons between criteria (Saaty 1–9 scale) per preference set |
| `ahp_alternative_judgments` | Pairwise comparisons between alternatives per criterion (full AHP mode) |
| `ahp_run_artifacts` | Run-level metadata: CR, λ_max, n_criteria, mode (full/hybrid) |
| `ahp_criterion_priorities` | Derived priority weights per criterion per run |
| `ahp_alternative_priorities` | Derived alternative priorities per criterion per run, with per-criterion CR |

AHP also uses the shared `preference_sets` table with `type='ahp'` and `criterion_weights` with `derived_from='ahp'`.

### Key Design Patterns

1. **UUID Primary Keys** — All tables use `uuid` with `gen_random_uuid()` default
2. **Cascading Deletes** — Foreign keys use `ON DELETE CASCADE`
3. **Check Constraints** — Enum-like validation (e.g., `direction IN ('benefit', 'cost')`)
4. **Timestamps** — `created_at` with `DEFAULT now()`

### Entity Relationship Summary

```
decisions
    └── scenarios (1:N)
            ├── alternatives (1:N)
            ├── criteria (1:N)
            ├── measurements (1:N) → references alternatives, criteria
            ├── preference_sets (1:N)
            │       └── criterion_weights (1:N) → references criteria
            ├── value_functions (1:N) → references criteria
            │       └── value_function_points (1:N)
            └── runs (1:N) → references preference_sets
                    ├── result_scores (1:N) → references alternatives
                    ├── topsis_* tables (1:N)
                    ├── vft_* tables (1:N)
                    ├── ahp_* tables (1:N)
        preference_sets (type='ahp')
                └── ahp_criteria_judgments (1:N) → references criteria
                └── ahp_alternative_judgments (1:N) → references criteria, alternatives
```

---

## Architecture Layers

### Layer 1: Engine Module (`persistence/engine.py`)

Provides singleton database engine access.

```python
@dataclass(frozen=True)
class DBConfig:
    database_url: str

_engine: Optional[Engine] = None

def get_db_config() -> DBConfig:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    return DBConfig(database_url=url)

def get_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine
    cfg = get_db_config()
    _engine = create_engine(cfg.database_url, pool_pre_ping=True, future=True)
    return _engine
```

**Key features:**
- **Singleton pattern** — Single engine instance reused across requests
- **Connection pooling** — `pool_pre_ping=True` validates connections before use
- **Future mode** — `future=True` enables SQLAlchemy 2.0 style

### Layer 2: Repository Layer (`persistence/repositories/`)

Each domain entity has a dedicated repository class.

| Repository | Entity | Key Methods |
|------------|--------|-------------|
| `DecisionRepo` | decisions | `create_decision()`, `get_decision()`, `list_decisions()` |
| `ScenarioRepo` | scenarios | `create_scenario()`, `get_scenario()`, `list_scenarios()` |
| `AlternativeRepo` | alternatives | `list_by_scenario()`, `upsert_by_names()`, `delete_missing()` |
| `CriterionRepo` | criteria | `list_by_scenario()`, `upsert_rows()`, `delete_missing()` |
| `MeasurementRepo` | measurements | `load_matrix_ui()`, `replace_all_for_scenario()` |
| `PreferenceRepo` | preference_sets, criterion_weights | `get_or_create_preference_set()`, `replace_weights()` |
| `RunRepo` | runs | `create_run()`, `list_runs()` |
| `ResultRepo` | result_scores | `replace_scores()`, `get_scores_with_names()` |
| `TopsisRepo` | topsis_* tables | `save_run_config()`, `replace_normalized()`, etc. |
| `TopsisReadRepo` | topsis_* tables (read) | `get_distances()`, `get_ideals()`, `get_matrix()` |
| `AHPRepo` | ahp_* tables | `save_criteria_judgments()`, `save_alternative_judgments()`, `save_run_artifacts()`, `replace_criterion_priorities()`, `replace_alternative_priorities()`, `get_*()` readers |

### Layer 3: Service Layer (`services/`)

Business logic that orchestrates multiple repositories.

| Service | Purpose |
|---------|---------|
| `ScenarioService` | Loads complete scenario data for analysis |
| `TopsisService` | Runs TOPSIS and persists all artifacts |
| `AHPService` | Runs AHP (full or hybrid mode) and persists all artifacts |
| `VFTService` | Runs VFT and persists results |
| `DeleteService` | Cascading delete operations |
| `ScenarioShareService` | Export/import `.mcda` files |

---

## Engine Module

### `persistence/engine.py` — Full Implementation

```python
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

def get_engine() -> Engine:
    global _engine
    if _engine is not None:
        return _engine
    cfg = get_db_config()
    _engine = create_engine(cfg.database_url, pool_pre_ping=True, future=True)
    return _engine

def ping_db() -> bool:
    try:
        eng = get_engine()
        with eng.begin() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
```

**Usage in UI:**
```python
from persistence.engine import get_engine, ping_db

# Check database connectivity
if ping_db():
    engine = get_engine()
    # Use engine...
```

---

## Repository Pattern

### Pattern Overview

Each repository:
1. Accepts an `Engine` instance via constructor injection
2. Uses raw SQL with `sqlalchemy.text()` for queries
3. Returns Python dicts or domain objects (not ORM models)

### Example: `CriterionRepo`

```python
class CriterionRepo:
    def __init__(self, engine: Engine):
        self.engine = engine

    def list_by_scenario(self, scenario_id: str) -> List[dict]:
        sql = """
        SELECT criterion_id::text AS criterion_id, name, direction, 
               scale_type, unit, description, created_at
        FROM criteria
        WHERE scenario_id = :scenario_id
        ORDER BY name
        """
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"scenario_id": scenario_id}).mappings().all()
        return [dict(r) for r in rows]

    def upsert_rows(self, scenario_id: str, rows: List[dict]) -> Dict[str, str]:
        # Insert new, update existing
        # Returns name -> criterion_id mapping
        ...

    def delete_missing(self, scenario_id: str, keep_names: List[str]) -> None:
        sql = """
        DELETE FROM criteria
        WHERE scenario_id = :scenario_id
          AND name <> ALL(:keep_names)
        """
        with self.engine.begin() as conn:
            conn.execute(text(sql), {"scenario_id": scenario_id, "keep_names": keep_names})
```

### Key Patterns

1. **UUID Casting** — `criterion_id::text AS criterion_id` for JSON serialization
2. **Parameterized Queries** — `:param` syntax prevents SQL injection
3. **Mapping Results** — `.mappings().all()` returns dict-like rows
4. **Upsert Logic** — Check existing, insert new, update changed

---

## Service Layer

### `ScenarioService` — Loading Analysis Data

Aggregates data from multiple tables into a single `ScenarioData` object:

```python
@dataclass(frozen=True)
class ScenarioData:
    alternative_ids: List[str]
    alternative_names: List[str]
    criterion_ids: List[str]
    criterion_names: List[str]
    directions: List[str]
    matrix: np.ndarray       # shape (m, n)
    weights: np.ndarray      # shape (n,)
    weight_by_criterion: Dict[str, float]

class ScenarioService:
    def __init__(self, engine: Engine):
        self.engine = engine

    def load(self, scenario_id: str, preference_set_id: str) -> ScenarioData:
        with self.engine.begin() as conn:
            alts = conn.execute(text("SELECT ... FROM alternatives ..."), {...}).mappings().all()
            crits = conn.execute(text("SELECT ... FROM criteria ..."), {...}).mappings().all()
            measurements = conn.execute(text("SELECT ... FROM measurements ..."), {...}).mappings().all()
            weights_rows = conn.execute(text("SELECT ... FROM criterion_weights ..."), {...}).mappings().all()

        # Build numpy matrix from measurements
        X = np.full((m, n), np.nan, dtype=float)
        for r in measurements:
            X[alt_index[r["alternative_id"]], crit_index[r["criterion_id"]]] = float(r["value_num"])

        return ScenarioData(...)
```

### `TopsisService` — Persisting Run Results

Orchestrates computation and multi-table persistence:

```python
class TopsisService:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.run_repo = RunRepo(engine)
        self.result_repo = ResultRepo(engine)
        self.topsis_repo = TopsisRepo(engine)

    def run_and_persist(self, scenario_id, preference_set_id, executed_by, data) -> str:
        # 1. Compute TOPSIS
        artifacts = compute_topsis(matrix=data.matrix, weights=w, directions=data.directions)

        # 2. Create run record
        run_id = self.run_repo.create_run(scenario_id, preference_set_id, "topsis", executed_by)

        # 3. Save configuration
        self.topsis_repo.save_run_config(run_id, normalization="vector", distance="euclidean")

        # 4. Save scores
        self.result_repo.replace_scores(run_id, alt_id_to_score)

        # 5. Save intermediate artifacts
        self.topsis_repo.replace_normalized(run_id, norm_rows)
        self.topsis_repo.replace_weighted(run_id, w_rows)
        self.topsis_repo.replace_ideals(run_id, ideal_rows)
        self.topsis_repo.replace_distances(run_id, dist_rows)

        return run_id
```

---

## Transaction Management

### Context Manager Pattern

All database operations use SQLAlchemy's `engine.begin()` context manager:

```python
with self.engine.begin() as conn:
    conn.execute(text(sql), params)
    # Auto-commits on successful exit
    # Auto-rollbacks on exception
```

### Batch Operations

For bulk inserts, pass a list of dicts:

```python
ins_sql = """
INSERT INTO measurements (scenario_id, alternative_id, criterion_id, value_num)
VALUES (:scenario_id, :alternative_id, :criterion_id, :value_num)
"""
payloads = [{"scenario_id": sid, "alternative_id": aid, ...}, ...]

with self.engine.begin() as conn:
    conn.execute(text(ins_sql), payloads)  # Executes all in one transaction
```

### Replace Pattern

Many repositories use a "delete then insert" pattern for updates:

```python
def replace_scores(self, run_id: str, alt_id_to_score: Dict[str, float]) -> None:
    del_sql = "DELETE FROM result_scores WHERE run_id = :run_id"
    ins_sql = "INSERT INTO result_scores ..."

    with self.engine.begin() as conn:
        conn.execute(text(del_sql), {"run_id": run_id})
        if payloads:
            conn.execute(text(ins_sql), payloads)
```

---

## Migrations

### Location

Migrations are stored in `schema/migrations/`.

### Migration Files

| File | Purpose |
|------|---------|
| `20260310_add_scenario_method_type.sql` | Added `method_type` column to scenarios |
| `20260330_add_ahp_method.sql` | Extended method constraints to include AHP |

### Example Migration

```sql
-- 20260330_add_ahp_method.sql
ALTER TABLE public.scenarios DROP CONSTRAINT IF EXISTS scenarios_method_type_check;
ALTER TABLE public.scenarios
    ADD CONSTRAINT scenarios_method_type_check
    CHECK (method_type IN ('topsis', 'vft', 'ahp'));

ALTER TABLE public.runs DROP CONSTRAINT IF EXISTS runs_method_check;
ALTER TABLE public.runs
    ADD CONSTRAINT runs_method_check
    CHECK (method IN ('topsis', 'vft', 'ahp'));
```

### Applying Migrations

```bash
psql -d mcda_db -f schema/schema.sql                              # Initial setup
psql -d mcda_db -f schema/migrations/20260330_add_ahp_method.sql  # Apply migration
```

---

## Data Flow Examples

### Example 1: Creating a New Scenario

```
UI (1_decision_setup.py)
    │
    ├── get_engine()
    │
    ├── DecisionRepo.create_decision(title, purpose)
    │       └── INSERT INTO decisions ... RETURNING decision_id
    │
    └── ScenarioRepo.create_scenario(decision_id, name, method_type)
            └── INSERT INTO scenarios ... RETURNING scenario_id
```

### Example 2: Saving Measurement Matrix

```
UI (2_data_input.py)
    │
    ├── AlternativeRepo.upsert_by_names(scenario_id, names)
    │       └── INSERT INTO alternatives (if new)
    │
    ├── CriterionRepo.upsert_rows(scenario_id, rows)
    │       └── INSERT/UPDATE criteria
    │
    └── MeasurementRepo.replace_all_for_scenario(scenario_id, matrix_df)
            ├── DELETE FROM measurements WHERE scenario_id = ?
            └── INSERT INTO measurements (batch)
```

### Example 3: Running TOPSIS Analysis

```
UI (3_run_models.py)
    │
    ├── ScenarioService.load(scenario_id, preference_set_id)
    │       └── SELECT from alternatives, criteria, measurements, criterion_weights
    │
    ├── core.topsis.compute_topsis(matrix, weights, directions)
    │       └── Pure computation (no DB)
    │
    └── Persist results:
            ├── INSERT INTO runs ... RETURNING run_id
            ├── INSERT INTO topsis_run_config
            ├── INSERT INTO result_scores (batch)
            ├── INSERT INTO topsis_normalized_values (batch)
            ├── INSERT INTO topsis_weighted_values (batch)
            ├── INSERT INTO topsis_ideals (batch)
            └── INSERT INTO topsis_distances (batch)
```

### Example 4: Running AHP Analysis (Hybrid Mode)

```
UI (3_run_models.py or ahp_baseball2.py)
    │
    ├── ScenarioService.load(scenario_id, preference_set_id)
    │       └── SELECT from alternatives, criteria, measurements, criterion_weights
    │
    ├── AHPRepo.load_criteria_judgments(preference_set_id)
    │       └── Build upper-triangle list from stored pairwise judgments
    │
    ├── AHPService.run_and_persist()
    │       ├── core.ahp.run_hybrid_ahp(crit_upper, performance_matrix, ...)
    │       │       └── Pure computation: eigenvector weights, column normalisation, CR
    │       │
    │       └── Persist results:
    │               ├── INSERT INTO runs (method='ahp') ... RETURNING run_id
    │               ├── INSERT INTO ahp_run_artifacts (CR, λ_max, n_criteria, mode)
    │               ├── INSERT INTO ahp_criterion_priorities (batch)
    │               ├── INSERT INTO ahp_alternative_priorities (batch)
    │               └── INSERT INTO result_scores (batch)
    │
    └── ResultRepo.get_scores_with_names(run_id)
            └── Final ranking
```

### Example 5: Running AHP Analysis (Full Mode)

```
UI (3_run_models.py)
    │
    ├── AHPRepo.load_alternative_judgments(pref_id, criterion_id)
    │       └── For each criterion, load alternative pairwise judgments
    │
    ├── AHPService.run_and_persist(mode='full')
    │       ├── core.ahp.run_full_ahp(crit_upper, alt_upper_by_crit, ...)
    │       │       └── Full pairwise: criteria AND alternatives
    │       │
    │       └── Persist (same as hybrid, plus per-criterion CR in alt priorities)
    │
    └── ResultRepo.get_scores_with_names(run_id)
```

### Example 6: Standalone AHP with DB Persistence (`ahp_baseball2.py`)

```
ahp_baseball2.py — Database tab
    │
    ├── AlternativeRepo.upsert_by_names(scenario_id, players)
    ├── CriterionRepo.upsert_rows(scenario_id, criteria)
    ├── MeasurementRepo.replace_all_for_scenario(scenario_id, raw_scores)
    │
    ├── PreferenceRepo.get_or_create_preference_set(type='ahp')
    ├── AHPRepo.save_criteria_judgments(pref_id, pairwise_rows)
    ├── INSERT INTO criterion_weights (derived_from='ahp', weights from eigenvector)
    │
    └── AHPService.run_and_persist(mode='hybrid')
            └── Persists run, artifacts, priorities, scores
```

### Example 7: Viewing Results

```
UI (4_results.py)
    │
    ├── RunRepo.list_runs(scenario_id)
    │       └── SELECT from runs
    │
    ├── ResultRepo.get_scores_with_names(run_id)
    │       └── SELECT with JOIN to alternatives
    │
    ├── [TOPSIS] TopsisReadRepo.get_distances(run_id)
    │       └── SELECT with JOIN to alternatives
    │
    └── [AHP] AHPRepo:
            ├── get_run_artifacts(run_id) → CR, λ_max, mode
            ├── get_criterion_priorities(run_id) → weight table
            └── get_alternative_priorities(run_id) → priority table with per-criterion CR
```

---

## Summary

| Aspect | Implementation |
|--------|----------------|
| **Database** | PostgreSQL 14+ with pgcrypto extension |
| **Connection** | SQLAlchemy 2.0 with singleton engine pattern |
| **Configuration** | `DATABASE_URL` environment variable |
| **Query Style** | Raw SQL with `text()` and parameterized queries |
| **Transactions** | `engine.begin()` context manager with auto-commit/rollback |
| **Architecture** | Repository pattern with service layer orchestration |
| **AHP Integration** | Full pipeline: judgments → eigenvector → persist artifacts + scores |
| **AHP Modes** | Hybrid (numeric matrix) and Full (pairwise alternatives) |
| **Migrations** | Manual SQL files in `schema/migrations/` |

The design prioritizes:
- **Explicit SQL** over ORM magic for transparency
- **Dependency injection** of engine for testability
- **Atomic transactions** for data integrity
- **Cascading deletes** for referential integrity
