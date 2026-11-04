"""Test the design end to end: build every table from the raw CSV, load it through the real DDL
into PostgreSQL, then reconcile totals and answer the business questions.

This is a design check written with pandas, not the production ETL.

Run:  python src/profiling/validate_design.py <raw_dir> <work_dir> <pg_package_dir> src/sql
"""
import glob
import os
import site
import sys
import time

RAW, WORK, PG_PKG, SQL = sys.argv[1:5]
sys.path.append(site.getusersitepackages())
sys.path.insert(0, PG_PKG)
import numpy as np
import pandas as pd
import pgserver

sys.stdout.reconfigure(encoding="utf-8")
os.makedirs(WORK, exist_ok=True)
ENR = ["code_module", "code_presentation", "id_student"]
OFFER = ["code_module", "code_presentation"]
NA_DAY, UNKNOWN_DAY = -9998, -9999
ORDER = {"2013B": 0, "2013J": 1, "2014B": 2, "2014J": 3}
DOMAIN = {"AAA": "Social Sciences", "BBB": "Social Sciences", "GGG": "Social Sciences",
          "CCC": "STEM", "DDD": "STEM", "EEE": "STEM", "FFF": "STEM"}
ACTIVITY_GROUP = {
    "oucontent": "Content", "resource": "Content", "subpage": "Content", "page": "Content",
    "url": "Content", "dualpane": "Content", "folder": "Content", "htmlactivity": "Content",
    "sharedsubpage": "Content", "repeatactivity": "Content", "glossary": "Content",
    "quiz": "Practice", "externalquiz": "Practice", "questionnaire": "Practice",
    "forumng": "Collaboration", "ouwiki": "Collaboration", "oucollaborate": "Collaboration",
    "ouelluminate": "Collaboration", "dataplus": "Collaboration",
    "homepage": "Navigation",
}


def h(title):
    print(f"\n{'=' * 8} {title} {'=' * 8}", flush=True)


def read(name, **kw):
    return pd.read_csv(os.path.join(RAW, name + ".csv"), **kw)


def out(df, name, cols):
    df[cols].to_csv(os.path.join(WORK, name + ".csv"), index=False, na_rep="")
    print(f"  built {name}: {len(df)} rows", flush=True)


t0 = time.time()
courses = read("courses")
assess = read("assessments")
vle = read("vle")
info = read("studentInfo", keep_default_na=False)
reg = read("studentRegistration")
sa = read("studentAssessment")
sv = read("studentVle", dtype={"code_module": str, "code_presentation": str, "id_student": "int32",
                               "id_site": "int32", "date": "int16", "sum_click": "int32"})

h("BUILD DIMENSIONS")
# dim_offering
off = courses.sort_values(OFFER).reset_index(drop=True)
off["offering_key"] = off.index + 1
off["domain"] = off.code_module.map(DOMAIN)
off["start_year"] = off.code_presentation.str[:4].astype(int)
off["start_month"] = off.code_presentation.str[4].map({"B": 2, "J": 10})
off["length_days"] = off.module_presentation_length
off["length_weeks"] = np.ceil(off.length_days / 7).astype(int)
out(off, "dim_offering", ["offering_key", "code_module", "domain", "code_presentation",
                          "start_year", "start_month", "length_days", "length_weeks"])
offkey = off[OFFER + ["offering_key", "length_days", "length_weeks"]]

# dim_student: one version per (id_student, age_band), oldest band first
info["imd_band"] = info.imd_band.replace({"10-20": "10-20%", "": "Unknown"})
IMD = {f"{i * 10}-{(i + 1) * 10}%": i + 1 for i in range(10)}
info["o"] = info.code_presentation.map(ORDER)
AGE = {"0-35": 0, "35-55": 1, "55<=": 2}
info["a"] = info.age_band.map(AGE)
attrs = ["gender", "region", "highest_education", "imd_band", "age_band", "disability"]
ver = (info.groupby(["id_student", "a"] + attrs).o.agg(["min", "max"]).reset_index()
       .sort_values(["id_student", "a"]))
