"""Profile the 7 raw OULAD CSV files. Every number in the design documents comes from here.

Run:  python src/profiling/profile_oulad.py data/raw > docs/profiling_output.txt
"""
import os
import site
import sys

sys.path.append(site.getusersitepackages())
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
RAW = sys.argv[1]
ENR = ["code_module", "code_presentation", "id_student"]
OFFER = ["code_module", "code_presentation"]
MISSING_TOKENS = {"", "?", "NA", "N/A", "null", "NULL", "None", "nan"}


def h(title):
    print(f"\n{'=' * 8} {title} {'=' * 8}")


def load_text(name):
    return pd.read_csv(os.path.join(RAW, name + ".csv"), dtype=str, keep_default_na=False)


def to_int(s):
    return pd.to_numeric(s.where(s != ""), errors="coerce")


def column_report(df):
    for c in df.columns:
        s = df[c]
        tokens = s[s.isin(MISSING_TOKENS)].value_counts().to_dict()
        untrimmed = int((s != s.str.strip()).sum())
        line = f"  {c}: distinct={s.nunique()} missing_tokens={tokens} untrimmed={untrimmed}"
        if s.nunique() <= 25:
            line += f"\n      values={s.value_counts().to_dict()}"
        print(line)


def pk_check(df, keys, label):
    print(f"  PK {label} {keys}: rows={len(df)} duplicates={int(df.duplicated(keys).sum())}")


def orphans(child, parent, keys, label):
    p = parent[keys].drop_duplicates()
    m = child[keys].drop_duplicates().merge(p, on=keys, how="left", indicator=True)
    print(f"  FK {label}: distinct_keys={len(m)} orphans={int((m['_merge'] == 'left_only').sum())}")


def num_summary(s, label):
    d = s.describe(percentiles=[0.01, 0.5, 0.99])
    print(f"  {label}: n={int(d['count'])} null={int(s.isna().sum())} min={d['min']:.0f} "
          f"p1={d['1%']:.0f} p50={d['50%']:.0f} p99={d['99%']:.0f} max={d['max']:.0f}")


courses = load_text("courses")
assess = load_text("assessments")
vle = load_text("vle")
info = load_text("studentInfo")
reg = load_text("studentRegistration")
sa = load_text("studentAssessment")

for name, df in [("courses", courses), ("assessments", assess), ("vle", vle),
                 ("studentInfo", info), ("studentRegistration", reg), ("studentAssessment", sa)]:
    h(f"COLUMNS {name} ({len(df)} rows)")
    column_report(df)

h("PRIMARY KEYS")
pk_check(courses, OFFER, "courses")
pk_check(assess, ["id_assessment"], "assessments")
pk_check(vle, ["id_site"], "vle")
pk_check(info, ENR, "studentInfo")
pk_check(reg, ENR, "studentRegistration")
pk_check(sa, ["id_assessment", "id_student"], "studentAssessment")

h("COURSES")
courses["len"] = to_int(courses["module_presentation_length"])
print(courses.pivot(index="code_module", columns="code_presentation", values="len").to_string())

h("ASSESSMENTS")
assess["date_i"] = to_int(assess["date"])
assess["weight_i"] = to_int(assess["weight"])
a = assess.merge(courses[OFFER + ["len"]], on=OFFER)
print("  null date by type:", a[a.date_i.isna()].assessment_type.value_counts().to_dict())
print("  date > module length:", int((a.date_i > a.len).sum()))
print("  date<0:", int((a.date_i < 0).sum()))
w = a.pivot_table(index=OFFER, columns="assessment_type", values="weight_i", aggfunc="sum").fillna(0)
w["total"] = w.sum(axis=1)
print(w.to_string())
print(a.pivot_table(index=OFFER, columns="assessment_type", values="id_assessment", aggfunc="count").fillna(0).astype(int).to_string())

h("STUDENT INFO")
print("  enrollments:", len(info), " distinct students:", info.id_student.nunique())
per = info.groupby("id_student").size()
print("  enrollments per student:", per.value_counts().sort_index().to_dict())
same_offer = info.groupby(["id_student", "code_presentation"]).size()
print("  students taking >1 module in same presentation:", int((same_offer > 1).sum()))
same_mod = info.groupby(["id_student", "code_module"]).size()
print("  (student,module) with >1 presentation:", int((same_mod > 1).sum()))
for c in ["gender", "region", "highest_education", "imd_band", "age_band", "disability"]:
    n = info.groupby("id_student")[c].nunique()
    print(f"  attribute changes across enrollments: {c}: students_with_>1_value={int((n > 1).sum())}")
