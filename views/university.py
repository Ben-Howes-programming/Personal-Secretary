"""
university.py
=============
Purpose : Deadlines, marks against your 75% target, study time, and a review
          queue that brings each lecture back before you forget it.
Location: views/university.py
Tokens  : None. Everything on this page is arithmetic on what you enter.
"""

import time as clock
from datetime import date, timedelta

import streamlit as st

import config
from database import university
from ui import state
from ui import theme as ui

today = state.now().date()
target = config.DEGREE_TARGET
ui.header("University", f"Second year, aiming for {target:g}% or better.")

modules = university.list_modules()
module_names = {m["id"]: m["name"] for m in modules}
assessments = university.list_assessments()
open_work = [a for a in assessments if a["status"] != "done"]
reviews = university.reviews_due(today)
week_minutes = sum(row["minutes"] for row in university.study_minutes(7))

# Credit-weighted average across modules that have marked work
standings = {m["id"]: university.module_standing([a for a in assessments if a["module_id"] == m["id"]], target) for m in modules}
marked = [(m, standings[m["id"]]) for m in modules if standings[m["id"]]["average"] is not None]
overall = None
if marked:
    weights = [(m["credits"] or 1) for m, _s in marked]
    overall = sum(w * s["average"] for w, (_m, s) in zip(weights, marked)) / sum(weights)

next_due = next((a for a in open_work if a.get("due")), None)
ui.kpis([
    ("average so far", f"{overall:.1f}%" if overall is not None else "no marks yet",
     f"{overall - target:+.1f} against target" if overall is not None else "", "good" if (overall or 0) >= target else "bad"),
    ("open deadlines", len(open_work)),
    ("next deadline", ui.days_until(next_due["due"], today) if next_due else "none set", next_due["title"] if next_due else ""),
    ("study this week", f"{week_minutes / 60:.1f} h"),
    ("lecture reviews due", len(reviews), "do these first" if reviews else "", "warn"),
])

deadlines, marks, study, lectures, setup = st.tabs(["Deadlines", "Marks and targets", "Study time", "Lectures", "Modules"])

# ------------------------------------------------------------------
with deadlines:
    with st.form("new_assessment", clear_on_submit=True):
        a, b, c, d = st.columns([2.5, 1.6, 1.2, 1])
        title = a.text_input("Coursework, test or exam", placeholder="Problem sheet 4")
        module = b.selectbox("Module", modules, format_func=lambda m: m["name"])
        due = c.date_input("Due", value=None)
        weight = d.number_input("Worth % of module", value=None, min_value=0.0, max_value=100.0, step=5.0)
        if ui.submit("Add deadline", type="primary") and title.strip() and module:
            university.add_assessment(module["id"], title.strip(), due.isoformat() if due else None, weight)
            st.rerun()

    if not open_work:
        ui.empty("No open deadlines.", "Add coursework and exams above. They also appear on the Today page.")
    for item in open_work:
        text_col, mark_col, save_col, delete_col = st.columns([5, 1.3, 1, 1], vertical_alignment="center")
        gap = (date.fromisoformat(item["due"]) - today).days if item.get("due") else None
        tone = None if gap is None else ("bad" if gap <= 3 else ("warn" if gap <= 10 else None))
        worth = f", worth {item['weight']:g}%" if item.get("weight") else ""
        with text_col:
            ui.rows([ui.row(item["title"], f"{item['module'] or 'No module'}{worth}",
                            f"{item['due']}, {ui.days_until(item['due'], today)}" if item.get("due") else "no date", tone=tone)])
        mark = mark_col.number_input("Mark %", value=None, min_value=0.0, max_value=100.0, step=1.0,
                                     key=f"mark_{item['id']}", label_visibility="collapsed", placeholder="Mark %")
        if save_col.button("Done", key=f"done_{item['id']}", help="Marks it finished. Add the mark now or later."):
            if mark is not None:
                university.set_mark(item["id"], mark)
            else:
                university.set_assessment_status(item["id"], "done")
            st.rerun()
        if delete_col.button("Remove", key=f"del_{item['id']}"):
            university.delete_assessment(item["id"])
            st.rerun()

