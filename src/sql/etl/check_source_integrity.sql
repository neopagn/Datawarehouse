-- Zero violations required. Run inside J02 before transformation/inner joins.
SELECT check_name, 0::bigint AS expected, actual, actual = 0 AS passed FROM (
SELECT 'source: info without registration' AS check_name, count(*) AS actual
FROM staging.student_info i LEFT JOIN staging.student_registration r USING (code_module, code_presentation, id_student)
WHERE r.id_student IS NULL
UNION ALL SELECT 'source: registration without info', count(*)
FROM staging.student_registration r LEFT JOIN staging.student_info i USING (code_module, code_presentation, id_student)
WHERE i.id_student IS NULL
UNION ALL SELECT 'source: info without course', count(*)
FROM staging.student_info i LEFT JOIN staging.courses c USING (code_module, code_presentation)
WHERE c.code_module IS NULL
UNION ALL SELECT 'source: assessment without course', count(*)
FROM staging.assessments a LEFT JOIN staging.courses c USING (code_module, code_presentation)
WHERE c.code_module IS NULL
UNION ALL SELECT 'source: site without course', count(*)
FROM staging.vle v LEFT JOIN staging.courses c USING (code_module, code_presentation)
WHERE c.code_module IS NULL
UNION ALL SELECT 'source: submission without enrollment', count(*)
FROM staging.student_assessment s
LEFT JOIN staging.assessments a ON a.id_assessment = s.id_assessment
LEFT JOIN staging.student_info i ON i.id_student = s.id_student
     AND i.code_module = a.code_module AND i.code_presentation = a.code_presentation
WHERE a.id_assessment IS NULL OR i.id_student IS NULL
UNION ALL SELECT 'source: VLE wrong offering or enrollment', count(*)
FROM staging.student_vle s
LEFT JOIN staging.vle v ON v.id_site = s.id_site AND v.code_module = s.code_module AND v.code_presentation = s.code_presentation
LEFT JOIN staging.student_info i ON i.code_module = s.code_module
     AND i.code_presentation = s.code_presentation AND i.id_student = s.id_student
WHERE v.id_site IS NULL OR i.id_student IS NULL
UNION ALL SELECT 'source: nonpositive clicks', count(*) FROM staging.student_vle
WHERE NULLIF(sum_click, '')::bigint IS NULL OR NULLIF(sum_click, '')::bigint <= 0
UNION ALL SELECT 'source: invalid banked flag', count(*) FROM staging.student_assessment
WHERE is_banked IS NULL OR is_banked NOT IN ('0', '1')
UNION ALL SELECT 'source: missing VLE day', count(*) FROM staging.student_vle
WHERE NULLIF(date, '') IS NULL
UNION ALL SELECT 'source: missing submission day', count(*) FROM staging.student_assessment
WHERE NULLIF(date_submitted, '') IS NULL
UNION ALL SELECT 'source: invalid age band', count(*) FROM staging.student_info
WHERE age_band IS NULL OR age_band NOT IN ('0-35', '35-55', '55<=')
UNION ALL SELECT 'source: invalid result', count(*) FROM staging.student_info
WHERE final_result IS NULL OR final_result NOT IN ('Distinction', 'Pass', 'Fail', 'Withdrawn')
UNION ALL SELECT 'source: invalid offering', count(*) FROM staging.courses
WHERE code_module IS NULL OR code_module NOT IN ('AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF', 'GGG')
   OR code_presentation IS NULL OR code_presentation !~ '^[0-9]{4}[BJ]$'
   OR NULLIF(module_presentation_length, '')::int IS NULL OR NULLIF(module_presentation_length, '')::int <= 0
) checks ORDER BY check_name;
