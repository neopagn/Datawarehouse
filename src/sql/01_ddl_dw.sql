-- Kho dữ liệu OULAD: galaxy schema gồm 6 bảng chiều dùng chung và 4 bảng fact.
-- Số dòng ghi trong chú thích là số đã kiểm chứng trên dữ liệu thật (xem docs/validation_output.txt).

CREATE SCHEMA IF NOT EXISTS dw;

DROP MATERIALIZED VIEW IF EXISTS dw.agg_vle_offering_week_activity;
DROP TABLE IF EXISTS dw.fact_student_week, dw.fact_vle_daily, dw.fact_assessment, dw.fact_enrollment,
    dw.dim_vle_site, dw.dim_assessment, dw.dim_result, dw.dim_day, dw.dim_offering, dw.dim_student;

-- ===== BẢNG CHIỀU =====

-- 28.857 dòng / 28.785 sinh viên. SCD type 2, chỉ age_band thực sự thay đổi (72 sinh viên).
-- Đếm sinh viên phải dùng COUNT(DISTINCT id_student), không đếm student_key.
CREATE TABLE dw.dim_student (
    student_key             INT PRIMARY KEY,
    id_student              INT NOT NULL,
    version_no              SMALLINT NOT NULL,
    gender                  VARCHAR(1) NOT NULL,
    region                  VARCHAR(30) NOT NULL,
    highest_education       VARCHAR(30) NOT NULL,
    imd_band                VARCHAR(10) NOT NULL,      -- 'Unknown' khi thiếu; đã sửa '10-20' thành '10-20%'
    imd_order               SMALLINT,                  -- 1 = nhóm nghèo nhất (0-10%), NULL khi Unknown
    age_band                VARCHAR(5) NOT NULL,
    disability              VARCHAR(1) NOT NULL,
    valid_from_presentation VARCHAR(5) NOT NULL,
    valid_to_presentation   VARCHAR(5) NOT NULL,
    is_current              BOOLEAN NOT NULL,
    UNIQUE (id_student, version_no),
    UNIQUE (id_student, age_band)                      -- khóa tra cứu khi nạp fact
);

-- 22 dòng. Một lần mở module, ví dụ DDD-2013J. Độ dài khóa phụ thuộc cả cặp nên gộp vào một chiều.
CREATE TABLE dw.dim_offering (
    offering_key      SMALLINT PRIMARY KEY,
    code_module       VARCHAR(3) NOT NULL,
    domain            VARCHAR(20) NOT NULL,            -- Bảng 1 trong paper OULAD, không có trong CSV
    code_presentation VARCHAR(5) NOT NULL,
    start_year        SMALLINT NOT NULL,
    start_month       SMALLINT NOT NULL,               -- B = tháng 2, J = tháng 10
    length_days       SMALLINT NOT NULL,
    length_weeks      SMALLINT NOT NULL,
    UNIQUE (code_module, code_presentation)
);

-- 976 dòng: ngày -365..608 và 2 dòng đặc biệt. Ngày trong OULAD là số ngày tính từ khai giảng,
-- nên chiều này không chứa ngày lịch. day_key = day_no với ngày thường.
CREATE TABLE dw.dim_day (
    day_key        INT PRIMARY KEY,                    -- -9998 = Không áp dụng, -9999 = Không rõ
    day_no         INT,
    week_no        INT,                                -- FLOOR(day_no / 7)
    block_no       INT,                                -- FLOOR(day_no / 28), mức roll-up trên tuần
    course_phase   VARCHAR(20) NOT NULL,               -- Before start / After start / Not applicable / Unknown
    CHECK ((day_key < -9000) = (day_no IS NULL))
);

-- 4 dòng.
CREATE TABLE dw.dim_result (
    result_key    SMALLINT PRIMARY KEY,
    final_result  VARCHAR(12) NOT NULL UNIQUE,
    outcome_group VARCHAR(12) NOT NULL,                -- Successful / At risk
    is_at_risk    BOOLEAN NOT NULL,
    result_order  SMALLINT NOT NULL
);