# ------------------------------------------------------------------
with marks:
    ui.muted("For each module: your average on marked work, and the average you need on what is left to finish on target.")
    st.latex(r"\text{needed} = \frac{T\sum w_i \;-\; \sum_{\text{marked}} w_i m_i}{\sum_{\text{unmarked}} w_i}")
    table = []
    for module in modules:
        standing = standings[module["id"]]
        needed = standing["needed"]
        if needed is None:
            verdict = "all marked" if standing["total_weight"] else "add weights"
        elif needed > 100:
            verdict = "target out of reach on these weights"
        elif needed <= 0:
            verdict = "target already secured"
        else:
            verdict = f"need {needed:.0f}% on the rest"
        table.append({"Module": module["name"], "Credits": module["credits"],
                      "Average so far %": round(standing["average"], 1) if standing["average"] is not None else None,
                      "Marked % of module": standing["done_weight"], "Verdict": verdict})
    ui.table(table)
    finished = [a for a in assessments if a["status"] == "done"]
    if finished:
        ui.section("Marked work")
        for item in finished:
            text_col, mark_col, save_col = st.columns([5, 1.3, 1], vertical_alignment="center")
            with text_col:
                ui.rows([ui.row(item["title"], item["module"] or "", f"{item['mark']:g}%" if item["mark"] is not None else "no mark yet",
                                tone=None if item["mark"] is None else ("good" if item["mark"] >= target else "warn"))])
            new_mark = mark_col.number_input("Mark %", value=item["mark"], min_value=0.0, max_value=100.0, step=1.0,
                                             key=f"edit_{item['id']}", label_visibility="collapsed")
            if save_col.button("Save", key=f"save_{item['id']}") and new_mark is not None:
                university.set_mark(item["id"], new_mark)
                st.rerun()

# ------------------------------------------------------------------
with study:
    timer_col, manual_col = st.columns(2, gap="large")
    with timer_col:
        ui.section("Focus timer")
        running = st.session_state.get("focus_start")
        focus_module = st.selectbox("Module", modules, format_func=lambda m: m["name"], key="focus_module")
        if running:
            elapsed = (clock.time() - running) / 60
            ui.note("accent", f"Focus block running: {elapsed:.0f} minutes. Phone in another room.")
            if st.button("Stop and log it", type="primary"):
                university.log_study(focus_module["id"] if focus_module else None, round(elapsed), "Focus timer")
                st.session_state.pop("focus_start")
                st.rerun()
            st.button("Update the clock")
        elif st.button("Start a focus block", type="primary"):
            st.session_state["focus_start"] = clock.time()
            st.rerun()
        ui.muted("Aim for 25 to 50 minutes on one task, then a 5 to 10 minute break away from the screen.")
    with manual_col:
        ui.section("Log study by hand")
        with st.form("study_form", clear_on_submit=True):
            study_module = st.selectbox("Module", modules, format_func=lambda m: m["name"])
            a, b = st.columns(2)
            minutes = a.number_input("Minutes", value=45, min_value=5, step=5)
            on = b.date_input("Date", value=today)
            if ui.submit("Log it"):
                university.log_study(study_module["id"] if study_module else None, minutes, "", on.isoformat())
                st.rerun()

    ui.section("Hours by week and module")
    rows = university.study_minutes(56)
    if rows:
        totals = {}
        for row in rows:
            monday = (date.fromisoformat(row["date"]) - timedelta(days=date.fromisoformat(row["date"]).weekday())).isoformat()
            totals[(monday, row["module"])] = totals.get((monday, row["module"]), 0) + row["minutes"] / 60
        ui.bar_chart([{"label": week[5:], "value": hours, "series": module} for (week, module), hours in sorted(totals.items())],
                     y_title="Hours", order=[m["name"] for m in modules] + ["General"])
        per_module = {}
        for row in university.study_minutes(14):
            per_module[row["module"]] = per_module.get(row["module"], 0) + row["minutes"]
        neglected = [m["name"] for m in modules if per_module.get(m["name"], 0) < 60]
        if neglected:
            ui.note("warn", "Under an hour in the last two weeks: " + ", ".join(neglected) + ".")
    else:
        ui.empty("No study logged yet.", "Use the timer or log a session by hand.")

