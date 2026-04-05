CREATE EXTENSION IF NOT EXISTS pgcrypto;


CREATE TABLE IF NOT EXISTS decisions (
  decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  purpose TEXT,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','archived')),
  owner_team TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS scenarios (
  scenario_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  decision_id UUID NOT NULL REFERENCES decisions(decision_id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by TEXT,
  UNIQUE (decision_id, name)
);

CREATE INDEX IF NOT EXISTS idx_scenarios_decision_id ON scenarios(decision_id);

CREATE TABLE IF NOT EXISTS alternatives (
  alternative_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id UUID NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (scenario_id, name)
);

CREATE INDEX IF NOT EXISTS idx_alternatives_scenario_id ON alternatives(scenario_id);

CREATE TABLE IF NOT EXISTS criteria (
  criterion_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id UUID NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  direction TEXT NOT NULL CHECK (direction IN ('benefit','cost')),
  scale_type TEXT NOT NULL CHECK (scale_type IN ('ratio','interval','ordinal','binary')),
  unit TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (scenario_id, name)
);

CREATE INDEX IF NOT EXISTS idx_criteria_scenario_id ON criteria(scenario_id);

CREATE TABLE IF NOT EXISTS measurements (
  measurement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id UUID NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
  alternative_id UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
  criterion_id UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
  value_num DOUBLE PRECISION NOT NULL,
  source TEXT,
  confidence DOUBLE PRECISION CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  note TEXT,
  collected_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (scenario_id, alternative_id, criterion_id)
);

CREATE INDEX IF NOT EXISTS idx_measurements_scenario_id ON measurements(scenario_id);
CREATE INDEX IF NOT EXISTS idx_measurements_alt_id ON measurements(alternative_id);
CREATE INDEX IF NOT EXISTS idx_measurements_crit_id ON measurements(criterion_id);

CREATE TABLE IF NOT EXISTS preference_sets (
  preference_set_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id UUID NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('direct','ahp','vft','qfd')),
  name TEXT NOT NULL DEFAULT 'Default Weights',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by TEXT,
  note TEXT,
  UNIQUE (scenario_id, name)
);

CREATE INDEX IF NOT EXISTS idx_preference_sets_scenario_id ON preference_sets(scenario_id);

CREATE TABLE IF NOT EXISTS criterion_weights (
  preference_set_id UUID NOT NULL REFERENCES preference_sets(preference_set_id) ON DELETE CASCADE,
  criterion_id UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
  weight DOUBLE PRECISION NOT NULL CHECK (weight >= 0),
  weight_type TEXT NOT NULL DEFAULT 'normalized' CHECK (weight_type IN ('raw','normalized')),
  derived_from TEXT NOT NULL DEFAULT 'direct' CHECK (derived_from IN ('direct','ahp','vft','qfd')),
  PRIMARY KEY (preference_set_id, criterion_id)
);

CREATE INDEX IF NOT EXISTS idx_criterion_weights_criterion_id ON criterion_weights(criterion_id);

CREATE TABLE IF NOT EXISTS runs (
  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id UUID NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
  preference_set_id UUID NOT NULL REFERENCES preference_sets(preference_set_id) ON DELETE RESTRICT,
  method TEXT NOT NULL CHECK (method IN ('topsis','vft','ahp')),
  engine_version TEXT NOT NULL DEFAULT 'core=0.1.0',
  executed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  executed_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_scenario_id ON runs(scenario_id);

CREATE TABLE IF NOT EXISTS result_scores (
  run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  alternative_id UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
  score DOUBLE PRECISION NOT NULL,
  rank INT,
  PRIMARY KEY (run_id, alternative_id)
);

CREATE INDEX IF NOT EXISTS idx_result_scores_run_id ON result_scores(run_id);

CREATE TABLE IF NOT EXISTS scenario_validation (
  scenario_id UUID PRIMARY KEY REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
  is_complete_matrix BOOLEAN NOT NULL,
  missing_cells_count INT NOT NULL DEFAULT 0,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =========================
-- TOPSIS TABLES
-- =========================
CREATE TABLE IF NOT EXISTS topsis_run_config (
  run_id UUID PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
  normalization TEXT NOT NULL CHECK (normalization IN ('vector')),
  distance TEXT NOT NULL CHECK (distance IN ('euclidean'))
);

CREATE TABLE IF NOT EXISTS topsis_normalized_values (
  run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  alternative_id UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
  criterion_id UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
  value DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (run_id, alternative_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS topsis_weighted_values (
  run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  alternative_id UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
  criterion_id UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
  value DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (run_id, alternative_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS topsis_ideals (
  run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  criterion_id UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
  pos_ideal DOUBLE PRECISION NOT NULL,
  neg_ideal DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (run_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS topsis_distances (
  run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  alternative_id UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
  s_pos DOUBLE PRECISION NOT NULL,
  s_neg DOUBLE PRECISION NOT NULL,
  c_star DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (run_id, alternative_id)
);

-- =========================
-- VFT TABLES
-- =========================
CREATE TABLE IF NOT EXISTS vft_run_config (
  run_id UUID PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
  output_min DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  output_max DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  missing_policy TEXT NOT NULL DEFAULT 'reject' CHECK (missing_policy IN ('reject'))
);

CREATE TABLE IF NOT EXISTS value_functions (
  value_function_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_id UUID NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE,
  criterion_id UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
  function_type TEXT NOT NULL CHECK (function_type IN ('piecewise_linear','linear')),
  output_min DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  output_max DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by TEXT,
  note TEXT,
  UNIQUE (scenario_id, criterion_id)
);

CREATE INDEX IF NOT EXISTS idx_value_functions_scenario_id ON value_functions(scenario_id);

CREATE TABLE IF NOT EXISTS value_function_points (
  value_function_id UUID NOT NULL REFERENCES value_functions(value_function_id) ON DELETE CASCADE,
  point_order INT NOT NULL,
  x DOUBLE PRECISION NOT NULL,
  y DOUBLE PRECISION NOT NULL CHECK (y >= 0 AND y <= 1),
  PRIMARY KEY (value_function_id, point_order),
  UNIQUE (value_function_id, x)
);

CREATE TABLE IF NOT EXISTS vft_criterion_utilities (
  run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  alternative_id UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
  criterion_id UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
  raw_value DOUBLE PRECISION NOT NULL,
  utility_value DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (run_id, alternative_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS vft_weighted_utilities (
  run_id UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
  alternative_id UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
  criterion_id UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
  weight DOUBLE PRECISION NOT NULL,
  weighted_utility DOUBLE PRECISION NOT NULL,
  PRIMARY KEY (run_id, alternative_id, criterion_id)
);

-- =========================
-- AHP TABLES
-- =========================
CREATE TABLE IF NOT EXISTS ahp_criteria_judgments (
    preference_set_id UUID NOT NULL REFERENCES preference_sets(preference_set_id) ON DELETE CASCADE,
    criterion_i_id    UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
    criterion_j_id    UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
    judgment          DOUBLE PRECISION NOT NULL CHECK (judgment > 0),
    PRIMARY KEY (preference_set_id, criterion_i_id, criterion_j_id)
);

CREATE INDEX IF NOT EXISTS idx_ahp_crit_judgments_pref ON ahp_criteria_judgments(preference_set_id);

CREATE TABLE IF NOT EXISTS ahp_alternative_judgments (
    preference_set_id UUID NOT NULL REFERENCES preference_sets(preference_set_id) ON DELETE CASCADE,
    criterion_id      UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
    alternative_i_id  UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
    alternative_j_id  UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
    judgment          DOUBLE PRECISION NOT NULL CHECK (judgment > 0),
    PRIMARY KEY (preference_set_id, criterion_id, alternative_i_id, alternative_j_id)
);

CREATE TABLE IF NOT EXISTS ahp_run_artifacts (
    run_id      UUID PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    criteria_cr DOUBLE PRECISION NOT NULL,
    lambda_max  DOUBLE PRECISION NOT NULL,
    n_criteria  INT NOT NULL,
    mode        TEXT NOT NULL DEFAULT 'hybrid' CHECK (mode IN ('full','hybrid'))
);

CREATE TABLE IF NOT EXISTS ahp_criterion_priorities (
    run_id       UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    criterion_id UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
    priority     DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (run_id, criterion_id)
);

CREATE TABLE IF NOT EXISTS ahp_alternative_priorities (
    run_id         UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    criterion_id   UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
    alternative_id UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
    priority       DOUBLE PRECISION NOT NULL,
    cr             DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    PRIMARY KEY (run_id, criterion_id, alternative_id)
);
