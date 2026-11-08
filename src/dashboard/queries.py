"""Fixed, parameterized OLAP queries. Never opens connections or writes data."""
from psycopg.rows import dict_row


COHORT = """
WITH selected AS (
    SELECT * FROM dw.dim_offering WHERE offering_key = ANY(%(offering_keys)s::smallint[])
), e AS (
    SELECT f.*, o.domain, o.code_module, o.code_presentation, s.id_student,
           s.imd_band, s.imd_order, s.highest_education, s.disability,
           r.final_result, r.is_at_risk
    FROM dw.fact_enrollment f
    JOIN selected o USING (offering_key)
    JOIN dw.dim_student s USING (student_key)
    JOIN dw.dim_result r USING (result_key)
)
"""
ENROLLMENT_METRICS = """
    count(*) AS enrollments, count(DISTINCT id_student) AS students,
    count(*) FILTER (WHERE is_at_risk) AS at_risk,
    count(*) FILTER (WHERE final_result = 'Withdrawn') AS withdrawn,
    round(100.0 * count(*) FILTER (WHERE is_at_risk) / nullif(count(*), 0), 2) AS risk_pct,
    round(100.0 * count(*) FILTER (WHERE final_result = 'Withdrawn') / nullif(count(*), 0), 2) AS withdrawn_pct
"""
WEEK_COHORT = COHORT + """, w AS (
    SELECT w.*, e.final_result, e.is_at_risk
    FROM dw.fact_student_week w JOIN e USING (student_key, offering_key)
    WHERE w.snapshot_day_key = %(cutoff)s
)
"""
WEEK_METRICS = """
    count(*) AS enrollments,
    round(avg(clicks_week), 2) AS avg_clicks,
    count(*) FILTER (WHERE clicks_week = 0) AS zero_click,
    round(100.0 * count(*) FILTER (WHERE clicks_week = 0) / nullif(count(*), 0), 2) AS zero_click_pct,
    round(avg(missed_cum), 2) AS avg_missed,
    count(*) FILTER (WHERE is_at_risk) AS at_risk,
    round(100.0 * count(*) FILTER (WHERE is_at_risk) / nullif(count(*), 0), 2) AS risk_pct
"""
ASSESSMENT_METRICS = """
    count(f.assessment_key) AS records,
    count(f.assessment_key) FILTER (WHERE f.is_banked) AS banked,
    count(f.score) AS scored, round(avg(f.score), 2) AS avg_score,
    count(f.assessment_key) FILTER (WHERE f.score < 40) AS below_40,
    round(100.0 * count(f.assessment_key) FILTER (WHERE f.score < 40)
          / nullif(count(f.score), 0), 2) AS below_40_pct,
    count(f.assessment_key) FILTER (
        WHERE a.assessment_type IN ('TMA', 'CMA') AND NOT f.is_banked AND f.is_late IS NOT NULL
    ) AS eligible_late,
    count(f.assessment_key) FILTER (
        WHERE a.assessment_type IN ('TMA', 'CMA') AND NOT f.is_banked AND f.is_late IS TRUE
    ) AS late,
    round(100.0 * count(f.assessment_key) FILTER (
        WHERE a.assessment_type IN ('TMA', 'CMA') AND NOT f.is_banked AND f.is_late IS TRUE
    ) / nullif(count(f.assessment_key) FILTER (
        WHERE a.assessment_type IN ('TMA', 'CMA') AND NOT f.is_banked AND f.is_late IS NOT NULL
    ), 0), 2) AS late_pct
"""


def rows(conn, query, params=None):
    # A cursor-local factory leaves warehouse_reader's tuple-based API unchanged.
    with conn.cursor(row_factory=dict_row) as cursor:
        return cursor.execute(query, params).fetchall()


def offerings(conn):
    return rows(conn, 'SELECT offering_key, domain, code_module, code_presentation, length_weeks '
                'FROM dw.dim_offering ORDER BY domain, code_module, code_presentation')


def overview(conn, params):
    summary = rows(conn, COHORT + 'SELECT ' + ENROLLMENT_METRICS + ' FROM e', params)[0]
    rollup = rows(conn, COHORT + 'SELECT domain, code_module, code_presentation, '
                  'GROUPING(domain, code_module, code_presentation) AS grouping, '
                  + ENROLLMENT_METRICS + ' FROM e '
                  'GROUP BY ROLLUP(domain, code_module, code_presentation) '
                  'ORDER BY domain NULLS FIRST, code_module NULLS FIRST, code_presentation NULLS FIRST', params)
    breakdowns = {}
    # Identifiers are code-owned allowlists, never interpolated user values.
    for name, field, order in (
        ('imd', 'imd_band', 'min(imd_order) NULLS LAST, imd_band'),
        ('education', 'highest_education', 'highest_education'),
        ('disability', 'disability', 'disability'),
    ):
        breakdowns[name] = rows(conn, COHORT + f'SELECT {field} AS label, ' + ENROLLMENT_METRICS
                                + f' FROM e GROUP BY {field} ORDER BY {order}', params)
    attempts = rows(conn, COHORT + 'SELECT least(num_prev_attempts, 2) AS previous_attempts, '
                    + ENROLLMENT_METRICS + ' FROM e GROUP BY 1 ORDER BY 1', params)
    return {'summary': summary, 'rollup': rollup, 'breakdowns': breakdowns, 'attempts': attempts}


