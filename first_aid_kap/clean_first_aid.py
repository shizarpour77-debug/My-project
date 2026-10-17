"""Clean and code first-aid knowledge pre/post-test exports for SPSS.

Usage: python clean_first_aid.py PRETEST.xlsx POSTTEST.xlsx OUT_DIR

Input: two exports of the online test platform (one row per attempt,
36-item bank, 20 random items per attempt, score = number correct).
Output (OUT_DIR):
  first_aid_long.sav      every attempt, item responses coded, QC flags
  first_aid_paired.sav    one row per participant, pre/post side by side
  linkage_key.xlsx        study ID <-> national ID (confidential)
  codebook.xlsx           variables, answer key, item statistics
  cleaning_log.txt        counts for every cleaning step
No national IDs are written to the .sav files.
"""
import sys
from pathlib import Path

import jdatetime
import numpy as np
import pandas as pd
import pyreadstat

N_ITEMS = 36
ITEM_COLS = range(2, 2 + N_ITEMS)
SPEEDER_MIN = 2.0      # full test answered in < 2 min
LONG_MIN = 60.0        # attempt open > 60 min
STUDY_START, STUDY_END = pd.Timestamp("2026-01-20"), pd.Timestamp("2026-03-01")

# Keyed (scored-as-correct) option for each item, recovered from the data:
# it reproduces the platform score for 9,931 of 9,932 attempts.
# Item 25 differs between versions (pre asks when vomiting is REQUIRED,
# post asks when it is FORBIDDEN), so it has one key per phase.
KEY = {
    1: "فشار مستقیم", 2: "5تا 6 سانتیمتر", 3: "قسمت میانی استخوان جناغ",
    4: "نبض بازویی", 5: "بین 100تا 120", 6: "بیماریهای قلبی و عروقی",
    7: "ارزیابی ایمنی صحنه", 8: "30به 2", 9: "مسمومیت با مونواکسید کربن",
    10: "درجه 2", 11: "0 تا 10 دقیقه", 12: "عقب افتادن زبان",
    13: "خوابیده به پشت", 14: "توالی 5ضربه به پشت و 5 فشار شکمی",
    15: "ماساژ قلبی", 16: "کاروتید", 17: "استفاده از مانور هیملیچ",
    18: "20-12 تنفس", 19: "پرشدگی مویرگی",
    20: "یافتن و درمان تمامی عامل تهدید کننده حیات", 21: "دیابت",
    22: "اپی گلوت", 23: "بیهوش دارای نبض و نفس", 24: "تشویق به سرفه",
    25: {1: "دارو های قلبی وخواب آور", 2: "همه موارد"},
    26: "عدم تعادل", 27: "3 درصد", 28: "کمبود اکسیژن", 29: "ایمنی امدادگر",
    30: "همه موارد", 31: "بررسی ایمنی صحنه و تماس با ارگان های امدادی",
    32: "در بیمارستان و فقط توسط پزشک", 33: "همه موارد", 34: "راه هوایی",
    35: "عدم پاسخگویی بیمار", 36: "نگاه کردن به بالا و پایین رفتن قفسه سینه",
}
# Items with doubtful key / version change, left out of the sensitivity score.
DOUBTFUL = [3, 11, 25, 27, 34]
# Items whose keyed answer is clinically questionable or that changed
# between versions; reported in the codebook, not altered in scoring.
ITEM_NOTES = {
    3: "Key = mid-sternum; standard adult Heimlich hand position is between navel and xiphoid (the modal answer). Review key.",
    11: "Key = 0-10 min; most curricula teach 4-6 min. Review key.",
    25: "Different question pre (vomiting REQUIRED) vs post (vomiting FORBIDDEN); induced vomiting is no longer recommended. Exclude from pre/post comparison.",
    27: "Key = 3%; by the palm rule (1 palm ~ 1% TBSA) 2 palms = 2%. Negative item-rest correlation: likely mis-keyed.",
    34: "Key = airway; current BLS sequence is C-A-B. Ambiguous item.",
    35: "Key = 'patient unresponsive'; wording ambiguous.",
}

log = []


def note(msg):
    log.append(msg)
    print(msg)


def nid_valid(c):
    if not isinstance(c, str) or len(c) != 10 or not c.isdigit() or len(set(c)) == 1:
        return 0
    s = sum(int(c[i]) * (10 - i) for i in range(9)) % 11
    k = int(c[9])
    return int(k == s if s < 2 else k == 11 - s)


