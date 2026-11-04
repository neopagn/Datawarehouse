"""Draw the galaxy schema to docs/schema_dw.png.

Run:  python src/profiling/draw_schema.py docs/schema_dw.png
"""
import site
import sys

sys.path.append(site.getusersitepackages())
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

INK = "#1f2933"
MUTED = "#52606d"
FACT = ("#fdf1e3", "#b7621b")
DIM = ("#e8f1f8", "#2b6a99")
LANE = {"dim_student": "#2b6a99", "dim_offering": "#2f8a6b", "dim_day": "#8a4fa8"}
LINE_H = 0.31
TITLE_H = 0.46
W = 4.1

TABLES = {
    "dim_student": ("28.857 dòng · SCD type 2", ["PK student_key", "id_student, version_no", "gender, region, disability",
                                                  "highest_education", "imd_band, imd_order", "age_band (type 2)",
                                                  "valid_from / valid_to, is_current"]),
    "dim_offering": ("22 dòng", ["PK offering_key", "code_module, domain", "code_presentation", "start_year, start_month",
                                 "length_days, length_weeks"]),
    "dim_day": ("976 dòng · ngày tính từ khai giảng", ["PK day_key  (-9998 N/A, -9999 Unknown)", "day_no", "week_no, block_no", "course_phase"]),
    "fact_enrollment": ("32.593 dòng · accumulating snapshot\n1 sinh viên × 1 lần mở module",
                        ["FK student, offering, result", "FK registration_day, unregistration_day", "FK first_active_day, last_active_day",
                         "enrollment_count, total_clicks", "active_days, submitted_count", "banked_count", "avg_coursework_score*",
                         "weighted_coursework_score*", "studied_credits*, num_prev_attempts*", "has_status_conflict"]),
    "fact_assessment": ("173.912 dòng · transaction\n1 sinh viên × 1 bài",
                        ["FK student, offering, assessment", "FK submitted_day", "score*, weighted_points", "days_late*, is_late",
                         "is_banked", "is_after_unregistration"]),
    "fact_vle_daily": ("8.459.320 dòng · transaction\n1 sinh viên × 1 tài nguyên × 1 ngày",
                       ["FK student, offering, site", "FK day", "sum_click, source_rows", "is_after_unregistration"]),
    "fact_student_week": ("920.734 dòng · periodic snapshot\n1 sinh viên còn đăng ký × 1 tuần",
                          ["FK student, offering", "FK snapshot_day", "clicks_week, active_days_week", "clicks_cum†, active_days_cum†",
                           "days_since_last_activity†", "submitted_cum†, due_cum†", "missed_cum†, avg_score_cum†"]),
    "dim_result": ("4 dòng", ["PK result_key", "final_result", "outcome_group, is_at_risk", "result_order"]),
    "dim_assessment": ("206 dòng", ["PK assessment_key, id_assessment", "offering_key → dim_offering", "assessment_type, weight",
                                    "due_day, effective_due_day", "is_due_estimated, is_formative", "has_recorded_results"]),
    "dim_vle_site": ("6.364 dòng", ["PK site_key, id_site", "offering_key → dim_offering", "activity_type, activity_group",
                                    "planned_week_from / to"]),
}


def height(name):
    sub, cols = TABLES[name]
    return TITLE_H + 0.27 * (sub.count("\n") + 1) + LINE_H * len(cols) + 0.14


def box(ax, name, x, top, palette):
    fill, edge = palette
    sub, cols = TABLES[name]
    hgt = height(name)
    ax.add_patch(FancyBboxPatch((x, top - hgt), W, hgt, boxstyle="round,pad=0,rounding_size=0.08",
                                fc=fill, ec=edge, lw=1.6, zorder=3))
    ax.text(x + 0.14, top - 0.27, name, fontsize=12.5, fontweight="bold", color=edge, va="center", zorder=4)
    y = top - TITLE_H - 0.06
    for line in sub.split("\n"):
        ax.text(x + 0.14, y, line, fontsize=8.8, color=MUTED, va="center", zorder=4)
        y -= 0.27
    y -= 0.04
    for c in cols:
        ax.text(x + 0.14, y, c, fontsize=9.6, color=INK, va="center", zorder=4)
        y -= LINE_H
    return hgt


fig, ax = plt.subplots(figsize=(19, 12.9), dpi=170)
ax.set_xlim(0, 19)
ax.set_ylim(-0.7, 12.2)
ax.axis("off")
ax.text(0.3, 11.92, "Galaxy schema của kho dữ liệu OULAD", fontsize=17, fontweight="bold", color=INK, va="center")

# shared dimensions on top, each with its own horizontal lane
top_y = 11.5
shared_x = {"dim_student": 1.6, "dim_offering": 7.45, "dim_day": 13.3}
for n, x in shared_x.items():
    box(ax, n, x, top_y, DIM)

fact_x = {"fact_enrollment": 0.3, "fact_assessment": 4.9, "fact_vle_daily": 9.9, "fact_student_week": 14.6}
fact_top = 7.45
for n, x in fact_x.items():
    box(ax, n, x, fact_top, FACT)

lanes = {"dim_student": 8.0, "dim_offering": 7.82, "dim_day": 7.64}
offset = {"dim_student": 1.45, "dim_offering": 2.05, "dim_day": 2.65}
for dim, sx in shared_x.items():
    colour = LANE[dim]
    lane = lanes[dim]
    start = sx + W / 2
    ax.plot([start, start], [top_y - height(dim), lane], color=colour, lw=2, zorder=2, solid_capstyle="round")
    xs = [fx + offset[dim] for fx in fact_x.values()]
    ax.plot([min(xs + [start]), max(xs + [start])], [lane, lane], color=colour, lw=2, zorder=2, solid_capstyle="round")
    for x in xs:
        ax.plot([x, x], [lane, fact_top], color=colour, lw=2, zorder=2, solid_capstyle="round")
        ax.plot(x, fact_top + 0.03, marker="v", ms=6, color=colour, zorder=5)

# dimensions used by a single fact sit below that fact
below = {"dim_result": "fact_enrollment", "dim_assessment": "fact_assessment", "dim_vle_site": "fact_vle_daily"}
below_top = 2.55
for dim, fact in below.items():
    x = fact_x[fact]
    box(ax, dim, x, below_top, DIM)
    ax.plot([x + W / 2, x + W / 2], [fact_top - height(fact), below_top], color=DIM[1], lw=2, zorder=2)
    ax.plot(x + W / 2, fact_top - height(fact) - 0.03, marker="^", ms=6, color=DIM[1], zorder=5)

# legend
lx, ly = 14.6, 2.3
ax.text(lx, ly, "Cách đọc", fontsize=11, fontweight="bold", color=INK)
for i, (dim, colour) in enumerate(LANE.items()):
    y = ly - 0.36 * (i + 1)
    ax.plot([lx, lx + 0.5], [y, y], color=colour, lw=2.4)
    ax.text(lx + 0.62, y, f"chiều dùng chung: {dim}", fontsize=9.6, color=INK, va="center")
notes = ["* không cộng dồn được (chỉ lấy trung bình)", "† semi-additive: không SUM theo thời gian",
         "fact_enrollment dùng dim_day theo 4 vai trò ngày"]
for i, t in enumerate(notes):
    ax.text(lx, ly - 1.6 - 0.32 * i, t, fontsize=9.6, color=MUTED, va="center")

fig.savefig(sys.argv[1], bbox_inches="tight", facecolor="white")