def registration(conn, params):
    summary = rows(conn, COHORT + 'SELECT ' + ENROLLMENT_METRICS + """,
        count(*) FILTER (WHERE unregistration_day_key > -9000) AS known_unregistration,
        count(*) FILTER (WHERE unregistration_day_key = -9999) AS unknown_unregistration,
        count(*) FILTER (WHERE unregistration_day_key = -9998) AS na_unregistration
        FROM e""", params)[0]
    cancellations = rows(conn, COHORT + """, bucketed AS (
        SELECT CASE WHEN unregistration_day_key < 0 THEN '1. Trước khai giảng'
                    WHEN unregistration_day_key = 0 THEN '2. Ngày 0'
                    WHEN unregistration_day_key < 28 THEN '3. Ngày 1–27'
                    WHEN unregistration_day_key < 84 THEN '4. Ngày 28–83'
                    ELSE '5. Ngày 84 trở đi' END AS phase
        FROM e WHERE unregistration_day_key > -9000
    ) SELECT phase, count(*) AS enrollments,
        round(100.0 * count(*) / nullif(sum(count(*)) OVER (), 0), 2) AS share_pct
      FROM bucketed GROUP BY phase ORDER BY phase""", params)
    registrations = rows(conn, COHORT + """, bucketed AS (
        SELECT e.*, CASE WHEN registration_day_key = -9999 THEN '5. Không rõ'
                    WHEN registration_day_key = -9998 THEN '6. Không áp dụng'
                    WHEN registration_day_key <= -90 THEN '1. Trước từ 90 ngày'
                    WHEN registration_day_key <= -30 THEN '2. Trước 30–89 ngày'
                    WHEN registration_day_key < 0 THEN '3. Trước 1–29 ngày'
                    ELSE '4. Ngày 0 hoặc sau' END AS phase FROM e
    ) SELECT phase, """ + ENROLLMENT_METRICS + ' FROM bucketed GROUP BY phase ORDER BY phase', params)
    return {'summary': summary, 'cancellations': cancellations, 'registrations': registrations}


def engagement(conn, params):
    summary = rows(conn, WEEK_COHORT + 'SELECT ' + WEEK_METRICS + ' FROM w', params)[0]
    outcomes = rows(conn, WEEK_COHORT + 'SELECT final_result, ' + WEEK_METRICS
                    + ' FROM w GROUP BY final_result ORDER BY final_result', params)
    activity = rows(conn, """
        WITH activity AS (
            SELECT activity_group, activity_type, sum(total_clicks) AS clicks
            FROM dw.agg_vle_offering_week_activity
            WHERE offering_key = ANY(%(offering_keys)s::smallint[]) AND week_no = %(week)s
            GROUP BY activity_group, activity_type
        ) SELECT activity_group, activity_type, GROUPING(activity_type) AS grouping,
                 sum(clicks) AS clicks,
                 round(100.0 * sum(clicks) / nullif((SELECT sum(clicks) FROM activity), 0), 2) AS share_pct
          FROM activity GROUP BY GROUPING SETS ((activity_group), (activity_group, activity_type))
          ORDER BY activity_group, activity_type NULLS FIRST
    """, params)
    # Weeks every selected offering reaches, so a line never changes cohort mid-way.
    trend = rows(conn, COHORT + """
        SELECT (w.snapshot_day_key - 6) / 7 AS week_no, e.final_result, count(*) AS enrollments,
               round(avg(w.clicks_week), 2) AS avg_clicks
        FROM dw.fact_student_week w JOIN e USING (student_key, offering_key)
        WHERE w.snapshot_day_key < (SELECT 7 * min(length_weeks) FROM selected)
        GROUP BY 1, 2 HAVING count(*) >= 20 ORDER BY 1, 2""", params)
    return {'summary': summary, 'outcomes': outcomes, 'activity': activity, 'trend': trend}


def assessments(conn, params):
    base = COHORT + """, a AS (
        SELECT a.* FROM dw.dim_assessment a JOIN selected o USING (offering_key)
    ) """
    joined = (' FROM a LEFT JOIN dw.fact_assessment f ON f.assessment_key = a.assessment_key '
              'AND f.offering_key = a.offering_key ')
    by_type = rows(conn, base + 'SELECT a.assessment_type, count(DISTINCT a.assessment_key) AS assessments, '
                   + ASSESSMENT_METRICS + joined + 'GROUP BY a.assessment_type ORDER BY a.assessment_type', params)
    detail = rows(conn, base + """
        SELECT a.id_assessment, o.code_module, o.code_presentation, a.assessment_type,
               a.effective_due_day, a.is_due_estimated, a.is_formative, a.has_recorded_results,
               a.weight, n.enrollments,
    """ + ASSESSMENT_METRICS + """,
        round(100.0 * count(f.assessment_key) / nullif(n.enrollments, 0), 2) AS record_pct
    """ + joined + """
        JOIN selected o ON o.offering_key = a.offering_key
        JOIN (SELECT o.offering_key, count(e.student_key) AS enrollments
              FROM selected o LEFT JOIN e ON e.offering_key = o.offering_key
              GROUP BY o.offering_key) n ON n.offering_key = a.offering_key
        GROUP BY a.assessment_key, a.id_assessment, o.code_module, o.code_presentation,
                 a.assessment_type, a.effective_due_day, a.is_due_estimated, a.is_formative,
                 a.has_recorded_results, a.weight, n.enrollments
        ORDER BY o.code_module, o.code_presentation, a.effective_due_day, a.id_assessment
    """, params)
    return {'by_type': by_type, 'detail': detail}


def signals(conn, params):
    summary = rows(conn, WEEK_COHORT + 'SELECT ' + WEEK_METRICS + ' FROM w', params)[0]
    buckets = rows(conn, WEEK_COHORT + 'SELECT least(missed_cum, 2) AS missed_bucket, '
                   + WEEK_METRICS + ' FROM w GROUP BY 1 ORDER BY 1', params)
    return {'summary': summary, 'buckets': buckets}


LOADERS = {
    'overview': overview,
    'registration': registration,
    'engagement': engagement,
    'assessments': assessments,
    'signals': signals,
}