ver["version_no"] = ver.groupby("id_student").cumcount() + 1
ver["is_current"] = ver.groupby("id_student").version_no.transform("max") == ver.version_no
back = {v: k for k, v in ORDER.items()}
ver["valid_from_presentation"] = ver["min"].map(back)
ver["valid_to_presentation"] = ver["max"].map(back)
ver["imd_order"] = ver.imd_band.map(IMD).astype("Int64")
ver = ver.reset_index(drop=True)
ver["student_key"] = ver.index + 1
out(ver, "dim_student", ["student_key", "id_student", "version_no", "gender", "region",
                         "highest_education", "imd_band", "imd_order", "age_band", "disability",
                         "valid_from_presentation", "valid_to_presentation", "is_current"])

# dim_day
days = pd.DataFrame({"day_no": np.arange(-365, 609)})
days["day_key"] = days.day_no
days["week_no"] = np.floor_divide(days.day_no, 7)
days["block_no"] = np.floor_divide(days.day_no, 28)
days["course_phase"] = np.where(days.day_no < 0, "Before start", "After start")
special = pd.DataFrame({"day_key": [NA_DAY, UNKNOWN_DAY], "course_phase": ["Not applicable", "Unknown"]})
dd = pd.concat([days, special], ignore_index=True).astype({"day_no": "Int64", "week_no": "Int64", "block_no": "Int64"})
out(dd, "dim_day", ["day_key", "day_no", "week_no", "block_no", "course_phase"])

# dim_result
res = pd.DataFrame({"result_key": [1, 2, 3, 4],
                    "final_result": ["Distinction", "Pass", "Fail", "Withdrawn"],
                    "outcome_group": ["Successful", "Successful", "At risk", "At risk"],
                    "is_at_risk": [False, False, True, True],
                    "result_order": [1, 2, 3, 4]})
out(res, "dim_result", list(res.columns))

# dim_assessment
da = assess.merge(offkey, on=OFFER).sort_values("id_assessment").reset_index(drop=True)
da["assessment_key"] = da.index + 1
da["due_day"] = da.date.astype("Int64")
da["is_due_estimated"] = da.date.isna()
da["effective_due_day"] = da.date.fillna(da.length_days).astype(int)
da["is_formative"] = da.weight == 0
da["has_recorded_results"] = da.id_assessment.isin(sa.id_assessment)
out(da, "dim_assessment", ["assessment_key", "id_assessment", "offering_key", "assessment_type", "weight",
                           "due_day", "effective_due_day", "is_due_estimated", "is_formative", "has_recorded_results"])

# dim_vle_site
ds = vle.merge(offkey, on=OFFER).sort_values("id_site").reset_index(drop=True)
ds["site_key"] = ds.index + 1
ds["activity_group"] = ds.activity_type.map(ACTIVITY_GROUP)
assert ds.activity_group.notna().all()
ds["planned_week_from"] = ds.week_from.astype("Int64")
ds["planned_week_to"] = ds.week_to.astype("Int64")
out(ds, "dim_vle_site", ["site_key", "id_site", "offering_key", "activity_type", "activity_group",
                         "planned_week_from", "planned_week_to"])

h("BUILD FACTS")
e = (info.merge(reg, on=ENR).merge(offkey, on=OFFER)
     .merge(ver[["id_student", "age_band", "student_key"]], on=["id_student", "age_band"])
     .merge(res[["final_result", "result_key"]], on="final_result"))
assert len(e) == 32593
ekeys = e[ENR + ["student_key", "offering_key", "date_registration", "date_unregistration", "length_days", "length_weeks"]]

# fact_vle_daily: SUM the repeated rows
v = (sv.groupby(["code_module", "code_presentation", "id_student", "id_site", "date"], sort=False)
     .sum_click.agg(sum_click="sum", source_rows="size").reset_index())
v = v.merge(ekeys[ENR + ["student_key", "offering_key", "date_unregistration"]], on=ENR)
v = v.merge(ds[["id_site", "site_key"]], on="id_site")
v["day_key"] = v.date
v["is_after_unregistration"] = v.date > v.date_unregistration
out(v, "fact_vle_daily", ["student_key", "offering_key", "site_key", "day_key", "sum_click", "source_rows", "is_after_unregistration"])
print("  source rows grouped into 6-row keys by offering:",
      v[v.source_rows >= 5].groupby(OFFER).size().to_dict(), flush=True)
print("  keys with source_rows>=5 by activity:",
      v[v.source_rows >= 5].merge(ds[["site_key", "activity_type"]], on="site_key").activity_type.value_counts().head(5).to_dict())

# fact_assessment
a = (sa.merge(da[["id_assessment", "assessment_key", "offering_key", "assessment_type", "weight", "effective_due_day"]], on="id_assessment")
     .merge(ekeys[["id_student", "offering_key", "student_key", "date_unregistration"]], on=["id_student", "offering_key"]))
