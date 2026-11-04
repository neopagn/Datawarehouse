-- SQL mẫu cho job J03: dim_student với SCD type 2. Mỗi cặp (id_student, age_band) là một phiên bản.
INSERT INTO dw.dim_student (student_key, id_student, version_no, gender, region, highest_education, imd_band, imd_order, age_band, disability, valid_from_presentation, valid_to_presentation, is_current)
WITH clean AS (
    SELECT id_student::int AS id_student, gender, region, highest_education,
           CASE WHEN NULLIF(imd_band, '') IS NULL THEN 'Unknown'
                WHEN imd_band = '10-20' THEN '10-20%'
                ELSE imd_band END AS imd_band,
           age_band, disability, code_presentation,
           array_position(ARRAY['0-35', '35-55', '55<='], age_band) AS age_order
    FROM staging.student_info
), versions AS (
    SELECT id_student, gender, region, highest_education, imd_band, age_band, disability, age_order,
           MIN(code_presentation) AS first_presentation,   -- chuỗi 2013B < 2013J < 2014B < 2014J đúng thứ tự thời gian
           MAX(code_presentation) AS last_presentation
    FROM clean
    GROUP BY id_student, gender, region, highest_education, imd_band, age_band, disability, age_order
)
SELECT (ROW_NUMBER() OVER (ORDER BY id_student, age_order))::int AS student_key,
       id_student,
       (ROW_NUMBER() OVER (PARTITION BY id_student ORDER BY age_order))::smallint AS version_no,
       gender, region, highest_education, imd_band,
       array_position(ARRAY['0-10%', '10-20%', '20-30%', '30-40%', '40-50%', '50-60%',
                            '60-70%', '70-80%', '80-90%', '90-100%'], imd_band)::smallint AS imd_order,
       age_band, disability,
       first_presentation AS valid_from_presentation,
       last_presentation AS valid_to_presentation,
       age_order = MAX(age_order) OVER (PARTITION BY id_student) AS is_current
FROM versions;
