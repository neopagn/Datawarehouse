-- Aggregate each transaction fact to enrollment BEFORE joining, avoiding fan-out.
-- Deliberately retains prototype weighted_points-based aggregation for team compatibility.
INSERT INTO dw.fact_enrollment
WITH activity AS (
    SELECT student_key, offering_key, sum(sum_click)::int AS clicks,
           count(DISTINCT day_key)::smallint AS days,
           min(day_key) AS first_day, max(day_key) AS last_day
    FROM dw.fact_vle_daily GROUP BY student_key, offering_key
), coursework AS (
    SELECT f.student_key, f.offering_key,
           count(*) FILTER (WHERE NOT f.is_banked)::smallint AS submitted,
           count(*) FILTER (WHERE f.is_banked)::smallint AS banked,
           round(avg(f.score), 2) AS avg_score,
           round(sum(f.weighted_points) * 100 /
                 nullif(sum(a.weight) FILTER (WHERE f.score IS NOT NULL), 0), 2) AS weighted_score
    FROM dw.fact_assessment f
    JOIN dw.dim_assessment a ON a.assessment_key = f.assessment_key
    WHERE a.assessment_type <> 'Exam'
    GROUP BY f.student_key, f.offering_key
)
SELECT s.student_key, o.offering_key, result.result_key,
       coalesce(NULLIF(r.date_registration, '')::int, -9999),
       coalesce(NULLIF(r.date_unregistration, '')::int,
                CASE WHEN i.final_result = 'Withdrawn' THEN -9999 ELSE -9998 END),
       coalesce(v.first_day, -9998), coalesce(v.last_day, -9998), 1,
       NULLIF(i.studied_credits, '')::smallint, NULLIF(i.num_of_prev_attempts, '')::smallint,
       coalesce(v.clicks, 0), coalesce(v.days, 0), coalesce(c.submitted, 0), coalesce(c.banked, 0),
       c.avg_score, c.weighted_score,
       (i.final_result = 'Withdrawn' AND NULLIF(r.date_unregistration, '') IS NULL)
       OR (i.final_result = 'Fail' AND NULLIF(r.date_unregistration, '') IS NOT NULL)
FROM staging.student_info i
JOIN staging.student_registration r USING (code_module, code_presentation, id_student)
JOIN dw.dim_offering o USING (code_module, code_presentation)
JOIN dw.dim_student s ON s.id_student = i.id_student::int AND s.age_band = i.age_band
JOIN dw.dim_result result ON result.final_result = i.final_result
LEFT JOIN activity v ON v.student_key = s.student_key AND v.offering_key = o.offering_key
LEFT JOIN coursework c ON c.student_key = s.student_key AND c.offering_key = o.offering_key;
