-- Operational bootstrap: never execute the destructive baseline log DDL on reload.
CREATE SCHEMA IF NOT EXISTS etl;
CREATE TABLE IF NOT EXISTS etl.run (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(10) NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED'))
);
CREATE TABLE IF NOT EXISTS etl.job_log (
    run_id BIGINT NOT NULL REFERENCES etl.run,
    job_id VARCHAR(5) NOT NULL,
    target_table VARCHAR(60),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    rows_written BIGINT,
    status VARCHAR(10) NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    message TEXT,
    PRIMARY KEY (run_id, job_id)
);
CREATE TABLE IF NOT EXISTS etl.check_result (
    run_id BIGINT NOT NULL REFERENCES etl.run,
    check_name VARCHAR(80) NOT NULL,
    expected BIGINT NOT NULL,
    actual BIGINT,
    passed BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, check_name)
);
