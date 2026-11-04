"""Follow-up checks for the design decisions raised by profile_oulad.py.

Run:  python src/profiling/profile_followup.py data/raw > docs/profiling_followup.txt
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
ORDER = {"2013B": 0, "2013J": 1, "2014B": 2, "2014J": 3}
AGE = {"0-35": 0, "35-55": 1, "55<=": 2}


def h(title):
    print(f"\n{'=' * 8} {title} {'=' * 8}")


def read(name, **kw):
    return pd.read_csv(os.path.join(RAW, name + ".csv"), **kw)


courses = read("courses")
assess = read("assessments")
info = read("studentInfo", keep_default_na=False)
reg = read("studentRegistration")
sa = read("studentAssessment")
enr = info.merge(reg, on=ENR).merge(courses, on=OFFER)
LEN = "module_presentation_length"

h("AGE BAND CHANGES (SCD2 decision)")
info["o"] = info.code_presentation.map(ORDER)
info["a"] = info.age_band.map(AGE)
changed = info.groupby("id_student").age_band.nunique()
ids = changed[changed > 1].index
c = info[info.id_student.isin(ids)].sort_values(["id_student", "o"])
print("  students with a change:", len(ids))
same = c.groupby(["id_student", "code_presentation"]).age_band.nunique()
print("  different age_band inside one presentation:", int((same > 1).sum()))
step = c.groupby("id_student").a.diff().dropna()
print("  transitions:", step.value_counts().to_dict(), "(+1 = older band, -1 = younger band)")
print("  sample:", c[["id_student", "code_module", "code_presentation", "age_band"]].head(6).values.tolist())

h("STUDIED CREDITS (additivity)")
two = info.groupby(["id_student", "code_presentation"]).filter(lambda g: len(g) > 1)
n = two.groupby(["id_student", "code_presentation"]).studied_credits.nunique()
print("  (student,presentation) with >1 module:", len(n), " same credits on all rows:", int((n == 1).sum()))
print("  credits by count:", info.studied_credits.value_counts().head(8).to_dict())
print("  credits>240:", int((info.studied_credits > 240).sum()))

h("REGISTRATION EDGE CASES")
print("  null date_registration by result:", enr[enr.date_registration.isna()].final_result.value_counts().to_dict())
print("  null reg with unreg present:", int((enr.date_registration.isna() & enr.date_unregistration.notna()).sum()))
print("  Withdrawn w/o unreg date: modules", enr[(enr.final_result == "Withdrawn") & enr.date_unregistration.isna()].code_module.value_counts().to_dict())
wf = enr[(enr.final_result == "Fail") & enr.date_unregistration.notna()]
print("  Fail with unreg date:", wf[["date_unregistration", LEN]].values.tolist())
wd = enr[enr.date_unregistration.notna()]
print("  unreg share by phase:",
      {"before day 0 (<0)": int((wd.date_unregistration < 0).sum()),
       "day 0": int((wd.date_unregistration == 0).sum()),
       "day 1..27": int(wd.date_unregistration.between(1, 27).sum()),
       "day>=28": int((wd.date_unregistration >= 28).sum())})
print("  date_registration>unreg? none expected:", int((enr.date_registration > enr.date_unregistration).sum()))

h("IMD BAND MISSING")
t = pd.crosstab(info.region, info.imd_band == "")
t["missing_share"] = (t[True] / t.sum(axis=1)).round(3)
print(t.sort_values("missing_share", ascending=False).to_string())

h("ASSESSMENT TIMING")
s = sa.merge(assess, on="id_assessment").merge(courses, on=OFFER)
s["late"] = s.date_submitted - s.date
nb = s[s.is_banked == 0]
print(nb.groupby("assessment_type").late.describe(percentiles=[0.05, 0.5, 0.95]).round(1).to_string())
print("  late>0 share by type:", nb.assign(l=nb.late > 0).groupby("assessment_type").l.mean().round(3).to_dict())
print("  submitted after module end:", s[s.date_submitted > s[LEN]].assessment_type.value_counts().to_dict(),
      " max:", int(s.date_submitted.max()))
print("  exam date null submissions by assessment:",
      s[s.date.isna()].groupby("id_assessment").date_submitted.describe()[["count", "min", "50%", "max"]].to_dict("index"))
print("  exam date known, submission vs date:",
      s[(s.assessment_type == "Exam") & s.date.notna()].groupby("id_assessment").late.describe()[["count", "min", "50%", "max"]].to_dict("index"))
print("  score by exam module:", s[s.assessment_type == "Exam"].groupby("code_module").score.describe()[["count", "mean"]].round(1).to_dict("index"))

h("BANKED")
b = s[s.is_banked == 1].merge(info[ENR + ["num_of_prev_attempts", "final_result"]], on=ENR)
print("  rows:", len(b), " distinct enrollments:", len(b[ENR].drop_duplicates()),
      " with prev_attempts=0:", int((b.num_of_prev_attempts == 0).sum()))
print("  by type:", b.assessment_type.value_counts().to_dict())

h("SUBMISSIONS AFTER UNREGISTRATION")
m = s.merge(reg, on=ENR)
a = m[m.date_submitted > m.date_unregistration]
print("  rows:", len(a), " banked:", int((a.is_banked == 1).sum()),
      " days after unreg:", (a.date_submitted - a.date_unregistration).describe(percentiles=[0.5, 0.95]).round(1).to_dict())

h("WEIGHTS")
print("  weight=0 by type:", assess[assess.weight == 0].assessment_type.value_counts().to_dict())
print("  weight=0 by module:", assess[assess.weight == 0].code_module.value_counts().to_dict())

h("STUDENT VLE ROWS")
sv = read("studentVle", dtype={"code_module": "category", "code_presentation": "category",
                               "id_student": "int32", "id_site": "int32", "date": "int16", "sum_click": "int32"})
key = ["id_student", "id_site", "date"]
grp = sv.groupby(key, sort=False).sum_click
agg = grp.agg(["size", "nunique", "sum", "max"])
del grp
multi = agg[agg["size"] > 1]
print("  keys:", len(agg), " keys with several rows:", len(multi), " rows in those keys:", int(multi["size"].sum()))
print("  rows per key:", agg["size"].value_counts().sort_index().to_dict())
print("  of multi-row keys, all values identical:", int((multi["nunique"] == 1).sum()),
      " values differ:", int((multi["nunique"] > 1).sum()))
dup = sv.duplicated()
print("  exact duplicate rows:", int(dup.sum()), " clicks in them:", int(sv.loc[dup, "sum_click"].sum()),
      " share of all clicks:", round(float(sv.loc[dup, "sum_click"].sum() / sv.sum_click.sum()), 4))
print("  duplicate rows by value of sum_click:", sv.loc[dup, "sum_click"].clip(upper=6).value_counts().sort_index().to_dict())
print("  all rows by value of sum_click:", sv.sum_click.clip(upper=6).value_counts(normalize=True).round(3).sort_index().to_dict())
del dup, multi, agg

sv["code_module"] = sv.code_module.astype(str)
sv["code_presentation"] = sv.code_presentation.astype(str)
j = sv.merge(reg[ENR + ["date_unregistration"]], on=ENR, how="left")
after = j.date > j.date_unregistration
print("  rows after unreg:", int(after.sum()), " clicks:", int(j.loc[after, "sum_click"].sum()),
      " share:", round(float(j.loc[after, "sum_click"].sum() / j.sum_click.sum()), 5))
print("  days after unreg:", (j.loc[after, "date"] - j.loc[after, "date_unregistration"]).describe(percentiles=[0.5, 0.95]).round(1).to_dict())
del j, after

h("AT-RISK POPULATION BY WEEK (what the DSS can actually see)")
e = enr.copy()
e["at_risk"] = e.final_result.isin(["Fail", "Withdrawn"])
print("  overall:", len(e), " at-risk:", int(e.at_risk.sum()), " share:", round(float(e.at_risk.mean()), 3))
for w in [0, 4, 8, 12, 16, 20, 26]:
    day = 7 * w
    active = e[e.date_unregistration.isna() | (e.date_unregistration > day)]
    gone = len(e) - len(active)
    print(f"  end of week {w - 1 if w else 'pre'} (day<{day}): still registered={len(active)} "
          f"already withdrawn={gone} at-risk among active={active.at_risk.mean():.3f} "
          f"fail={(active.final_result == 'Fail').mean():.3f} later-withdraw={(active.final_result == 'Withdrawn').mean():.3f}")

h("WEEK RANGE AND DAY RANGE")
print("  day range over all date columns:", {
    "vle": (int(sv.date.min()), int(sv.date.max())),
    "reg": (int(reg.date_registration.min()), int(reg.date_registration.max())),
    "unreg": (int(reg.date_unregistration.min()), int(reg.date_unregistration.max())),
    "submitted": (int(sa.date_submitted.min()), int(sa.date_submitted.max())),
    "assessment_due": (int(assess.date.min()), int(assess.date.max())),
    "module_len": (int(courses[LEN].min()), int(courses[LEN].max())),
})