assert len(a) == 173912
a["banked"] = a.is_banked == 1
a["submitted_day_key"] = np.where(a.banked, NA_DAY, a.date_submitted)
a["score"] = a.score.astype("Int64")
a["weighted_points"] = (a.score.astype(float) * a.weight / 100).round(2)
late = (a.date_submitted - a.effective_due_day).where(~a.banked & (a.assessment_type != "Exam"))
a["days_late"] = late.astype("Int64")
a["is_late"] = (late > 0).astype("boolean").where(late.notna())
a["is_after_unregistration"] = a.date_submitted > a.date_unregistration
fa = a.rename(columns={"banked": "is_banked_flag"})
fa["is_banked"] = fa.is_banked_flag
out(fa, "fact_assessment", ["student_key", "offering_key", "assessment_key", "submitted_day_key", "score",
                            "weighted_points", "days_late", "is_late", "is_banked", "is_after_unregistration"])

# fact_enrollment
day_level = v.groupby(["student_key", "offering_key", "date"], sort=False).sum_click.sum().reset_index()
act = day_level.groupby(["student_key", "offering_key"]).agg(
    total_clicks=("sum_click", "sum"), active_days=("date", "size"),
    first_active_day_key=("date", "min"), last_active_day_key=("date", "max")).reset_index()
cw = a[a.assessment_type != "Exam"].copy()
cw["score_f"] = cw.score.astype(float)
cw["w_scored"] = cw.weight.where(cw.score_f.notna())
sub = cw.groupby(["student_key", "offering_key"]).agg(
    submitted_count=("banked", lambda s: int((~s).sum())), banked_count=("banked", "sum"),
    avg_coursework_score=("score_f", "mean"),
    w_points=("weighted_points", "sum"), w_total=("w_scored", "sum")).reset_index()
sub["weighted_coursework_score"] = (sub.w_points / sub.w_total * 100).where(sub.w_total > 0)
fe = e.merge(act, on=["student_key", "offering_key"], how="left").merge(sub, on=["student_key", "offering_key"], how="left")
for c in ["total_clicks", "active_days", "submitted_count", "banked_count"]:
    fe[c] = fe[c].fillna(0).astype(int)
for c in ["first_active_day_key", "last_active_day_key"]:
    fe[c] = fe[c].fillna(NA_DAY).astype(int)
fe["registration_day_key"] = fe.date_registration.fillna(UNKNOWN_DAY).astype(int)
withdrawn = fe.final_result == "Withdrawn"
fe["unregistration_day_key"] = fe.date_unregistration.fillna(-1).astype(int)
fe.loc[fe.date_unregistration.isna(), "unregistration_day_key"] = np.where(
    withdrawn[fe.date_unregistration.isna()], UNKNOWN_DAY, NA_DAY)
fe["has_status_conflict"] = (withdrawn & fe.date_unregistration.isna()) | ((fe.final_result == "Fail") & fe.date_unregistration.notna())
fe["enrollment_count"] = 1
fe["num_prev_attempts"] = fe.num_of_prev_attempts
for c in ["avg_coursework_score", "weighted_coursework_score"]:
    fe[c] = fe[c].round(2)
out(fe, "fact_enrollment", ["student_key", "offering_key", "result_key", "registration_day_key", "unregistration_day_key",
                            "first_active_day_key", "last_active_day_key", "enrollment_count", "studied_credits",
                            "num_prev_attempts", "total_clicks", "active_days", "submitted_count", "banked_count",
                            "avg_coursework_score", "weighted_coursework_score", "has_status_conflict"])

# fact_student_week: dense skeleton of (enrollment, week) still registered at the end of that week
sk = ekeys[["student_key", "offering_key", "date_registration", "date_unregistration", "length_weeks"]]
sk = sk.loc[sk.index.repeat(sk.length_weeks)].copy()
sk["w"] = sk.groupby(["student_key", "offering_key"]).cumcount()
sk["end"] = sk.w * 7 + 6
sk = sk[(sk.date_unregistration.isna() | (sk.date_unregistration > sk.end)) &
        (sk.date_registration.isna() | (sk.date_registration <= sk.end))]
ids = ["student_key", "offering_key"]