attrs = ["gender", "region", "highest_education", "imd_band", "age_band", "disability"]
print("  distinct attribute combinations (student profile):", len(info[attrs].drop_duplicates()))
print("  distinct student+profile versions:", len(info[["id_student"] + attrs].drop_duplicates()))
print("  num_of_prev_attempts:", info.num_of_prev_attempts.value_counts().sort_index().to_dict())
num_summary(to_int(info.studied_credits), "studied_credits")
print(pd.crosstab(info.code_module, info.final_result, margins=True).to_string())
print(pd.crosstab(info.code_presentation, info.final_result, margins=True).to_string())
print("  module x presentation enrollments:")
print(info.pivot_table(index="code_module", columns="code_presentation", values="id_student", aggfunc="count").to_string())

# does num_of_prev_attempts agree with earlier rows in the dataset?
order = {"2013B": 0, "2013J": 1, "2014B": 2, "2014J": 3}
t = info.assign(o=info.code_presentation.map(order), pa=to_int(info.num_of_prev_attempts))
t = t.sort_values(["id_student", "code_module", "o"])
t["seen"] = t.groupby(["id_student", "code_module"]).cumcount()
print("  prev_attempts vs earlier rows in dataset:",
      {"equal": int((t.pa == t.seen).sum()), "attempts>seen": int((t.pa > t.seen).sum()),
       "attempts<seen": int((t.pa < t.seen).sum())})

h("REGISTRATION")
reg["r"] = to_int(reg.date_registration)
reg["u"] = to_int(reg.date_unregistration)
num_summary(reg.r, "date_registration")
num_summary(reg.u, "date_unregistration")
orphans(reg, info, ENR, "registration->studentInfo")
orphans(info, reg, ENR, "studentInfo->registration")
r = reg.merge(info[ENR + ["final_result"]], on=ENR).merge(courses[OFFER + ["len"]], on=OFFER)
print("  unregistered by final_result:", r[r.u.notna()].final_result.value_counts().to_dict())
print("  not unregistered by final_result:", r[r.u.isna()].final_result.value_counts().to_dict())
print("  unreg<=0 (quit before start):", int((r.u <= 0).sum()),
      " unreg<reg:", int((r.u < r.r).sum()), " unreg>length:", int((r.u > r.len).sum()),
      " reg>0 (registered after start):", int((r.r > 0).sum()))
