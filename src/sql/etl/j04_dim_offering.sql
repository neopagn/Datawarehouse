INSERT INTO dw.dim_offering
SELECT row_number() OVER (ORDER BY code_module, code_presentation)::smallint,
       code_module,
       CASE WHEN code_module IN ('AAA', 'BBB', 'GGG') THEN 'Social Sciences'
            WHEN code_module IN ('CCC', 'DDD', 'EEE', 'FFF') THEN 'STEM' END,
       code_presentation, left(code_presentation, 4)::smallint,
       CASE right(code_presentation, 1) WHEN 'B' THEN 2 WHEN 'J' THEN 10 END,
       NULLIF(module_presentation_length, '')::smallint,
       ceil(NULLIF(module_presentation_length, '')::numeric / 7)::smallint
FROM staging.courses;
