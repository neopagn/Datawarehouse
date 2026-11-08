-- Small source keys: uniqueness protects all subsequent enrollment lookups.
CREATE UNIQUE INDEX stg_course_key ON staging.courses (code_module, code_presentation);
CREATE UNIQUE INDEX stg_info_key ON staging.student_info (code_module, code_presentation, id_student);
CREATE UNIQUE INDEX stg_registration_key ON staging.student_registration (code_module, code_presentation, id_student);
CREATE UNIQUE INDEX stg_assessment_key ON staging.assessments (id_assessment);
CREATE UNIQUE INDEX stg_site_key ON staging.vle (id_site);
CREATE UNIQUE INDEX stg_submission_key ON staging.student_assessment (id_assessment, id_student);
ANALYZE staging.courses;
ANALYZE staging.assessments;
ANALYZE staging.vle;
ANALYZE staging.student_info;
ANALYZE staging.student_registration;
ANALYZE staging.student_assessment;
ANALYZE staging.student_vle;
