-- SQL mẫu cho job J08: gộp 10.655.280 dòng nguồn thành 8.459.320 dòng theo sinh viên x tài nguyên x ngày.
INSERT INTO dw.fact_vle_daily (student_key, offering_key, site_key, day_key, sum_click, source_rows, is_after_unregistration)
WITH enrollment AS (
    SELECT i.code_module, i.code_presentation, i.id_student,
           s.student_key, o.offering_key,
           NULLIF(r.date_unregistration, '')::int AS unreg_day
    FROM staging.student_info i
    JOIN staging.student_registration r USING (code_module, code_presentation, id_student)
    JOIN dw.dim_offering o USING (code_module, code_presentation)
    JOIN dw.dim_student s ON s.id_student = i.id_student::int AND s.age_band = i.age_band
)
SELECT e.student_key, e.offering_key, d.site_key,
       v.date::int AS day_key,
       SUM(v.sum_click::int)::int AS sum_click,
       COUNT(*)::smallint AS source_rows,
       COALESCE(v.date::int > e.unreg_day, FALSE) AS is_after_unregistration
FROM staging.student_vle v
JOIN enrollment e USING (code_module, code_presentation, id_student)
JOIN dw.dim_vle_site d ON d.id_site = v.id_site::int
GROUP BY e.student_key, e.offering_key, d.site_key, v.date::int, e.unreg_day;
