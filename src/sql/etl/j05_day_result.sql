INSERT INTO dw.dim_day (day_key, day_no, week_no, block_no, course_phase)
SELECT day, day, floor(day / 7.0)::int, floor(day / 28.0)::int,
       CASE WHEN day < 0 THEN 'Before start' ELSE 'After start' END
FROM generate_series(-365, 608) AS day;
INSERT INTO dw.dim_day (day_key, course_phase) VALUES
(-9998, 'Not applicable'), (-9999, 'Unknown');
INSERT INTO dw.dim_result VALUES
(1, 'Distinction', 'Successful', false, 1),
(2, 'Pass', 'Successful', false, 2),
(3, 'Fail', 'At risk', true, 3),
(4, 'Withdrawn', 'At risk', true, 4);