def jalali_to_dt(x):
    try:
        d, t = x.split("-")
        y, m, dd = map(int, d.split("/"))
        hh, mm, ss = map(int, t.split(":"))
        return jdatetime.datetime(y, m, dd, hh, mm, ss).togregorian()
    except (AttributeError, ValueError):
        return pd.NaT


def read_phase(path, phase):
    raw = pd.read_excel(path, dtype=str)
    questions = raw.iloc[0, 2:2 + N_ITEMS].str.replace("\xa0", " ").str.strip().tolist()
    d = raw.iloc[1:].reset_index(drop=True)
    note(f"[{'pre' if phase == 1 else 'post'}] rows read: {len(d)}")
    d = d[d.iloc[:, 0].notna()].copy()
    note(f"  rows with a national ID: {len(d)}")
    out = pd.DataFrame({
        "nid": d.iloc[:, 0].str.strip(),
        "region": d.iloc[:, 1].str.extract(r"(\d+)")[0].astype(float),
        "phase": phase,
        "start_jalali": d["تاریخ شروع"].str.replace("-", " "),
        "start_dt": pd.to_datetime(d["تاریخ شروع"].map(jalali_to_dt)),
        "end_dt": pd.to_datetime(d["تاریخ اتمام"].map(jalali_to_dt)),
        "score_platform": pd.to_numeric(d["امتیاز"], errors="coerce"),
    })
    resp = d.iloc[:, list(ITEM_COLS)].apply(lambda s: s.str.strip())
    resp.columns = range(1, N_ITEMS + 1)
    return out.reset_index(drop=True), resp.reset_index(drop=True), questions


