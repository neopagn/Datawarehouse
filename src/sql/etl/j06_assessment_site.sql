INSERT INTO dw.dim_assessment
SELECT row_number() OVER (ORDER BY a.id_assessment::int)::int,
       a.id_assessment::int, o.offering_key, a.assessment_type,
       NULLIF(a.weight, '')::numeric, NULLIF(a.date, '')::smallint,
       coalesce(NULLIF(a.date, '')::smallint, o.length_days),
       NULLIF(a.date, '') IS NULL, NULLIF(a.weight, '')::numeric = 0,
       EXISTS (SELECT 1 FROM staging.student_assessment s WHERE s.id_assessment = a.id_assessment)
FROM staging.assessments a
JOIN dw.dim_offering o USING (code_module, code_presentation);

INSERT INTO dw.dim_vle_site
SELECT row_number() OVER (ORDER BY v.id_site::int)::int,
       v.id_site::int, o.offering_key, v.activity_type,
       CASE WHEN v.activity_type IN ('oucontent', 'resource', 'subpage', 'page', 'url',
                 'dualpane', 'folder', 'htmlactivity', 'sharedsubpage', 'repeatactivity', 'glossary') THEN 'Content'
            WHEN v.activity_type IN ('forumng', 'ouwiki', 'oucollaborate', 'ouelluminate', 'dataplus') THEN 'Collaboration'
            WHEN v.activity_type IN ('quiz', 'externalquiz', 'questionnaire') THEN 'Practice'
            WHEN v.activity_type = 'homepage' THEN 'Navigation' END,
       NULLIF(v.week_from, '')::smallint, NULLIF(v.week_to, '')::smallint
FROM staging.vle v
JOIN dw.dim_offering o USING (code_module, code_presentation);
