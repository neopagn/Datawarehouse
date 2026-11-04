-- Vùng staging: giữ nguyên dữ liệu gốc dưới dạng TEXT, chưa làm sạch gì.
-- Nạp bằng: COPY staging.<bảng> FROM '<file>.csv' WITH (FORMAT csv, HEADER true);
-- Chú ý: file nguồn ghi giá trị thiếu là "" có dấu nháy nên COPY giữ thành chuỗi rỗng, kể cả khi đặt NULL ''.
-- Khi đổi kiểu dữ liệu phải dùng NULLIF(cot, '')::int, nếu không câu lệnh sẽ báo lỗi.

CREATE SCHEMA IF NOT EXISTS staging;

DROP TABLE IF EXISTS staging.courses, staging.assessments, staging.vle, staging.student_info,
    staging.student_registration, staging.student_assessment, staging.student_vle;

CREATE TABLE staging.courses (
    code_module TEXT, code_presentation TEXT, module_presentation_length TEXT
);

CREATE TABLE staging.assessments (
    code_module TEXT, code_presentation TEXT, id_assessment TEXT,
    assessment_type TEXT, date TEXT, weight TEXT
);

CREATE TABLE staging.vle (
    id_site TEXT, code_module TEXT, code_presentation TEXT,
    activity_type TEXT, week_from TEXT, week_to TEXT
);

CREATE TABLE staging.student_info (
    code_module TEXT, code_presentation TEXT, id_student TEXT, gender TEXT, region TEXT,
    highest_education TEXT, imd_band TEXT, age_band TEXT, num_of_prev_attempts TEXT,
    studied_credits TEXT, disability TEXT, final_result TEXT
);

CREATE TABLE staging.student_registration (
    code_module TEXT, code_presentation TEXT, id_student TEXT,
    date_registration TEXT, date_unregistration TEXT
);

CREATE TABLE staging.student_assessment (
    id_assessment TEXT, id_student TEXT, date_submitted TEXT, is_banked TEXT, score TEXT
);

CREATE TABLE staging.student_vle (
    code_module TEXT, code_presentation TEXT, id_student TEXT,
    id_site TEXT, date TEXT, sum_click TEXT
);
