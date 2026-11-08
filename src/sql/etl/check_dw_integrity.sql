-- Dataset-independent reconciliations supplement, never replace, 29 baseline checks.
SELECT check_name, expected, actual, expected = actual AS passed FROM (
SELECT 'integrity: enrollment count' AS check_name,
       (SELECT count(*) FROM staging.student_info) AS expected,
       (SELECT count(*) FROM dw.fact_enrollment) AS actual
UNION ALL SELECT 'integrity: assessment count',
       (SELECT count(*) FROM staging.student_assessment), (SELECT count(*) FROM dw.fact_assessment)
UNION ALL SELECT 'integrity: source row conservation',
       (SELECT count(*) FROM staging.student_vle), (SELECT coalesce(sum(source_rows), 0)::bigint FROM dw.fact_vle_daily)
UNION ALL SELECT 'integrity: click conservation',
       (SELECT coalesce(sum(sum_click::bigint), 0)::bigint FROM staging.student_vle),
       (SELECT coalesce(sum(sum_click), 0)::bigint FROM dw.fact_vle_daily)
UNION ALL SELECT 'integrity: enrollment clicks',
       (SELECT coalesce(sum(sum_click), 0)::bigint FROM dw.fact_vle_daily),
       (SELECT coalesce(sum(total_clicks), 0)::bigint FROM dw.fact_enrollment)
UNION ALL SELECT 'integrity: aggregate clicks',
       (SELECT coalesce(sum(sum_click), 0)::bigint FROM dw.fact_vle_daily),
       (SELECT coalesce(sum(total_clicks), 0)::bigint FROM dw.agg_vle_offering_week_activity)
UNION ALL SELECT 'integrity: assessment offering or enrollment', 0, count(*)
FROM dw.fact_assessment f JOIN dw.dim_assessment a ON a.assessment_key = f.assessment_key
LEFT JOIN dw.fact_enrollment e ON e.student_key = f.student_key AND e.offering_key = f.offering_key
WHERE f.offering_key <> a.offering_key OR e.student_key IS NULL
UNION ALL SELECT 'integrity: VLE offering or enrollment', 0, count(*)
FROM dw.fact_vle_daily f JOIN dw.dim_vle_site s ON s.site_key = f.site_key
LEFT JOIN dw.fact_enrollment e ON e.student_key = f.student_key AND e.offering_key = f.offering_key
WHERE f.offering_key <> s.offering_key OR e.student_key IS NULL
UNION ALL SELECT 'integrity: student version', 0, count(*)
FROM dw.fact_enrollment e
JOIN dw.dim_student s ON s.student_key = e.student_key
JOIN dw.dim_offering o ON o.offering_key = e.offering_key
LEFT JOIN staging.student_info i ON i.id_student::int = s.id_student
     AND i.code_module = o.code_module AND i.code_presentation = o.code_presentation AND i.age_band = s.age_band
WHERE i.id_student IS NULL
UNION ALL SELECT 'integrity: snapshot outside cohort', 0, count(*)
FROM dw.fact_student_week w
LEFT JOIN dw.fact_enrollment e ON e.student_key = w.student_key AND e.offering_key = w.offering_key
JOIN dw.dim_offering o ON o.offering_key = w.offering_key
WHERE e.student_key IS NULL OR w.snapshot_day_key < 6
   OR (w.snapshot_day_key - 6) % 7 <> 0 OR w.snapshot_day_key > 7 * o.length_weeks - 1
   OR (e.registration_day_key > -9000 AND e.registration_day_key > w.snapshot_day_key)
   OR (e.unregistration_day_key > -9000 AND e.unregistration_day_key <= w.snapshot_day_key)
UNION ALL SELECT 'integrity: invalid snapshot measures', 0, count(*)
FROM dw.fact_student_week WHERE clicks_week < 0 OR clicks_cum < clicks_week
   OR active_days_week NOT BETWEEN 0 AND 7 OR active_days_cum < active_days_week
   OR missed_cum < 0 OR due_cum < missed_cum OR submitted_cum < 0 OR days_since_last_activity < 0
) checks ORDER BY check_name;