-- 206 dòng. Giữ offering_key vì 18 bài thi không có lượt nộp nào nên không xuất hiện trong fact.
CREATE TABLE dw.dim_assessment (
    assessment_key       INT PRIMARY KEY,
    id_assessment        INT NOT NULL UNIQUE,
    offering_key         SMALLINT NOT NULL REFERENCES dw.dim_offering,
    assessment_type      VARCHAR(4) NOT NULL CHECK (assessment_type IN ('TMA', 'CMA', 'Exam')),
    weight               NUMERIC(5,2) NOT NULL,
    due_day              SMALLINT,                     -- giữ nguyên nguồn, NULL ở 11 bài thi
    effective_due_day    SMALLINT NOT NULL,            -- NULL thì lấy ngày cuối khóa (quy ước của paper)
    is_due_estimated     BOOLEAN NOT NULL,
    is_formative         BOOLEAN NOT NULL,             -- weight = 0 (56 bài)
    has_recorded_results BOOLEAN NOT NULL              -- FALSE ở 18 bài thi
);

-- 6.364 dòng. Giữ offering_key vì 96 tài nguyên chưa từng được click nên không xuất hiện trong fact.
CREATE TABLE dw.dim_vle_site (
    site_key          INT PRIMARY KEY,
    id_site           INT NOT NULL UNIQUE,
    offering_key      SMALLINT NOT NULL REFERENCES dw.dim_offering,
    activity_type     VARCHAR(20) NOT NULL,
    activity_group    VARCHAR(20) NOT NULL,            -- nhóm do nhóm tự đặt, xem tài liệu thiết kế
    planned_week_from SMALLINT,                        -- chỉ có ở 17,6% tài nguyên
    planned_week_to   SMALLINT
);

-- ===== BẢNG FACT =====

-- Mỗi dòng: 1 sinh viên x 1 lần mở module. 32.593 dòng. Accumulating snapshot.
-- studied_credits là tổng tín chỉ của sinh viên trong kỳ, KHÔNG được SUM.
CREATE TABLE dw.fact_enrollment (
    student_key               INT NOT NULL REFERENCES dw.dim_student,
    offering_key              SMALLINT NOT NULL REFERENCES dw.dim_offering,
    result_key                SMALLINT NOT NULL REFERENCES dw.dim_result,
    registration_day_key      INT NOT NULL REFERENCES dw.dim_day,
    unregistration_day_key    INT NOT NULL REFERENCES dw.dim_day,
    first_active_day_key      INT NOT NULL REFERENCES dw.dim_day,
    last_active_day_key       INT NOT NULL REFERENCES dw.dim_day,
    enrollment_count          SMALLINT NOT NULL DEFAULT 1,
    studied_credits           SMALLINT NOT NULL,
    num_prev_attempts         SMALLINT NOT NULL,
    total_clicks              INT NOT NULL,
    active_days               SMALLINT NOT NULL,
    submitted_count           SMALLINT NOT NULL,       -- không tính bài banked và bài thi
    banked_count              SMALLINT NOT NULL,
    avg_coursework_score      NUMERIC(5,2),            -- TMA + CMA có điểm, kể cả banked
    weighted_coursework_score NUMERIC(5,2),            -- NULL khi không có bài có trọng số (toàn bộ GGG, hoặc chưa nộp bài nào)
    has_status_conflict       BOOLEAN NOT NULL,        -- Withdrawn không có ngày hủy, hoặc Fail có ngày hủy
    PRIMARY KEY (student_key, offering_key)
);