day_level["w"] = np.floor_divide(day_level.date, 7)
post = day_level[day_level.w >= 0].groupby(ids + ["w"]).agg(
    clicks_week=("sum_click", "sum"), active_days_week=("date", "size"), last_day=("date", "max")).reset_index()
pre = day_level[day_level.w < 0].groupby(ids).agg(
    pre_clicks=("sum_click", "sum"), pre_days=("date", "size"), pre_last=("date", "max")).reset_index()

ok = a[(~a.banked) & (a.assessment_type != "Exam")].copy()
ok["w"] = np.floor_divide(ok.date_submitted, 7).clip(lower=0)
ok["score_f"] = ok.score.astype(float)
s_w = ok.groupby(ids + ["w"]).agg(sub=("score_f", "size"), s_sum=("score_f", "sum"), s_n=("score_f", "count")).reset_index()

# an assessment stops being "missed" in the later of its due week and its submission week
cover = a[a.assessment_type != "Exam"].copy()
cover["due_w"] = np.floor_divide(cover.effective_due_day, 7)
cover["sub_w"] = np.where(cover.banked, 0, np.floor_divide(cover.date_submitted, 7))
cover["w"] = np.maximum(cover.due_w, cover.sub_w)
c_w = cover.groupby(ids + ["w"]).size().rename("covered").reset_index()

due = da[da.assessment_type != "Exam"].copy()
due["w"] = np.floor_divide(due.effective_due_day, 7)
due_w = due.groupby(["offering_key", "w"]).size().rename("due").reset_index()
grid = off[["offering_key", "length_weeks"]].loc[off.index.repeat(off.length_weeks)].copy()
grid["w"] = grid.groupby("offering_key").cumcount()
grid = grid.merge(due_w, on=["offering_key", "w"], how="left").fillna({"due": 0})
grid["due_cum"] = grid.groupby("offering_key").due.cumsum().astype(int)

# cumulative totals must see every week, including weeks where the row was filtered out later
full = ekeys[ids + ["length_weeks"]].copy()
full = full.loc[full.index.repeat(full.length_weeks)]
full["w"] = full.groupby(ids).cumcount()
full = (full.merge(post, on=ids + ["w"], how="left").merge(s_w, on=ids + ["w"], how="left")
        .merge(c_w, on=ids + ["w"], how="left").merge(pre, on=ids, how="left"))
for c in ["clicks_week", "active_days_week", "sub", "s_sum", "s_n", "covered", "pre_clicks", "pre_days"]:
    full[c] = full[c].fillna(0)
g = full.groupby(ids, sort=False)
full["clicks_cum"] = g.clicks_week.cumsum() + full.pre_clicks
full["active_days_cum"] = g.active_days_week.cumsum() + full.pre_days
full["submitted_cum"] = g["sub"].cumsum()
full["covered_cum"] = g.covered.cumsum()
s_cum = g.s_sum.cumsum()
n_cum = g.s_n.cumsum()
full["avg_score_cum"] = (s_cum / n_cum.where(n_cum > 0)).round(2)
full["last_seen"] = g.last_day.ffill().fillna(full.pre_last)
fw = sk[ids + ["w", "end"]].merge(full.drop(columns=["length_weeks"]), on=ids + ["w"]).merge(grid[["offering_key", "w", "due_cum"]], on=["offering_key", "w"])
fw["snapshot_day_key"] = fw.end
fw["missed_cum"] = (fw.due_cum - fw.covered_cum).clip(lower=0).astype(int)
fw["days_since_last_activity"] = (fw.end - fw.last_seen).astype("Int64")
for c in ["clicks_week", "active_days_week", "clicks_cum", "active_days_cum", "submitted_cum"]:
    fw[c] = fw[c].astype(int)
out(fw, "fact_student_week", ["student_key", "offering_key", "snapshot_day_key", "clicks_week", "active_days_week", "clicks_cum",
                              "active_days_cum", "days_since_last_activity", "submitted_cum", "due_cum", "missed_cum", "avg_score_cum"])
print(f"  build time {time.time() - t0:.0f}s", flush=True)
del sv, v, day_level, full, fw, sk, a, fa, fe, cw, cover, post, ok, g, s_cum, n_cum

h("LOAD INTO POSTGRESQL")
db = pgserver.get_server(os.path.join(WORK, "pgdata"), cleanup_mode="stop")
print(db.psql("SELECT version();"), flush=True)


def fw_path(p):
    return os.path.abspath(p).replace(chr(92), "/")