def main(pre_path, post_path, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pre, pre_resp, q_pre = read_phase(pre_path, 1)
    post, post_resp, q_post = read_phase(post_path, 2)
    att = pd.concat([pre, post], ignore_index=True)
    resp = pd.concat([pre_resp, post_resp], ignore_index=True)

    # Option codes: 1 = keyed answer, 2-4 = distractors (fixed alphabetical order).
    option_labels, item_vars = {}, {}
    for i in range(1, N_ITEMS + 1):
        key_by_phase = KEY[i] if isinstance(KEY[i], dict) else {1: KEY[i], 2: KEY[i]}
        keys = set(key_by_phase.values())
        distractors = sorted(set(resp[i].dropna()) - keys)
        code_map = {o: c for c, o in enumerate(distractors, start=2)}
        codes = resp[i].map(code_map)
        for ph, k in key_by_phase.items():
            codes[(att.phase == ph) & (resp[i] == k)] = 1
        unmapped = resp[i].notna() & codes.isna()
        assert not unmapped.any(), f"item {i}: unmapped options {resp[i][unmapped].unique()}"
        r, c = f"Q{i:02d}_r", f"Q{i:02d}_c"
        item_vars[r] = codes.fillna(9)
        item_vars[c] = np.where(codes.isna(), np.nan, (codes == 1).astype(float))
        key_txt = " / ".join(f"{'pre' if p == 1 else 'post'}: {k}" for p, k in key_by_phase.items()) \
            if isinstance(KEY[i], dict) else KEY[i]
        option_labels[r] = {1.0: f"صحیح: {key_txt}"[:120],
                            **{float(c): o[:120] for o, c in code_map.items()},
                            9.0: "ارائه نشده/بی‌پاسخ"}
    items = pd.DataFrame(item_vars)
    att = pd.concat([att, items], axis=1)

    cor_cols = [f"Q{i:02d}_c" for i in range(1, N_ITEMS + 1)]
    att["n_answered"] = att[cor_cols].notna().sum(axis=1)
    att["score"] = att[cor_cols].sum(axis=1)
    mism = (att.score != att.score_platform).sum()
    note(f"recalculated score != platform score: {mism} attempt(s)")
    att["score_pct"] = att.score / 20 * 100
    att["pct_of_answered"] = np.where(att.n_answered > 0, att.score / att.n_answered.replace(0, np.nan) * 100, np.nan)
    excl = [c for c in cor_cols if c != "Q25_c"]
    n_ex = att[excl].notna().sum(axis=1)
    att["pct_excl_q25"] = np.where(n_ex > 0, att[excl].sum(axis=1) / n_ex.replace(0, np.nan) * 100, np.nan)
    core = [c for c in cor_cols if int(c[1:3]) not in DOUBTFUL]
    n_core = att[core].notna().sum(axis=1)
    att["pct_core"] = np.where(n_core > 0, att[core].sum(axis=1) / n_core.replace(0, np.nan) * 100, np.nan)
    att["know_cat"] = pd.cut(att.score_pct, [-1, 59.999, 79.999, 101], labels=[1, 2, 3]).astype(float)

    att["duration_min"] = ((att.end_dt - att.start_dt).dt.total_seconds() / 60).round(2)
    att["nid_valid"] = att.nid.map(nid_valid)
    att["flag_incomplete"] = ((att.n_answered > 0) & (att.n_answered < 20)).astype(int)
    att["flag_empty"] = (att.n_answered == 0).astype(int)
    att["flag_speeder"] = ((att.duration_min < SPEEDER_MIN) & (att.n_answered == 20)).astype(int)
    att["flag_long"] = (att.duration_min > LONG_MIN).astype(int)
    att["flag_outside_period"] = ((att.start_dt < STUDY_START) | (att.start_dt >= STUDY_END)).astype(int)

    # Attempt order within person and phase.
    att = att.sort_values(["nid", "phase", "start_dt"]).reset_index(drop=True)
    att["attempt_no"] = att.groupby(["nid", "phase"]).cumcount() + 1
    att["n_attempts"] = att.groupby(["nid", "phase"]).phase.transform("size")

    # Selection: pre = first non-empty pre attempt;
    # post = first post attempt starting after the selected pre (else first post).
    att["selected"] = 0
    sel_pre = att[(att.phase == 1) & (att.n_answered > 0)].groupby("nid").head(1)
    att.loc[sel_pre.index, "selected"] = 1
    pre_start = sel_pre.set_index("nid").start_dt
    post = att[att.phase == 2].copy()
    post["pre_start"] = post.nid.map(pre_start)
    after = post[post.pre_start.isna() | (post.start_dt > post.pre_start)].groupby("nid").head(1)
    att.loc[after.index, "selected"] = 1
    only_before = set(post.nid[post.pre_start.notna()]) - set(after.nid)
    note(f"participants whose only post-tests precede their pre-test (post not used): {len(only_before)}")

    # Pseudonymised study ID.
    ids = sorted(att.nid.unique())
    pid_map = {n: i + 1 for i, n in enumerate(ids)}
    att.insert(0, "pid", att.nid.map(pid_map))
    att.insert(1, "attempt_id", np.arange(1, len(att) + 1))

    # Region conflicts.
    reg_n = att.groupby("pid").region.nunique()
    att["flag_region_conflict"] = att.pid.isin(reg_n[reg_n > 1].index).astype(int)

    for ph, nm in [(1, "pre"), (2, "post")]:
        s = att[att.phase == ph]
        note(f"[{nm}] attempts {len(s)} | persons {s.pid.nunique()} | repeat-attempt persons "
             f"{(s.groupby('pid').size() > 1).sum()} | empty {s.flag_empty.sum()} | incomplete "
             f"{s.flag_incomplete.sum()} | speeders {s.flag_speeder.sum()} | >60 min {s.flag_long.sum()} | "
             f"outside Jan-Feb 2026 {s.flag_outside_period.sum()} | invalid NID checksum {(s.nid_valid == 0).sum()}")

    # ---------- paired (wide) file ----------
    sel = att[att.selected == 1]
    keep = ["start_dt", "start_jalali", "duration_min", "n_answered", "score", "score_pct",
            "pct_of_answered", "pct_excl_q25", "pct_core", "know_cat", "n_attempts", "flag_incomplete",
            "flag_speeder", "flag_long", "flag_outside_period"] + cor_cols
    w_pre = sel[sel.phase == 1].set_index("pid")[keep].add_prefix("pre_")
    w_post = sel[sel.phase == 2].set_index("pid")[keep].add_prefix("post_")
    base = att.sort_values(["phase", "start_dt"]).groupby("pid").agg(
        region=("region", "first"), nid_valid=("nid_valid", "first"),
        flag_region_conflict=("flag_region_conflict", "max"))
    wide = base.join(w_pre, how="left").join(w_post, how="left")
    wide["has_pre"] = wide.pre_score.notna().astype(int)
    wide["has_post"] = wide.post_score.notna().astype(int)
    wide["matched"] = (wide.has_pre & wide.has_post).astype(int)
    wide["score_change"] = wide.post_score - wide.pre_score
    wide["pct_change_excl_q25"] = wide.post_pct_excl_q25 - wide.pre_pct_excl_q25
    wide["pct_change_core"] = wide.post_pct_core - wide.pre_pct_core
    wide["gap_hours"] = ((wide.post_start_dt - wide.pre_start_dt).dt.total_seconds() / 3600).round(2)
    wide["analysable"] = ((wide.matched == 1) & (wide.pre_n_answered == 20) & (wide.post_n_answered == 20)
                          & (wide.pre_flag_speeder == 0) & (wide.post_flag_speeder == 0)).astype(int)
    wide = wide.reset_index()
    note(f"participants: {len(wide)} | pre only {((wide.has_pre == 1) & (wide.has_post == 0)).sum()} | "
         f"post only {((wide.has_pre == 0) & (wide.has_post == 1)).sum()} | matched {wide.matched.sum()} | "
         f"analysable (matched, both complete, no speeders) {wide.analysable.sum()}")

    # ---------- labels ----------
    yn = {0.0: "خیر", 1.0: "بله"}
    region_lab = {float(r): f"منطقه {r}" for r in range(1, 23)}
    cat_lab = {1.0: "ضعیف (<60%)", 2.0: "متوسط (60-79%)", 3.0: "خوب (≥80%)"}
    vlab = {"pid": "Study ID (pseudonymised)", "attempt_id": "Attempt ID",
            "region": "محل خدمت (منطقه)", "phase": "Test phase",
            "start_jalali": "Start date-time (Jalali)", "start_dt": "Start date-time (Gregorian)",
            "end_dt": "End date-time (Gregorian)", "score_platform": "Score reported by platform",
            "n_answered": "Items answered (of 20 presented)", "score": "Correct answers (0-20)",
            "score_pct": "Score % (correct/20)", "pct_of_answered": "% correct of answered items",
            "pct_excl_q25": "% correct of answered items, excluding Q25",
            "pct_core": "% correct of answered items, excluding doubtful items Q03 Q11 Q25 Q27 Q34",
            "pct_change_core": "Post minus pre %, excluding doubtful items",
            "know_cat": "Knowledge level (Bloom cut-offs)", "duration_min": "Attempt duration (min)",
            "nid_valid": "National ID passes checksum", "flag_incomplete": "Answered 1-19 items",
            "flag_empty": "No items answered", "flag_speeder": "20 items in <2 min",
            "flag_long": "Attempt open >60 min", "flag_outside_period": "Outside main period (Jan-Feb 2026)",
            "attempt_no": "Attempt number within phase", "n_attempts": "Attempts in this phase",
            "selected": "Attempt used in paired file", "flag_region_conflict": "Different region across attempts",
            "has_pre": "Has pre-test", "has_post": "Has post-test", "matched": "Has both pre and post",
            "score_change": "Post minus pre score", "pct_change_excl_q25": "Post minus pre %, excl. Q25",
            "gap_hours": "Hours between pre and post", "analysable": "Matched, both complete, no speeders"}
    qtext = {i + 1: q for i, q in enumerate(q_post)}
    for i in range(1, N_ITEMS + 1):
        vlab[f"Q{i:02d}_r"] = f"Q{i:02d} response: {qtext[i]}"[:250]
        vlab[f"Q{i:02d}_c"] = f"Q{i:02d} correct: {qtext[i]}"[:250]
    vlab["Q25_r"] = vlab["Q25_c"] = "Q25 vomiting item (pre: REQUIRED / post: FORBIDDEN versions differ)"
    val = {"region": region_lab, "phase": {1.0: "پیش‌آزمون", 2.0: "پس‌آزمون"}, "know_cat": cat_lab,
           **option_labels}
    for v in ["nid_valid", "flag_incomplete", "flag_empty", "flag_speeder", "flag_long", "flag_outside_period",
              "selected", "flag_region_conflict", "has_pre", "has_post", "matched", "analysable"]:
        val[v] = yn
    for c in cor_cols:
        val[c] = {0.0: "غلط", 1.0: "صحیح"}

    long_cols = ["pid", "attempt_id", "phase", "attempt_no", "n_attempts", "selected", "region",
                 "nid_valid", "flag_region_conflict", "start_jalali", "start_dt", "end_dt", "duration_min",
                 "n_answered", "score", "score_platform", "score_pct", "pct_of_answered", "pct_excl_q25", "pct_core",
                 "know_cat", "flag_empty", "flag_incomplete", "flag_speeder", "flag_long",
                 "flag_outside_period"] + [f"Q{i:02d}_{s}" for s in "rc" for i in range(1, N_ITEMS + 1)]
    long_df = att[long_cols].copy()
    pyreadstat.write_sav(
        long_df, out_dir / "first_aid_long.sav",
        column_labels={c: vlab.get(c, c) for c in long_cols},
        variable_value_labels={k: v for k, v in val.items() if k in long_cols},
        missing_ranges={f"Q{i:02d}_r": [9] for i in range(1, N_ITEMS + 1)},
        variable_measure={**{c: "nominal" for c in long_cols if c.endswith("_r") or c.startswith("flag")
                             or c in ("region", "phase", "selected", "nid_valid")},
                          "know_cat": "ordinal"},
        variable_display_width={"start_jalali": 20})

    def wlab(c):
        for p, t in (("pre_", "Pre: "), ("post_", "Post: ")):
            if c.startswith(p):
                return t + vlab.get(c[len(p):], c[len(p):])
        return vlab.get(c, c)

    def wval(c):
        for p in ("pre_", "post_"):
            if c.startswith(p) and c[len(p):] in val:
                return val[c[len(p):]]
        return val.get(c)

    wide_cols = (["pid", "region", "nid_valid", "flag_region_conflict", "has_pre", "has_post", "matched",
                  "analysable", "gap_hours", "score_change", "pct_change_excl_q25", "pct_change_core"]
                 + [c for c in wide.columns if c.startswith("pre_")]
                 + [c for c in wide.columns if c.startswith("post_")])
    wide = wide[wide_cols]
    pyreadstat.write_sav(
        wide, out_dir / "first_aid_paired.sav",
        column_labels={c: wlab(c)[:250] for c in wide_cols},
        variable_value_labels={c: wval(c) for c in wide_cols if wval(c)},
        variable_measure={c: "nominal" for c in wide_cols if wval(c) and not c.endswith("know_cat")})

    # ---------- linkage key (confidential) ----------
    key_df = att.groupby("pid").agg(national_id=("nid", "first"), nid_valid=("nid_valid", "first")).reset_index()
    key_df.to_excel(out_dir / "linkage_key_CONFIDENTIAL.xlsx", index=False)

    # ---------- codebook ----------
    item_rows = []
    m = wide[wide.analysable == 1]
    for i in range(1, N_ITEMS + 1):
        c = f"Q{i:02d}_c"
        row = {"item": f"Q{i:02d}", "question (post version)": q_post[i - 1],
               "key": KEY[i] if not isinstance(KEY[i], dict) else f"pre: {KEY[i][1]} | post: {KEY[i][2]}"}
        for ph, nm in [(1, "pre"), (2, "post")]:
            s = att[(att.phase == ph) & (att.selected == 1)]
            row[f"{nm}_n"] = int(s[c].notna().sum())
            row[f"{nm}_%correct"] = round(s[c].mean() * 100, 1)
            ok = s[c].notna()
            rest = s.score[ok] - s[c][ok]
            row[f"{nm}_item-rest r"] = round(np.corrcoef(s[c][ok], rest)[0, 1], 2)
        both = m[[f"pre_{c}", f"post_{c}"]].dropna()
        row["paired_n (both phases)"] = len(both)
        row["note"] = ITEM_NOTES.get(i, "")
        if q_pre[i - 1] != q_post[i - 1]:
            row["note"] = (row["note"] + " Pre wording: " + q_pre[i - 1]).strip()
        item_rows.append(row)
    cb_long = pd.DataFrame({"variable": long_cols, "label": [vlab.get(c, c) for c in long_cols],
                            "values": [str(val.get(c, "")) for c in long_cols]})
    cb_wide = pd.DataFrame({"variable": wide_cols, "label": [wlab(c) for c in wide_cols],
                            "values": [str(wval(c) or "") for c in wide_cols]})
    with pd.ExcelWriter(out_dir / "codebook.xlsx") as xw:
        pd.DataFrame(item_rows).to_excel(xw, sheet_name="items_answer_key", index=False)
        cb_long.to_excel(xw, sheet_name="vars_long", index=False)
        cb_wide.to_excel(xw, sheet_name="vars_paired", index=False)
        pd.DataFrame({"step": log}).to_excel(xw, sheet_name="cleaning_log", index=False)
    (out_dir / "cleaning_log.txt").write_text("\n".join(log), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:4])