-- Mỗi dòng: 1 sinh viên x 1 bài. 173.912 dòng. Transaction.
CREATE TABLE dw.fact_assessment (
    student_key             INT NOT NULL REFERENCES dw.dim_student,
    offering_key            SMALLINT NOT NULL REFERENCES dw.dim_offering,
    assessment_key          INT NOT NULL REFERENCES dw.dim_assessment,
    submitted_day_key       INT NOT NULL REFERENCES dw.dim_day,   -- -9998 với bài banked (nguồn ghi -1)
    score                   SMALLINT CHECK (score BETWEEN 0 AND 100),  -- trung bình được, không SUM
    weighted_points         NUMERIC(6,2),              -- score * weight / 100
    days_late               SMALLINT,                  -- NULL với bài banked và bài thi
    is_late                 BOOLEAN,
    is_banked               BOOLEAN NOT NULL,
    is_after_unregistration BOOLEAN NOT NULL,
    PRIMARY KEY (student_key, assessment_key)
);

-- Mỗi dòng: 1 sinh viên x 1 tài nguyên x 1 ngày. 8.459.320 dòng, gộp từ 10.655.280 dòng nguồn.
CREATE TABLE dw.fact_vle_daily (
    student_key             INT NOT NULL REFERENCES dw.dim_student,
    offering_key            SMALLINT NOT NULL REFERENCES dw.dim_offering,
    site_key                INT NOT NULL REFERENCES dw.dim_vle_site,
    day_key                 INT NOT NULL REFERENCES dw.dim_day,
    sum_click               INT NOT NULL CHECK (sum_click > 0),
    source_rows             SMALLINT NOT NULL,         -- số dòng nguồn đã gộp
    is_after_unregistration BOOLEAN NOT NULL,
    PRIMARY KEY (student_key, site_key, day_key)
);
CREATE INDEX idx_vle_offering_day ON dw.fact_vle_daily (offering_key, day_key);
CREATE INDEX idx_vle_site ON dw.fact_vle_daily (site_key);

-- Mỗi dòng: 1 sinh viên còn đăng ký vào cuối 1 tuần của khóa. 920.734 dòng. Periodic snapshot, đầu vào của DSS.
-- Có cả tuần không hoạt động. Cố ý không chứa kết quả cuối khóa để tránh rò rỉ nhãn.
-- Các cột *_cum là semi-additive: không SUM theo thời gian.
CREATE TABLE dw.fact_student_week (
    student_key              INT NOT NULL REFERENCES dw.dim_student,
    offering_key             SMALLINT NOT NULL REFERENCES dw.dim_offering,
    snapshot_day_key         INT NOT NULL REFERENCES dw.dim_day,   -- ngày cuối tuần: 7w + 6
    clicks_week              INT NOT NULL,
    active_days_week         SMALLINT NOT NULL,
    clicks_cum               INT NOT NULL,             -- có tính click trước khai giảng
    active_days_cum          SMALLINT NOT NULL,
    days_since_last_activity SMALLINT,                 -- NULL nếu chưa từng hoạt động
    submitted_cum            SMALLINT NOT NULL,
    due_cum                  SMALLINT NOT NULL,        -- số TMA + CMA đã đến hạn
    missed_cum               SMALLINT NOT NULL,        -- đã đến hạn mà chưa nộp vào thời điểm snapshot
    avg_score_cum            NUMERIC(5,2),             -- không tính banked
    PRIMARY KEY (student_key, offering_key, snapshot_day_key)
);
CREATE INDEX idx_week_offering_day ON dw.fact_student_week (offering_key, snapshot_day_key);

-- ===== BẢNG TỔNG HỢP =====

-- 8.436 dòng, để dashboard không phải quét fact_vle_daily.
CREATE MATERIALIZED VIEW dw.agg_vle_offering_week_activity AS
SELECT f.offering_key, d.week_no, s.activity_group, s.activity_type,
       SUM(f.sum_click) AS total_clicks,
       COUNT(*) AS interaction_rows
FROM dw.fact_vle_daily f
JOIN dw.dim_day d ON d.day_key = f.day_key
JOIN dw.dim_vle_site s ON s.site_key = f.site_key
GROUP BY f.offering_key, d.week_no, s.activity_group, s.activity_type
WITH NO DATA;