def run_file(p):
    with open(p, encoding="utf-8") as f:
        return db.psql("\\set ON_ERROR_STOP on\n" + f.read())


t = time.time()
run_file(os.path.join(SQL, "00_ddl_staging.sql"))
run_file(os.path.join(SQL, "01_ddl_dw.sql"))
print(f"  DDL applied in {time.time() - t:.1f}s", flush=True)

t = time.time()
for csv_name, table in [("courses", "courses"), ("assessments", "assessments"), ("vle", "vle"),
                        ("studentInfo", "student_info"), ("studentRegistration", "student_registration"),
                        ("studentAssessment", "student_assessment"), ("studentVle", "student_vle")]:
    db.psql(f"\\set ON_ERROR_STOP on\nCOPY staging.{table} FROM '{fw_path(os.path.join(RAW, csv_name + '.csv'))}' WITH (FORMAT csv, HEADER true, NULL '');")
print(f"  staging COPY in {time.time() - t:.0f}s", flush=True)
print(db.psql("""
SELECT 'courses' t, count(*) FROM staging.courses UNION ALL SELECT 'assessments', count(*) FROM staging.assessments
UNION ALL SELECT 'vle', count(*) FROM staging.vle UNION ALL SELECT 'student_info', count(*) FROM staging.student_info
UNION ALL SELECT 'student_registration', count(*) FROM staging.student_registration
UNION ALL SELECT 'student_assessment', count(*) FROM staging.student_assessment
UNION ALL SELECT 'student_vle', count(*) FROM staging.student_vle;"""), flush=True)

LOAD = ["dim_student", "dim_offering", "dim_day", "dim_result", "dim_assessment", "dim_vle_site",
        "fact_enrollment", "fact_assessment", "fact_vle_daily", "fact_student_week"]
for name in LOAD:
    t = time.time()
    p = os.path.join(WORK, name + ".csv")
    header = open(p, encoding="utf-8").readline().strip()
    db.psql(f"\\set ON_ERROR_STOP on\nCOPY dw.{name} ({header}) FROM '{fw_path(p)}' WITH (FORMAT csv, HEADER true, NULL '');")
    print(f"  {name} loaded in {time.time() - t:.0f}s", flush=True)
t = time.time()
db.psql("\\set ON_ERROR_STOP on\nREFRESH MATERIALIZED VIEW dw.agg_vle_offering_week_activity; ANALYZE;")
print(f"  aggregate refreshed in {time.time() - t:.0f}s", flush=True)

h("RECONCILIATION")
print(db.psql("""
SELECT 'dim_student' t, count(*) n FROM dw.dim_student UNION ALL SELECT 'dim_offering', count(*) FROM dw.dim_offering
UNION ALL SELECT 'dim_day', count(*) FROM dw.dim_day UNION ALL SELECT 'dim_result', count(*) FROM dw.dim_result
UNION ALL SELECT 'dim_assessment', count(*) FROM dw.dim_assessment UNION ALL SELECT 'dim_vle_site', count(*) FROM dw.dim_vle_site
UNION ALL SELECT 'fact_enrollment', count(*) FROM dw.fact_enrollment UNION ALL SELECT 'fact_assessment', count(*) FROM dw.fact_assessment
UNION ALL SELECT 'fact_vle_daily', count(*) FROM dw.fact_vle_daily UNION ALL SELECT 'fact_student_week', count(*) FROM dw.fact_student_week
UNION ALL SELECT 'agg_vle_offering_week_activity', count(*) FROM dw.agg_vle_offering_week_activity;
SELECT sum(sum_click::bigint) AS staging_clicks, count(*) AS staging_rows FROM staging.student_vle;
SELECT sum(sum_click::bigint) AS fact_clicks, sum(source_rows::bigint) AS fact_source_rows FROM dw.fact_vle_daily;
SELECT sum(total_clicks::bigint) AS enrollment_clicks FROM dw.fact_enrollment;
SELECT sum(total_clicks) AS agg_clicks FROM dw.agg_vle_offering_week_activity;
SELECT count(*) AS rows, count(score) AS scored, sum(is_banked::int) AS banked, sum(is_after_unregistration::int) AS after_unreg, sum(is_late::int) AS late FROM dw.fact_assessment;
SELECT sum(is_after_unregistration::int) AS vle_after_unreg, sum(CASE WHEN is_after_unregistration THEN sum_click ELSE 0 END) AS clicks_after_unreg FROM dw.fact_vle_daily;
SELECT count(*) FILTER (WHERE has_status_conflict) AS status_conflict,
       count(*) FILTER (WHERE registration_day_key = -9999) AS unknown_reg,
       count(*) FILTER (WHERE unregistration_day_key = -9999) AS unknown_unreg,
       count(*) FILTER (WHERE unregistration_day_key = -9998) AS na_unreg,
       count(*) FILTER (WHERE first_active_day_key = -9998) AS no_activity,
       count(*) FILTER (WHERE weighted_coursework_score IS NULL) AS no_weighted FROM dw.fact_enrollment;
SELECT count(*) FILTER (WHERE missed_cum > due_cum) AS missed_gt_due,
       count(*) FILTER (WHERE clicks_week > clicks_cum) AS week_gt_cum,
       min(missed_cum), max(missed_cum), max(due_cum), max(snapshot_day_key) FROM dw.fact_student_week;
"""), flush=True)

