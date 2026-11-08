-- Truy vấn OLAP mẫu, chỉ đọc, tái lập các bảng ở Mục 4.2 của báo cáo.
-- Bổ sung cho giao diện: phân cấp ngày -> tuần -> khối 4 tuần và tới từng tài nguyên,
-- cùng pivot và CUBE. Chạy: psql -d oulad_dw -f src/sql/04_olap_mau.sql

-- name: rollup_time
-- Roll-up thời gian của một lần mở: tổng click, bốn khối đầu, ba cấp khối/tuần/ngày.
SELECT d.block_no, d.week_no, d.day_no, SUM(f.sum_click) AS clicks,
       GROUPING(d.block_no, d.week_no, d.day_no) AS level_mask
FROM dw.fact_vle_daily f
JOIN dw.dim_day d ON d.day_key = f.day_key
JOIN dw.dim_offering o ON o.offering_key = f.offering_key
WHERE o.code_module = 'FFF' AND o.code_presentation = '2014J' AND d.block_no BETWEEN 0 AND 3
GROUP BY ROLLUP (d.block_no, d.week_no, d.day_no)
ORDER BY d.block_no NULLS FIRST, d.week_no NULLS FIRST, d.day_no NULLS FIRST;

-- name: rollup_resource
-- Roll-up tài nguyên: nhóm -> loại -> từng id_site.
SELECT s.activity_group, s.activity_type, s.id_site, SUM(f.sum_click) AS clicks,
       GROUPING(s.activity_group, s.activity_type, s.id_site) AS level_mask
FROM dw.fact_vle_daily f
JOIN dw.dim_vle_site s ON s.site_key = f.site_key
JOIN dw.dim_offering o ON o.offering_key = f.offering_key
WHERE o.code_module = 'FFF' AND o.code_presentation = '2014J'
GROUP BY ROLLUP (s.activity_group, s.activity_type, s.id_site)
ORDER BY s.activity_group NULLS FIRST, s.activity_type NULLS FIRST, clicks DESC;

-- name: pivot_module_result
-- Pivot: module ở dòng, kết quả cuối khóa ở cột.
SELECT o.code_module,
       COUNT(*) FILTER (WHERE r.final_result = 'Distinction') AS distinction,
       COUNT(*) FILTER (WHERE r.final_result = 'Pass') AS pass,
       COUNT(*) FILTER (WHERE r.final_result = 'Fail') AS fail,
       COUNT(*) FILTER (WHERE r.final_result = 'Withdrawn') AS withdrawn,
       COUNT(*) AS total
FROM dw.fact_enrollment e
JOIN dw.dim_offering o USING (offering_key)
JOIN dw.dim_result r USING (result_key)
GROUP BY ROLLUP (o.code_module)
ORDER BY o.code_module NULLS LAST;

-- name: cube_domain_outcome
-- CUBE trên lĩnh vực và nhóm kết quả: đủ mọi tổ hợp tổng phụ.
SELECT o.domain, r.outcome_group, COUNT(*) AS enrollments,
       GROUPING(o.domain, r.outcome_group) AS level_mask
FROM dw.fact_enrollment e
JOIN dw.dim_offering o USING (offering_key)
JOIN dw.dim_result r USING (result_key)
GROUP BY CUBE (o.domain, r.outcome_group)
ORDER BY level_mask, o.domain, r.outcome_group;