# ------------------------------------------------------------------
with lectures:
    ui.note("info", "A routine for lectures that are hard to follow: skim the notes for ten minutes beforehand and write down two questions; "
                    "during the lecture, listen for the answers instead of copying everything; straight after, close your notes and write "
                    "what you remember for five minutes. Then log it here and the review queue does the rest.")
    with st.form("lecture_form", clear_on_submit=True):
        a, b, c = st.columns([1.5, 3, 1.5])
        lecture_module = a.selectbox("Module", modules, format_func=lambda m: m["name"], key="lecture_module")
        topic = b.text_input("Topic", placeholder="Partition function for a two-level system")
        understanding = c.slider("How well did you follow it?", 1, 5, 3)
        if ui.submit("Log lecture", type="primary") and topic.strip() and lecture_module:
            university.log_lecture(lecture_module["id"], topic.strip(), understanding)
            st.rerun()

    ui.section(f"Reviews due ({len(reviews)})")
    if not reviews:
        ui.empty("Nothing to review today.")
    for lecture in reviews:
        text_col, score_col, done_col = st.columns([5, 2, 1], vertical_alignment="center")
        with text_col:
            ui.rows([ui.row(lecture["topic"], f"{lecture['module'] or ''}, lecture on {lecture['date']}",
                            f"review {lecture['reviews_done'] + 1}", tone="warn" if lecture["understanding"] <= 3 else None)])
        score = score_col.slider("Now", 1, 5, max(lecture["understanding"], 3), key=f"score_{lecture['id']}", label_visibility="collapsed")
        if done_col.button("Reviewed", key=f"rev_{lecture['id']}"):
            university.complete_review(lecture["id"], score)
            st.rerun()
    ui.muted("Review means recall first: write or say what you remember, then check the notes. Topics you rate 4 or 5 come back after "
             "3, 7, 14 and 30 days. Lower ratings come back tomorrow.")

    recent = university.recent_lectures()
    if recent:
        ui.section("Recently logged")
        ui.table([{"Date": l["date"], "Module": l["module"], "Topic": l["topic"], "Followed (1 to 5)": l["understanding"],
                   "Next review": l["next_review"] or "finished"} for l in recent])

# ------------------------------------------------------------------
with setup:
    ui.muted("Add each module's code and credits so the overall average is weighted correctly.")
    for module in modules:
        name_col, code_col, credit_col, save_col, delete_col = st.columns([3, 1.5, 1.2, 1, 1], vertical_alignment="bottom")
        name_col.markdown(f"**{module['name']}**")
        code = code_col.text_input("Code", value=module["code"] or "", key=f"code_{module['id']}", placeholder="PH2xxxx")
        credits = credit_col.number_input("Credits", value=module["credits"], min_value=0.0, step=1.0, key=f"credits_{module['id']}")
        if save_col.button("Save", key=f"modsave_{module['id']}"):
            university.update_module(module["id"], code.strip(), credits)
            st.rerun()
        if delete_col.button("Remove", key=f"moddel_{module['id']}", help="Also removes its deadlines, study log and lectures"):
            university.delete_module(module["id"])
            st.rerun()
    with st.form("new_module", clear_on_submit=True):
        a, b, c = st.columns([3, 1.5, 1])
        name = a.text_input("New module", placeholder="Scientific computing")
        code = b.text_input("Code")
        semester = c.selectbox("Semester", ["1", "2"])
        if ui.submit("Add module") and name.strip():
            university.add_module(name.strip(), code.strip(), None, semester)
            st.rerun()