QUESTIONS = {
"Q1a result by domain and module (ROLLUP)": """
SELECT o.domain, o.code_module, sum(f.enrollment_count) AS enrollments,
       round(100.0 * sum(f.enrollment_count) FILTER (WHERE r.is_at_risk) / sum(f.enrollment_count), 1) AS at_risk_pct
FROM dw.fact_enrollment f JOIN dw.dim_offering o USING (offering_key) JOIN dw.dim_result r USING (result_key)
GROUP BY ROLLUP (o.domain, o.code_module) ORDER BY 1 NULLS LAST, 2 NULLS LAST;""",
"Q1b at-risk share by IMD": """
SELECT s.imd_band, count(*) AS n, round(100.0 * count(*) FILTER (WHERE r.is_at_risk) / count(*), 1) AS at_risk_pct
FROM dw.fact_enrollment f JOIN dw.dim_student s USING (student_key) JOIN dw.dim_result r USING (result_key)
GROUP BY s.imd_band, s.imd_order ORDER BY s.imd_order NULLS LAST;""",
"Q1c at-risk share by education and disability (CUBE)": """
SELECT s.highest_education, s.disability, count(*) AS n, round(100.0 * count(*) FILTER (WHERE r.is_at_risk) / count(*), 1) AS at_risk_pct
FROM dw.fact_enrollment f JOIN dw.dim_student s USING (student_key) JOIN dw.dim_result r USING (result_key)
GROUP BY CUBE (s.highest_education, s.disability) ORDER BY 1 NULLS LAST, 2 NULLS LAST;""",
"Q1d distinct students, correct vs wrong count": """
SELECT count(DISTINCT s.id_student) AS distinct_students, count(DISTINCT f.student_key) AS distinct_keys, count(*) AS enrollments
FROM dw.fact_enrollment f JOIN dw.dim_student s USING (student_key);""",
"Q2a withdrawal timing": """
SELECT CASE WHEN d.day_no < 0 THEN '1 before start' WHEN d.day_no = 0 THEN '2 day 0'
            WHEN d.day_no < 28 THEN '3 day 1-27' WHEN d.day_no < 84 THEN '4 day 28-83' ELSE '5 day 84+' END AS phase,
       count(*) AS n FROM dw.fact_enrollment f JOIN dw.dim_day d ON d.day_key = f.unregistration_day_key
WHERE d.day_no IS NOT NULL GROUP BY 1 ORDER BY 1;""",
"Q2b registration timing vs result": """
SELECT CASE WHEN d.day_no IS NULL THEN '9 unknown' WHEN d.day_no <= -90 THEN '1 90+ days early' WHEN d.day_no <= -30 THEN '2 30-89 days early'
            WHEN d.day_no < 0 THEN '3 1-29 days early' ELSE '4 on/after start' END AS reg, count(*) n,
       round(100.0 * count(*) FILTER (WHERE r.final_result='Withdrawn') / count(*), 1) AS withdrawn_pct,
       round(100.0 * count(*) FILTER (WHERE r.is_at_risk) / count(*), 1) AS at_risk_pct
FROM dw.fact_enrollment f JOIN dw.dim_day d ON d.day_key = f.registration_day_key JOIN dw.dim_result r USING (result_key)
GROUP BY 1 ORDER BY 1;""",
"Q3a weekly engagement by final result (snapshot, selected weeks)": """
SELECT d.week_no, r.final_result, count(*) AS active_students, round(avg(w.clicks_week), 1) AS avg_clicks_week,
       round(100.0 * count(*) FILTER (WHERE w.clicks_week = 0) / count(*), 1) AS zero_click_pct,
       round(avg(w.missed_cum), 2) AS avg_missed
FROM dw.fact_student_week w JOIN dw.dim_day d ON d.day_key = w.snapshot_day_key
JOIN dw.fact_enrollment f USING (student_key, offering_key) JOIN dw.dim_result r USING (result_key)
WHERE d.week_no IN (3, 7, 11) GROUP BY d.week_no, r.final_result, r.result_order ORDER BY d.week_no, r.result_order;""",
"Q3b clicks per enrollment by activity group and outcome (scans 8.4M rows)": """
SELECT s.activity_group, r.outcome_group, round(sum(v.sum_click)::numeric / max(n.enr), 1) AS clicks_per_enrollment
FROM dw.fact_vle_daily v JOIN dw.dim_vle_site s ON s.site_key = v.site_key
JOIN dw.fact_enrollment f ON f.student_key = v.student_key AND f.offering_key = v.offering_key
JOIN dw.dim_result r ON r.result_key = f.result_key
JOIN (SELECT r2.outcome_group, count(*) enr FROM dw.fact_enrollment f2 JOIN dw.dim_result r2 USING (result_key) GROUP BY 1) n ON n.outcome_group = r.outcome_group
GROUP BY s.activity_group, r.outcome_group ORDER BY 1, 2;""",
"Q3c same data from the aggregate (dashboard path)": """
SELECT activity_group, sum(total_clicks) AS clicks, round(100.0 * sum(total_clicks) / sum(sum(total_clicks)) OVER (), 1) AS pct
FROM dw.agg_vle_offering_week_activity GROUP BY 1 ORDER BY 2 DESC;""",
"Q4a timing and score by assessment type": """
SELECT a.assessment_type, count(*) n, round(avg(f.score), 1) AS avg_score,
       round(100.0 * count(*) FILTER (WHERE f.score < 40) / nullif(count(f.score), 0), 1) AS below_40_pct,
       round(100.0 * avg(f.is_late::int), 1) AS late_pct
FROM dw.fact_assessment f JOIN dw.dim_assessment a USING (assessment_key) GROUP BY 1 ORDER BY 1;""",
"Q4b submission rate of each TMA in one offering (drill-down, FFF-2014J)": """
SELECT a.id_assessment, a.effective_due_day, a.weight, count(f.student_key) AS submitted,
       round(100.0 * count(f.student_key) / max(n.enr), 1) AS submit_pct, round(avg(f.score), 1) AS avg_score
FROM dw.dim_assessment a JOIN dw.dim_offering o USING (offering_key)
LEFT JOIN dw.fact_assessment f USING (assessment_key)
JOIN (SELECT offering_key, count(*) enr FROM dw.fact_enrollment GROUP BY 1) n ON n.offering_key = a.offering_key
WHERE o.code_module = 'FFF' AND o.code_presentation = '2014J' AND a.assessment_type = 'TMA'
GROUP BY a.id_assessment, a.effective_due_day, a.weight ORDER BY 2;""",
"Q5 previous attempts vs result": """
SELECT least(f.num_prev_attempts, 2) AS prev_attempts, count(*) n,
       round(100.0 * count(*) FILTER (WHERE r.is_at_risk) / count(*), 1) AS at_risk_pct
FROM dw.fact_enrollment f JOIN dw.dim_result r USING (result_key) GROUP BY 1 ORDER BY 1;""",
"Q6 can the DSS rank at week_no 7? missed work vs final outcome": """
SELECT least(w.missed_cum, 2) AS missed, count(*) n,
       round(100.0 * count(*) FILTER (WHERE r.is_at_risk) / count(*), 1) AS at_risk_pct
FROM dw.fact_student_week w JOIN dw.dim_day d ON d.day_key = w.snapshot_day_key
JOIN dw.fact_enrollment f USING (student_key, offering_key) JOIN dw.dim_result r USING (result_key)
WHERE d.week_no = 7 GROUP BY 1 ORDER BY 1;""",
"Q7 active students by week, all offerings": """
SELECT d.week_no, count(*) n FROM dw.fact_student_week w JOIN dw.dim_day d ON d.day_key = w.snapshot_day_key
WHERE d.week_no IN (0, 3, 7, 11, 15, 19, 25, 33, 38) GROUP BY 1 ORDER BY 1;""",
}
h("BUSINESS QUESTIONS")
for title, q in QUESTIONS.items():
    t = time.time()
    r = db.psql(q)
    print(f"--- {title} ({time.time() - t:.2f}s)\n{r if r.strip() else 'QUERY FAILED: no output'}", flush=True)

