-- SQL mẫu cho job J10: snapshot cuối mỗi tuần. Cần chạy sau fact_enrollment, fact_assessment, fact_vle_daily.
INSERT INTO dw.fact_student_week (student_key, offering_key, snapshot_day_key, clicks_week, active_days_week, clicks_cum, active_days_cum, days_since_last_activity, submitted_cum, due_cum, missed_cum, avg_score_cum)
WITH enrollment AS (
    SELECT f.student_key, f.offering_key, o.length_weeks,
           NULLIF(f.registration_day_key, -9999) AS reg_day,
           CASE WHEN f.unregistration_day_key < -9000 THEN NULL ELSE f.unregistration_day_key END AS unreg_day
    FROM dw.fact_enrollment f
    JOIN dw.dim_offering o ON o.offering_key = f.offering_key
), grid AS (                                 -- mọi tuần của khóa, kể cả tuần không hoạt động
    SELECT e.*, w, 7 * w + 6 AS end_day
    FROM enrollment e
    CROSS JOIN LATERAL generate_series(0, e.length_weeks - 1) AS w
), daily AS (                                -- gộp theo ngày để đếm đúng số ngày hoạt động
    SELECT student_key, offering_key, day_key, SUM(sum_click) AS clicks
    FROM dw.fact_vle_daily
    GROUP BY student_key, offering_key, day_key
), pre_start AS (                            -- hoạt động trước khai giảng chỉ tính vào lũy kế
    SELECT student_key, offering_key, SUM(clicks) AS clicks, COUNT(*) AS days, MAX(day_key) AS last_day
    FROM daily WHERE day_key < 0
    GROUP BY student_key, offering_key
), weekly AS (
    SELECT student_key, offering_key, FLOOR(day_key / 7.0)::int AS w,
           SUM(clicks) AS clicks, COUNT(*) AS days, MAX(day_key) AS last_day
    FROM daily WHERE day_key >= 0
    GROUP BY student_key, offering_key, FLOOR(day_key / 7.0)::int
), coursework AS (                           -- chỉ TMA và CMA; bài thi không tính
    SELECT f.student_key, f.offering_key, f.is_banked, f.score, f.submitted_day_key,
           FLOOR(a.effective_due_day / 7.0)::int AS due_w
    FROM dw.fact_assessment f
    JOIN dw.dim_assessment a ON a.assessment_key = f.assessment_key
    WHERE a.assessment_type <> 'Exam'
), submitted AS (                            -- nộp trước khai giảng thì tính vào tuần 0; banked không tính
    SELECT student_key, offering_key, GREATEST(FLOOR(submitted_day_key / 7.0)::int, 0) AS w,
           COUNT(*) AS n, SUM(score) AS score_sum, COUNT(score) AS score_n
    FROM coursework WHERE NOT is_banked
    GROUP BY 1, 2, 3
), covered AS (                              -- bài hết "bỏ lỡ" ở tuần muộn hơn giữa tuần đến hạn và tuần nộp
    SELECT student_key, offering_key,
           GREATEST(due_w, CASE WHEN is_banked THEN 0 ELSE FLOOR(submitted_day_key / 7.0)::int END) AS w,
           COUNT(*) AS n
    FROM coursework
    GROUP BY 1, 2, 3
), due AS (                                  -- số bài đến hạn lũy kế của từng lần mở
    SELECT offering_key, FLOOR(effective_due_day / 7.0)::int AS w, COUNT(*) AS n
    FROM dw.dim_assessment WHERE assessment_type <> 'Exam'
    GROUP BY 1, 2
), filled AS (
    SELECT g.student_key, g.offering_key, g.w, g.end_day, g.reg_day, g.unreg_day,
           COALESCE(wk.clicks, 0) AS clicks_week,
           COALESCE(wk.days, 0) AS days_week,
           COALESCE(p.clicks, 0) + SUM(COALESCE(wk.clicks, 0)) OVER win AS clicks_cum,
           COALESCE(p.days, 0) + SUM(COALESCE(wk.days, 0)) OVER win AS days_cum,
           COALESCE(MAX(wk.last_day) OVER win, p.last_day) AS last_day,
           SUM(COALESCE(s.n, 0)) OVER win AS submitted_cum,
           SUM(COALESCE(s.score_sum, 0)) OVER win AS score_sum,
           SUM(COALESCE(s.score_n, 0)) OVER win AS score_n,
           SUM(COALESCE(c.n, 0)) OVER win AS covered_cum,
           SUM(COALESCE(d.n, 0)) OVER win AS due_cum
    FROM grid g
    LEFT JOIN weekly wk ON wk.student_key = g.student_key AND wk.offering_key = g.offering_key AND wk.w = g.w
    LEFT JOIN pre_start p ON p.student_key = g.student_key AND p.offering_key = g.offering_key
    LEFT JOIN submitted s ON s.student_key = g.student_key AND s.offering_key = g.offering_key AND s.w = g.w
    LEFT JOIN covered c ON c.student_key = g.student_key AND c.offering_key = g.offering_key AND c.w = g.w
    LEFT JOIN due d ON d.offering_key = g.offering_key AND d.w = g.w
    WINDOW win AS (PARTITION BY g.student_key, g.offering_key ORDER BY g.w)
)
SELECT student_key, offering_key, end_day AS snapshot_day_key,
       clicks_week::int AS clicks_week,
       days_week::smallint AS active_days_week,
       clicks_cum::int AS clicks_cum,
       days_cum::smallint AS active_days_cum,
       (end_day - last_day)::smallint AS days_since_last_activity,
       submitted_cum::smallint AS submitted_cum,
       due_cum::smallint AS due_cum,
       GREATEST(due_cum - covered_cum, 0)::smallint AS missed_cum,
       ROUND(score_sum::numeric / NULLIF(score_n, 0), 2) AS avg_score_cum
FROM filled
WHERE (reg_day IS NULL OR reg_day <= end_day)        -- đã đăng ký vào cuối tuần
  AND (unreg_day IS NULL OR unreg_day > end_day);    -- và chưa hủy
