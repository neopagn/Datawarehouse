"""Student-level reads. Features and labels are separate queries so scoring can never see an outcome."""
from src.dashboard.queries import rows


CHECKPOINT_WEEKS = (3, 7, 11)
SCORE_LAG_DAYS = 14

# Only the two snapshots at or before the cutoff, plus attributes fixed at registration.
FEATURE_ROWS = """
SELECT w.student_key, w.offering_key, s.id_student, o.code_module, o.code_presentation,
       e.num_prev_attempts, e.studied_credits,
       w.clicks_week, w.clicks_cum, w.days_since_last_activity,
       w.submitted_cum, w.due_cum, w.missed_cum,
       w.avg_score_cum AS score_now, lagged.avg_score_cum AS score_lagged
FROM dw.fact_student_week w
JOIN dw.dim_offering o ON o.offering_key = w.offering_key
JOIN dw.dim_student s ON s.student_key = w.student_key
JOIN dw.fact_enrollment e ON e.student_key = w.student_key AND e.offering_key = w.offering_key
LEFT JOIN dw.fact_student_week lagged
       ON lagged.student_key = w.student_key AND lagged.offering_key = w.offering_key
      AND lagged.snapshot_day_key = %(cutoff)s - %(lag)s
WHERE w.offering_key = ANY(%(offering_keys)s::smallint[]) AND w.snapshot_day_key = %(cutoff)s
ORDER BY w.offering_key, w.student_key
"""
LABEL_ROWS = """
SELECT e.student_key, e.offering_key, r.is_at_risk
FROM dw.fact_enrollment e JOIN dw.dim_result r USING (result_key)
WHERE e.offering_key = ANY(%(offering_keys)s::smallint[])
"""
LEAVER_ROWS = """
SELECT count(*) AS enrollments,
       count(*) FILTER (WHERE unregistration_day_key > -9000
                        AND unregistration_day_key <= %(first_cutoff)s) AS left_before_first_cutoff,
       count(*) FILTER (WHERE unregistration_day_key > -9000
                        AND unregistration_day_key <= %(cutoff)s) AS left_before_cutoff
FROM dw.fact_enrollment
WHERE offering_key = ANY(%(offering_keys)s::smallint[])
"""


def cutoff_day(week):
    return 7 * week + 6


def feature_rows(conn, offering_keys, week):
    return rows(conn, FEATURE_ROWS, {'offering_keys': offering_keys, 'cutoff': cutoff_day(week),
                                     'lag': SCORE_LAG_DAYS})


def label_rows(conn, offering_keys):
    return rows(conn, LABEL_ROWS, {'offering_keys': offering_keys})


def leavers(conn, offering_keys, week=None):
    """Enrollments gone before a snapshot, so no contact list can cover them. Sentinels are not days."""
    return rows(conn, LEAVER_ROWS, {'offering_keys': offering_keys, 'first_cutoff': cutoff_day(0),
                                    'cutoff': cutoff_day(0 if week is None else week)})[0]