print("  unreg week histogram (Withdrawn):",
      ((r.u.dropna() // 7).clip(-5, 40).astype(int)).value_counts().sort_index().to_dict())

h("VLE SITES")
orphans(vle, courses, OFFER, "vle->courses")
print("  activity_type:", vle.activity_type.value_counts().to_dict())
print("  week_from filled:", int((vle.week_from != "").sum()), "of", len(vle))
print("  sites per offering:", vle.groupby(OFFER).size().to_dict())
print(pd.crosstab(vle.code_module, vle.activity_type).to_string())

h("STUDENT ASSESSMENT")
sa["sub"] = to_int(sa.date_submitted)
sa["score_i"] = to_int(sa.score)
orphans(sa, assess, ["id_assessment"], "sa->assessments")
s = sa.merge(assess[OFFER + ["id_assessment", "assessment_type", "date_i", "weight_i"]], on="id_assessment")
orphans(s, info, ENR, "sa->studentInfo (via assessment's offering)")
num_summary(s.score_i, "score")
num_summary(s["sub"], "date_submitted")
print("  score out of [0,100]:", int(((s.score_i < 0) | (s.score_i > 100)).sum()))
print("  is_banked:", s.is_banked.value_counts().to_dict())
print("  submissions by type:", s.assessment_type.value_counts().to_dict())
print("  null score by type:", s[s.score_i.isna()].assessment_type.value_counts().to_dict())
print("  banked date_submitted: ", s[s.is_banked == "1"]["sub"].describe()[["min", "50%", "max"]].to_dict())
print("  banked in row with null score:", int((s.is_banked.eq("1") & s.score_i.isna()).sum()))
late = s["sub"] - s.date_i
print("  days late (non-banked): ", late[s.is_banked == "0"].describe(percentiles=[0.01, 0.5, 0.99]).round(1).to_dict())
print("  late>0 share (non-banked):", round(float((late[s.is_banked == "0"] > 0).mean()), 4))
print("  exam rows per offering:")
ex = a[a.assessment_type == "Exam"][OFFER + ["id_assessment", "date_i", "weight_i"]]
cnt = s[s.assessment_type == "Exam"].groupby("id_assessment").size()
ex = ex.assign(submissions=ex.id_assessment.map(cnt).fillna(0).astype(int))
print(ex.to_string(index=False))
# submissions after withdrawal
m = s.merge(reg[ENR + ["u"]], on=ENR, how="left")
print("  submissions after unregistration:", int((m["sub"] > m.u).sum()))
# assessments with zero submissions (non exam)
no = set(assess.id_assessment) - set(sa.id_assessment)
print("  assessments with zero submissions:", sorted(no))
print("  enrollments with no submission at all:",
      len(info[ENR].merge(s[ENR].drop_duplicates(), on=ENR, how="left", indicator=True).query("_merge=='left_only'")))

h("STUDENT VLE (10.6M)")
sv = pd.read_csv(os.path.join(RAW, "studentVle.csv"),
                 dtype={"code_module": "category", "code_presentation": "category",
                        "id_student": "int32", "id_site": "int32", "date": "int16", "sum_click": "int32"})
print("  rows:", len(sv), " nulls:", sv.isna().sum().to_dict())
num_summary(sv.sum_click, "sum_click")
num_summary(sv.date, "date")
print("  sum_click total:", int(sv.sum_click.sum()), " sum_click<=0:", int((sv.sum_click <= 0).sum()))
print("  exact duplicate rows:", int(sv.duplicated().sum()))
g = sv.groupby(["code_module", "code_presentation", "id_student", "id_site", "date"], observed=True)["sum_click"].size()
print("  distinct student x site x day:", len(g), " avg rows per key:", round(len(sv) / len(g), 3), " max rows per key:", int(g.max()))
del g
print("  distinct student x day:", len(sv[["code_module", "code_presentation", "id_student", "date"]].drop_duplicates()))
sv["week"] = (sv.date // 7).astype("int16")
print("  distinct enrollment x week:", len(sv[["code_module", "code_presentation", "id_student", "week"]].drop_duplicates()))
site_type = vle.assign(id_site=vle.id_site.astype("int32")).set_index("id_site")["activity_type"]
sv["activity_type"] = sv.id_site.map(site_type).astype("category")
print("  sites missing from vle.csv:", int(sv.activity_type.isna().sum()))
print("  distinct enrollment x week x activity:",
      len(sv[["code_module", "code_presentation", "id_student", "week", "activity_type"]].drop_duplicates()))
print("  distinct offering x week x activity:",
      len(sv[["code_module", "code_presentation", "week", "activity_type"]].drop_duplicates()))
print("  rows by offering:", sv.groupby(OFFER, observed=True).size().to_dict())
print("  clicks by activity:", sv.groupby("activity_type", observed=True).sum_click.sum().sort_values(ascending=False).to_dict())

# FK against vle (site must belong to the same offering) and against enrollments
sites = vle.assign(id_site=vle.id_site.astype("int32"))[["id_site", "code_module", "code_presentation"]]
pairs = sv[["id_site", "code_module", "code_presentation"]].drop_duplicates().astype({"code_module": str, "code_presentation": str})
x = pairs.merge(sites, on=["id_site", "code_module", "code_presentation"], how="left", indicator=True)
print("  distinct site/offering pairs:", len(pairs), " not in vle.csv:", int((x._merge == "left_only").sum()))
print("  sites never clicked:", len(set(sites.id_site) - set(pairs.id_site)))
en = sv[ENR].drop_duplicates().astype({"code_module": str, "code_presentation": str})
info_int = info[ENR].assign(id_student=info.id_student.astype("int32"))
x = en.merge(info_int, on=ENR, how="left", indicator=True)
print("  enrollments in VLE:", len(en), " not in studentInfo:", int((x._merge == "left_only").sum()))
x = info_int.merge(en, on=ENR, how="left", indicator=True)
no_click = x[x._merge == "left_only"][ENR]
fr = no_click.merge(info[ENR + ["final_result"]].assign(id_student=info.id_student.astype("int32")), on=ENR)
print("  enrollments with zero VLE rows:", len(no_click), fr.final_result.value_counts().to_dict())

# activity outside the enrollment window: this is the leakage risk for the DSS
reg_int = reg.assign(id_student=reg.id_student.astype("int32"))[ENR + ["r", "u"]]
per_enr = sv.groupby(ENR, observed=True).date.agg(["min", "max"]).reset_index().astype({"code_module": str, "code_presentation": str})
pe = per_enr.merge(reg_int, on=ENR).merge(courses[OFFER + ["len"]], on=OFFER)
print("  enrollments: last click after unregistration:", int((pe["max"] > pe.u).sum()),
      " first click before registration:", int((pe["min"] < pe.r).sum()),
      " click after module end:", int((pe["max"] > pe.len).sum()))
print("  clicks before day 0 share:", round(float(sv.loc[sv.date < 0, "sum_click"].sum() / sv.sum_click.sum()), 4))

h("ROW ESTIMATE: fact_student_week if densified")
pe2 = info[ENR].merge(courses[OFFER + ["len"]], on=OFFER)
print("  enrollment x every week of the module:", int(np.ceil(pe2.len / 7).sum()))