h("SNAPSHOT RECOMPUTED FROM STAGING WITH SQL, INDEPENDENT OF THE PANDAS BUILD (week_no 7, day 55)")
print(db.psql("""
WITH snap AS (
  SELECT w.*, s.id_student, o.code_module, o.code_presentation
  FROM dw.fact_student_week w JOIN dw.dim_student s ON s.student_key = w.student_key
  JOIN dw.dim_offering o ON o.offering_key = w.offering_key WHERE w.snapshot_day_key = 55),
clk AS (
  SELECT code_module, code_presentation, id_student::int AS id_student, sum(sum_click::bigint) AS c
  FROM staging.student_vle WHERE date::int <= 55 GROUP BY 1, 2, 3),
due AS (
  SELECT code_module, code_presentation, id_assessment FROM staging.assessments
  WHERE assessment_type <> 'Exam' AND NULLIF(date, '')::int <= 55),
due_n AS (SELECT code_module, code_presentation, count(*) AS n FROM due GROUP BY 1, 2),
cov AS (
  SELECT d.code_module, d.code_presentation, sa.id_student::int AS id_student, count(*) AS n
  FROM due d JOIN staging.student_assessment sa ON sa.id_assessment = d.id_assessment
  WHERE sa.is_banked = '1' OR sa.date_submitted::int <= 55 GROUP BY 1, 2, 3),
scr AS (
  SELECT a.code_module, a.code_presentation, sa.id_student::int AS id_student,
         count(*) AS n, avg(NULLIF(sa.score, '')::numeric) AS m
  FROM staging.student_assessment sa JOIN staging.assessments a ON a.id_assessment = sa.id_assessment
  WHERE a.assessment_type <> 'Exam' AND sa.is_banked = '0' AND sa.date_submitted::int <= 55 GROUP BY 1, 2, 3)
SELECT count(*) AS rows_checked,
       count(*) FILTER (WHERE coalesce(clk.c, 0) <> snap.clicks_cum) AS clicks_mismatch,
       count(*) FILTER (WHERE coalesce(due_n.n, 0) - coalesce(cov.n, 0) <> snap.missed_cum) AS missed_mismatch,
       count(*) FILTER (WHERE coalesce(scr.n, 0) <> snap.submitted_cum) AS submitted_mismatch,
       count(*) FILTER (WHERE abs(coalesce(scr.m, 0) - coalesce(snap.avg_score_cum, 0)) > 0.01) AS avg_score_mismatch
FROM snap
LEFT JOIN clk USING (code_module, code_presentation, id_student)
LEFT JOIN due_n USING (code_module, code_presentation)
LEFT JOIN cov USING (code_module, code_presentation, id_student)
LEFT JOIN scr USING (code_module, code_presentation, id_student);
SELECT count(*) AS snapshot_rows_on_or_after_unregistration
FROM dw.fact_student_week w JOIN dw.fact_enrollment f ON f.student_key = w.student_key AND f.offering_key = w.offering_key
WHERE f.unregistration_day_key > -9000 AND w.snapshot_day_key >= f.unregistration_day_key;
SELECT count(*) AS enrollments_without_any_snapshot,
       count(*) FILTER (WHERE f.unregistration_day_key BETWEEN -9000 AND 6) AS of_which_unregistered_by_day_6
FROM dw.fact_enrollment f
WHERE NOT EXISTS (SELECT 1 FROM dw.fact_student_week w WHERE w.student_key = f.student_key AND w.offering_key = f.offering_key);
SELECT count(*) AS unregistered_by_day_6 FROM dw.fact_enrollment WHERE unregistration_day_key BETWEEN -9000 AND 6;
SELECT count(*) AS empty_strings_left_in_staging_score FROM staging.student_assessment WHERE score = '';
"""), flush=True)

h("STORAGE")
print(db.psql("""SELECT c.relname, pg_size_pretty(pg_total_relation_size(c.oid)) AS total
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname IN ('dw','staging') AND c.relkind IN ('r','m') ORDER BY pg_total_relation_size(c.oid) DESC;"""), flush=True)
db.cleanup()
print("done", flush=True)
