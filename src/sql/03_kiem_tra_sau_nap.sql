-- Bài kiểm tra sau khi nạp (job J13). Mọi dòng phải có passed = true, nếu không thì ETL sai.
-- Số mong đợi lấy từ docs/profiling_output.txt và docs/validation_output.txt.

SELECT check_name, expected, actual, expected = actual AS passed
FROM (
    SELECT 'staging.student_vle: so dong' AS check_name, 10655280::bigint AS expected, (SELECT count(*) FROM staging.student_vle) AS actual
    UNION ALL SELECT 'fact_vle_daily: tong source_rows', 10655280, (SELECT sum(source_rows::bigint) FROM dw.fact_vle_daily)
    UNION ALL SELECT 'staging.student_vle: tong click', 39605099, (SELECT sum(sum_click::bigint) FROM staging.student_vle)
    UNION ALL SELECT 'fact_vle_daily: tong click', 39605099, (SELECT sum(sum_click::bigint) FROM dw.fact_vle_daily)
    UNION ALL SELECT 'fact_enrollment: tong click', 39605099, (SELECT sum(total_clicks::bigint) FROM dw.fact_enrollment)
    UNION ALL SELECT 'agg_vle: tong click', 39605099, (SELECT sum(total_clicks)::bigint FROM dw.agg_vle_offering_week_activity)
    UNION ALL SELECT 'dim_student: so dong', 28857, (SELECT count(*) FROM dw.dim_student)
    UNION ALL SELECT 'dim_student: so sinh vien', 28785, (SELECT count(DISTINCT id_student) FROM dw.dim_student)
    UNION ALL SELECT 'dim_offering: so dong', 22, (SELECT count(*) FROM dw.dim_offering)
    UNION ALL SELECT 'dim_day: so dong', 976, (SELECT count(*) FROM dw.dim_day)
    UNION ALL SELECT 'dim_result: so dong', 4, (SELECT count(*) FROM dw.dim_result)
    UNION ALL SELECT 'dim_assessment: so dong', 206, (SELECT count(*) FROM dw.dim_assessment)
    UNION ALL SELECT 'dim_vle_site: so dong', 6364, (SELECT count(*) FROM dw.dim_vle_site)
    UNION ALL SELECT 'fact_enrollment: so dong', 32593, (SELECT count(*) FROM dw.fact_enrollment)
    UNION ALL SELECT 'fact_assessment: so dong', 173912, (SELECT count(*) FROM dw.fact_assessment)
    UNION ALL SELECT 'fact_vle_daily: so dong', 8459320, (SELECT count(*) FROM dw.fact_vle_daily)
    UNION ALL SELECT 'fact_student_week: so dong', 920734, (SELECT count(*) FROM dw.fact_student_week)
    UNION ALL SELECT 'agg_vle: so dong', 8436, (SELECT count(*) FROM dw.agg_vle_offering_week_activity)
    UNION ALL SELECT 'fact_assessment: co diem', 173739, (SELECT count(score) FROM dw.fact_assessment)
    UNION ALL SELECT 'fact_assessment: banked', 1909, (SELECT count(*) FROM dw.fact_assessment WHERE is_banked)
    UNION ALL SELECT 'fact_assessment: sau khi huy', 601, (SELECT count(*) FROM dw.fact_assessment WHERE is_after_unregistration)
    UNION ALL SELECT 'fact_assessment: nop tre', 49311, (SELECT count(*) FROM dw.fact_assessment WHERE is_late)
    UNION ALL SELECT 'fact_vle_daily: click sau khi huy', 98745, (SELECT coalesce(sum(sum_click), 0) FROM dw.fact_vle_daily WHERE is_after_unregistration)
    UNION ALL SELECT 'fact_enrollment: mau thuan trang thai', 102, (SELECT count(*) FROM dw.fact_enrollment WHERE has_status_conflict)
    UNION ALL SELECT 'fact_enrollment: khong ro ngay dang ky', 45, (SELECT count(*) FROM dw.fact_enrollment WHERE registration_day_key = -9999)
    UNION ALL SELECT 'fact_enrollment: khong ro ngay huy', 93, (SELECT count(*) FROM dw.fact_enrollment WHERE unregistration_day_key = -9999)
    UNION ALL SELECT 'fact_enrollment: khong co hoat dong VLE', 3365, (SELECT count(*) FROM dw.fact_enrollment WHERE first_active_day_key = -9998)
    UNION ALL SELECT 'fact_student_week: missed_cum > due_cum', 0, (SELECT count(*) FROM dw.fact_student_week WHERE missed_cum > due_cum)
    UNION ALL SELECT 'fact_student_week: dong sau ngay huy', 0,
        (SELECT count(*) FROM dw.fact_student_week w
         JOIN dw.fact_enrollment f ON f.student_key = w.student_key AND f.offering_key = w.offering_key
         WHERE f.unregistration_day_key > -9000 AND w.snapshot_day_key >= f.unregistration_day_key)
) AS checks
ORDER BY passed, check_name;
