-- Compatibility with the handed-over prototype: banked -1 is used ONLY for
-- the legacy after-unregistration flag; it is never treated as a real submitted day.
INSERT INTO dw.fact_assessment
WITH submissions AS (
    SELECT s.student_key, a.offering_key, a.assessment_key,
           NULLIF(sa.date_submitted, '')::int AS submitted_day,
           NULLIF(sa.score, '')::smallint AS score,
           NULLIF(sa.is_banked, '')::int = 1 AS banked,
           NULLIF(r.date_unregistration, '')::int AS unreg_day,
           a.weight, a.effective_due_day, a.assessment_type
    FROM staging.student_assessment sa
    JOIN dw.dim_assessment a ON a.id_assessment = sa.id_assessment::int
    JOIN dw.dim_offering o ON o.offering_key = a.offering_key
    JOIN staging.student_info i ON i.id_student = sa.id_student
         AND i.code_module = o.code_module AND i.code_presentation = o.code_presentation
    JOIN staging.student_registration r ON r.code_module = i.code_module
         AND r.code_presentation = i.code_presentation AND r.id_student = i.id_student
    JOIN dw.dim_student s ON s.id_student = i.id_student::int AND s.age_band = i.age_band
), measured AS (
    SELECT *, CASE WHEN NOT banked AND assessment_type <> 'Exam'
                   THEN submitted_day - effective_due_day END AS late
    FROM submissions
)
SELECT student_key, offering_key, assessment_key,
       CASE WHEN banked THEN -9998 ELSE submitted_day END,
       score,
       -- Preserve prototype ties-to-even rounding for intermediate weighted points.
       CASE WHEN mod(score * weight, 1) = 0.5 AND mod(floor(score * weight), 2) = 0
            THEN floor(score * weight) / 100 ELSE round(score * weight / 100, 2) END,
       late::smallint, late > 0,
       banked, coalesce(submitted_day > unreg_day, false)
FROM measured;
