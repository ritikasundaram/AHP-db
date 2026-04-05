-- schema/schema_ahp.sql
-- Migration: Add AHP support tables and update runs.method constraint
-- Run ONCE against your existing database.
-- Usage: psql $DATABASE_URL -f schema/schema_ahp.sql

-- ── 1. Extend runs.method to include 'ahp' ──────────────────────────────────
-- Drop existing constraint and recreate with 'ahp' added
ALTER TABLE runs
    DROP CONSTRAINT IF EXISTS runs_method_check;

ALTER TABLE runs
    ADD CONSTRAINT runs_method_check
        CHECK (method IN ('topsis', 'vft', 'ahp'));

-- ── 2. AHP criteria pairwise judgments ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS ahp_criteria_judgments (
    preference_set_id UUID NOT NULL
        REFERENCES preference_sets(preference_set_id) ON DELETE CASCADE,
    criterion_i_id    UUID NOT NULL
        REFERENCES criteria(criterion_id) ON DELETE CASCADE,
    criterion_j_id    UUID NOT NULL
        REFERENCES criteria(criterion_id) ON DELETE CASCADE,
    judgment          DOUBLE PRECISION NOT NULL
        CHECK (judgment > 0),
    PRIMARY KEY (preference_set_id, criterion_i_id, criterion_j_id)
);

CREATE INDEX IF NOT EXISTS idx_ahp_crit_judgments_pref
    ON ahp_criteria_judgments(preference_set_id);

-- ── 3. AHP alternative pairwise judgments per criterion ─────────────────────
CREATE TABLE IF NOT EXISTS ahp_alternative_judgments (
    preference_set_id UUID NOT NULL
        REFERENCES preference_sets(preference_set_id) ON DELETE CASCADE,
    criterion_id      UUID NOT NULL
        REFERENCES criteria(criterion_id) ON DELETE CASCADE,
    alternative_i_id  UUID NOT NULL
        REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
    alternative_j_id  UUID NOT NULL
        REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
    judgment          DOUBLE PRECISION NOT NULL
        CHECK (judgment > 0),
    PRIMARY KEY (preference_set_id, criterion_id, alternative_i_id, alternative_j_id)
);

CREATE INDEX IF NOT EXISTS idx_ahp_alt_judgments_pref
    ON ahp_alternative_judgments(preference_set_id);
CREATE INDEX IF NOT EXISTS idx_ahp_alt_judgments_crit
    ON ahp_alternative_judgments(criterion_id);

-- ── 4. AHP run-level artifacts ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ahp_run_artifacts (
    run_id      UUID PRIMARY KEY
        REFERENCES runs(run_id) ON DELETE CASCADE,
    criteria_cr DOUBLE PRECISION NOT NULL,
    lambda_max  DOUBLE PRECISION NOT NULL,
    n_criteria  INT              NOT NULL,
    mode        TEXT             NOT NULL DEFAULT 'hybrid'
        CHECK (mode IN ('full', 'hybrid'))
);

-- ── 5. AHP criterion priority vectors ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ahp_criterion_priorities (
    run_id       UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    criterion_id UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
    priority     DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (run_id, criterion_id)
);

CREATE INDEX IF NOT EXISTS idx_ahp_crit_priorities_run
    ON ahp_criterion_priorities(run_id);

-- ── 6. AHP alternative priorities per criterion ───────────────────────────────
CREATE TABLE IF NOT EXISTS ahp_alternative_priorities (
    run_id         UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    criterion_id   UUID NOT NULL REFERENCES criteria(criterion_id) ON DELETE CASCADE,
    alternative_id UUID NOT NULL REFERENCES alternatives(alternative_id) ON DELETE CASCADE,
    priority       DOUBLE PRECISION NOT NULL,
    cr             DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    PRIMARY KEY (run_id, criterion_id, alternative_id)
);

CREATE INDEX IF NOT EXISTS idx_ahp_alt_priorities_run
    ON ahp_alternative_priorities(run_id);
