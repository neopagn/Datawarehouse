"""Run the sample ETL SQL against a database already loaded by validate_design.py and compare the
result with the tables built by pandas. Also applies the log DDL and runs the acceptance checks.

Run:  python src/profiling/check_etl_samples.py <work_dir> <pg_package_dir> src/sql > docs/etl_check_output.txt
"""
import os
import re
import site
import sys
import time

WORK, PG_PKG, SQL = sys.argv[1:4]
sys.path.append(site.getusersitepackages())
sys.path.insert(0, PG_PKG)
import pgserver

sys.stdout.reconfigure(encoding="utf-8")
db = pgserver.get_server(os.path.join(WORK, "pgdata"), cleanup_mode="stop")


def read(*parts):
    with open(os.path.join(SQL, *parts), encoding="utf-8") as f:
        return f.read()


def as_temp(path, name):
    """Turn the sample INSERT into a temp table so the real table can serve as the comparison."""
    body, n = re.subn(r"INSERT INTO dw\.\w+ \(.*?\)\n", f"CREATE TEMP TABLE {name} AS\n", read(*path), count=1, flags=re.S)
    assert n == 1
    return body


def h(title):
    print(f"\n{'=' * 8} {title} {'=' * 8}", flush=True)


def run(title, sql):
    t = time.time()
    out = db.psql(sql)
    print(f"--- {title} ({time.time() - t:.0f}s)\n{out if out.strip() else 'QUERY FAILED: no output'}", flush=True)


h("J03 dim_student: SQL vs pandas")
run("dim_student", as_temp(("etl_mau", "j03_dim_student.sql"), "chk") + """
SELECT (SELECT count(*) FROM chk) AS sql_rows,
       (SELECT count(*) FROM (SELECT * FROM chk EXCEPT SELECT student_key, id_student, version_no, gender, region, highest_education, imd_band, imd_order, age_band, disability, valid_from_presentation, valid_to_presentation, is_current FROM dw.dim_student) x) AS only_in_sql,
       (SELECT count(*) FROM (SELECT student_key, id_student, version_no, gender, region, highest_education, imd_band, imd_order, age_band, disability, valid_from_presentation, valid_to_presentation, is_current FROM dw.dim_student EXCEPT SELECT * FROM chk) x) AS only_in_table;
""")

h("J08 fact_vle_daily: SQL vs pandas")
run("fact_vle_daily", as_temp(("etl_mau", "j08_fact_vle_daily.sql"), "chk") + """
SELECT (SELECT count(*) FROM chk) AS sql_rows,
       (SELECT count(*) FROM (SELECT * FROM chk EXCEPT SELECT * FROM dw.fact_vle_daily) x) AS only_in_sql,
       (SELECT count(*) FROM (SELECT * FROM dw.fact_vle_daily EXCEPT SELECT * FROM chk) x) AS only_in_table;
""")

h("J10 fact_student_week: SQL vs pandas, all rows and all columns")
run("fact_student_week", as_temp(("etl_mau", "j10_fact_student_week.sql"), "chk") + """
SELECT (SELECT count(*) FROM chk) AS sql_rows,
       count(*) FILTER (WHERE c.student_key IS NULL) AS only_in_table,
       count(*) FILTER (WHERE w.student_key IS NULL) AS only_in_sql,
       count(*) FILTER (WHERE c.clicks_week IS DISTINCT FROM w.clicks_week) AS clicks_week,
       count(*) FILTER (WHERE c.active_days_week IS DISTINCT FROM w.active_days_week) AS active_days_week,
       count(*) FILTER (WHERE c.clicks_cum IS DISTINCT FROM w.clicks_cum) AS clicks_cum,
       count(*) FILTER (WHERE c.active_days_cum IS DISTINCT FROM w.active_days_cum) AS active_days_cum,
       count(*) FILTER (WHERE c.days_since_last_activity IS DISTINCT FROM w.days_since_last_activity) AS days_since,
       count(*) FILTER (WHERE c.submitted_cum IS DISTINCT FROM w.submitted_cum) AS submitted_cum,
       count(*) FILTER (WHERE c.due_cum IS DISTINCT FROM w.due_cum) AS due_cum,
       count(*) FILTER (WHERE c.missed_cum IS DISTINCT FROM w.missed_cum) AS missed_cum,
       count(*) FILTER (WHERE (c.avg_score_cum IS NULL) <> (w.avg_score_cum IS NULL) OR abs(c.avg_score_cum - w.avg_score_cum) > 0.011) AS avg_score_cum
FROM chk c FULL JOIN dw.fact_student_week w
  ON c.student_key = w.student_key AND c.offering_key = w.offering_key AND c.snapshot_day_key = w.snapshot_day_key;
""")

h("LOG DDL")
run("apply 02_ddl_etl_log.sql", "\\set ON_ERROR_STOP on\n" + read("02_ddl_etl_log.sql") + """
SELECT table_name FROM information_schema.tables WHERE table_schema = 'etl' ORDER BY 1;
""")

h("ACCEPTANCE CHECKS (03_kiem_tra_sau_nap.sql)")
run("checks", read("03_kiem_tra_sau_nap.sql"))
db.cleanup()
print("done", flush=True)
