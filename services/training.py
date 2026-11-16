"""
training.py
===========
Purpose : The health analysis and the training planner. Pure functions on plain
          data, so they cost no tokens and are covered by tests.
Location: services/training.py
Used by : views/health.py, views/home.py, ai/context.py
Note    : General training guidance, not medical advice. The rules used are common
          coaching rules of thumb and each one is named where it is applied.
"""

import statistics
from datetime import date, datetime, timedelta

from services.calendar import at, free_ranges

# ------------------------------------------------------------------
# Sleep
# ------------------------------------------------------------------
def _minutes_after_6pm(hhmm):
    """Bedtimes straddle midnight, so measure them from 18:00 (23:30 gives 330, 00:30 gives 390)."""
    try:
        moment = datetime.strptime(hhmm, "%H:%M")
    except (TypeError, ValueError):
        return None
    return (moment.hour * 60 + moment.minute - 18 * 60) % (24 * 60)


def sleep_stats(rows, target_hours=8.0):
    """Average sleep, total debt against the target, and how regular bedtime is.

    bedtime_spread is the standard deviation of bedtime in minutes. Under about
    30 is very regular, over 60 means the body clock is being moved around.
    """
    hours = [row["hours"] for row in rows if row.get("hours")]
    bedtimes = [m for m in (_minutes_after_6pm(row.get("bed_time")) for row in rows) if m is not None]
    stats = {"nights": len(hours), "average": None, "debt": 0.0, "bedtime_spread": None, "average_bedtime": None}
    if hours:
        stats["average"] = sum(hours) / len(hours)
        stats["debt"] = sum(max(0.0, target_hours - h) for h in hours)
    if len(bedtimes) >= 3:
        stats["bedtime_spread"] = statistics.stdev(bedtimes)
    if bedtimes:
        mean = (sum(bedtimes) / len(bedtimes) + 18 * 60) % (24 * 60)
        stats["average_bedtime"] = f"{int(mean // 60):02d}:{int(mean % 60):02d}"
    return stats


# ------------------------------------------------------------------
# Training load
# ------------------------------------------------------------------
def week_start(day):
    day = date.fromisoformat(day) if isinstance(day, str) else day
    return day - timedelta(days=day.weekday())


def _blank_week(key):
    return {"week": key, "strength": 0, "runs": 0, "other": 0, "run_km": 0.0, "minutes": 0.0}


def weekly_load(workouts, through=None):
    """Sessions and running distance per week (weeks start on Monday), oldest first.

    Weeks with nothing logged are included as zeros, and the list always ends on the
    week containing `through` (today by default), so the last entry is "this week".
    """
    weeks = {}
    for workout in workouts:
        key = week_start(workout["date"]).isoformat()
        week = weeks.setdefault(key, _blank_week(key))
        kind = workout.get("kind")
        if kind == "strength":
            week["strength"] += 1
        elif kind == "run":
            week["runs"] += 1
            week["run_km"] += workout.get("distance_km") or 0
        else:
            week["other"] += 1
        week["minutes"] += workout.get("duration_min") or 0
    if not weeks:
        return []
    cursor, last = date.fromisoformat(min(weeks)), week_start(through or date.today())
    while cursor <= last:
        weeks.setdefault(cursor.isoformat(), _blank_week(cursor.isoformat()))
        cursor += timedelta(days=7)
    return [weeks[key] for key in sorted(weeks)]


def run_load_ratio(load):
    """This week's running distance over the average of the previous three weeks.

    A ratio well above about 1.3 is a common warning sign that distance is rising too fast.
    """
    if len(load) < 2:
        return None
    previous = [week["run_km"] for week in load[-4:-1]]
    baseline = sum(previous) / len(previous) if previous else 0
    return (load[-1]["run_km"] / baseline) if baseline > 0 else None


# ------------------------------------------------------------------
# Strength
# ------------------------------------------------------------------
def epley_1rm(weight_kg, reps):
    """Estimated one-rep max, Epley formula: 1RM = w (1 + r / 30)."""
    if not weight_kg or not reps:
        return None
    return weight_kg if reps == 1 else weight_kg * (1 + reps / 30)


def strength_trend(lifts):
    """Best estimated 1RM per day for one exercise: [{date, e1rm}]."""
    best = {}
    for lift in lifts:
        estimate = epley_1rm(lift["weight_kg"], lift["reps"])
        if estimate:
            best[lift["date"]] = max(best.get(lift["date"], 0), estimate)
    return [{"date": day, "e1rm": round(value, 1)} for day, value in sorted(best.items())]


def next_lift_target(lifts, rep_range=(6, 10), step_kg=2.5):
    """Double progression: add reps until the top of the range, then add weight.

    Looks at the most recent session for one exercise and returns the next target.
    """
    if not lifts:
        return None
    last_day = max(lift["date"] for lift in lifts)
    session = [lift for lift in lifts if lift["date"] == last_day]
    top = max(session, key=lambda lift: (lift["weight_kg"], lift["reps"]))
    low, high = rep_range
    if top["reps"] >= high:
        return {"weight_kg": top["weight_kg"] + step_kg, "reps": low,
                "why": f"You hit {top['reps']} reps at {top['weight_kg']:g} kg, the top of the range. Add {step_kg:g} kg and restart at {low} reps."}
    return {"weight_kg": top["weight_kg"], "reps": min(high, top["reps"] + 1),
            "why": f"Stay at {top['weight_kg']:g} kg and aim for {min(high, top['reps'] + 1)} reps before adding weight."}


def protein_target(weight_kg, per_kg=(1.6, 2.2)):
    if not weight_kg:
        return None
    return round(weight_kg * per_kg[0]), round(weight_kg * per_kg[1])


# ------------------------------------------------------------------
# Weekly plan
# ------------------------------------------------------------------
SESSIONS = {
    "Upper A": ("strength", 65, ["Bench press 4 x 6-8", "Barbell row 4 x 6-8", "Overhead press 3 x 8-10",
                                 "Lat pulldown 3 x 8-12", "Lateral raise 3 x 12-15", "Triceps pushdown 3 x 10-12"]),
    "Upper B": ("strength", 65, ["Incline dumbbell press 4 x 8-10", "Pull-up or assisted pull-up 4 x 6-10",
                                 "Seated cable row 3 x 8-12", "Dumbbell shoulder press 3 x 8-10",
                                 "Biceps curl 3 x 10-12", "Face pull 3 x 12-15"]),
    "Lower A": ("strength", 65, ["Back squat 4 x 6-8", "Romanian deadlift 3 x 8-10", "Leg press 3 x 10-12",
                                 "Leg curl 3 x 10-12", "Calf raise 3 x 12-15", "Plank 3 x 45 s"]),
    "Lower B": ("strength", 65, ["Deadlift 3 x 5", "Bulgarian split squat 3 x 8-10 each leg", "Leg extension 3 x 12-15",
                                 "Hip thrust 3 x 8-10", "Calf raise 3 x 12-15", "Hanging knee raise 3 x 10-12"]),
    "Full body A": ("strength", 70, ["Back squat 3 x 6-8", "Bench press 3 x 6-8", "Barbell row 3 x 8-10",
                                     "Overhead press 2 x 8-10", "Leg curl 2 x 10-12", "Plank 3 x 45 s"]),
    "Full body B": ("strength", 70, ["Romanian deadlift 3 x 8-10", "Incline dumbbell press 3 x 8-10",
                                     "Lat pulldown 3 x 8-12", "Split squat 2 x 8-10 each leg", "Lateral raise 3 x 12-15",
                                     "Biceps curl 2 x 10-12"]),
    "Full body C": ("strength", 70, ["Leg press 3 x 10-12", "Dumbbell shoulder press 3 x 8-10", "Pull-up 3 x 6-10",
                                     "Hip thrust 3 x 8-10", "Triceps pushdown 2 x 10-12", "Calf raise 3 x 12-15"]),
    "Easy run": ("run", 35, ["Conversational pace, effort 3-4 out of 10. You should be able to talk in full sentences."]),
    "Quality run": ("run", 45, ["10 min easy warm-up", "5 x 3 min hard (effort 8 out of 10) with 2 min easy jog between",
                                "10 min easy cool-down"]),
    "Long run": ("run", 60, ["Easy effort throughout, 3-4 out of 10. Distance matters here, not pace."]),
    "Rest": ("rest", 0, ["Walk, stretch, sleep. Adaptation happens on rest days."]),
}

# Monday to Sunday. Hard running sits away from heavy leg days, the long run is on Sunday,
# and Saturday is kept free.
PATTERNS = {
    (4, 3): ["Lower A", "Upper A", "Quality run", "Lower B", "Upper B+Easy run", "Rest", "Long run"],
    (4, 2): ["Lower A", "Upper A", "Quality run", "Lower B", "Upper B", "Rest", "Long run"],
    (4, 1): ["Lower A", "Upper A", "Rest", "Lower B", "Upper B", "Rest", "Long run"],
    (4, 0): ["Lower A", "Upper A", "Rest", "Lower B", "Upper B", "Rest", "Rest"],
    (3, 3): ["Full body A", "Easy run", "Full body B", "Quality run", "Full body C", "Rest", "Long run"],
    (3, 2): ["Full body A", "Quality run", "Full body B", "Rest", "Full body C", "Rest", "Long run"],
    (3, 1): ["Full body A", "Rest", "Full body B", "Rest", "Full body C", "Rest", "Long run"],
    (3, 0): ["Full body A", "Rest", "Full body B", "Rest", "Full body C", "Rest", "Rest"],
}


def run_distances(recent_weekly_km, runs):
    """Split next week's distance across the runs.

    Next week is last week plus 10 percent (the "10 percent rule"), never below
    a small starting volume, with the long run taking the largest share.
    """
    if runs <= 0:
        return {}
    total = max(recent_weekly_km * 1.1, 4.0 * runs)
    shares = {1: {"Long run": 1.0},
              2: {"Long run": 0.6, "Quality run": 0.4},
              3: {"Long run": 0.45, "Quality run": 0.3, "Easy run": 0.25}}[min(runs, 3)]
    return {name: round(total * share * 2) / 2 for name, share in shares.items()}   # nearest 0.5 km


def build_week_plan(strength_days, run_days, week_of, recent_weekly_km=0.0):
    """Seven days of sessions starting on the Monday of `week_of`."""
    strength_days = 4 if strength_days >= 4 else 3
    run_days = max(0, min(3, run_days))
    pattern = PATTERNS[(strength_days, run_days)]
    distances = run_distances(recent_weekly_km, run_days)
    monday = week_start(week_of)
    plan = []
    for offset, label in enumerate(pattern):
        names = label.split("+")
        details, minutes, kinds = [], 0, []
        for name in names:
            kind, length, lines = SESSIONS[name]
            kinds.append(kind)
            minutes += length
            if name in distances:
                details.append(f"{name}: about {distances[name]:g} km")
            details.extend(lines)
        plan.append({"date": monday + timedelta(days=offset), "title": " and ".join(names),
                     "kind": kinds[0], "minutes": minutes, "details": details})
    return plan


def suggest_times(plan, events, window=("07:00", "20:30"), prefer="evening", bedtime="23:30"):
    """Give each session a start time that fits around the calendar.

    Rules: stay inside the training window, finish at least two hours before
    bedtime (hard exercise late in the evening tends to delay sleep), and take the
    earliest or latest gap depending on your preference.
    """
    suggestions = []
    for day in plan:
        entry = dict(day, start=None, end=None)
        if day["kind"] != "rest":
            start_dt, end_dt = at(day["date"], window[0]), at(day["date"], window[1])
            if int(bedtime[:2]) >= 12:            # a bedtime after midnight sets no extra limit
                end_dt = min(end_dt, at(day["date"], bedtime) - timedelta(hours=2))
            need = timedelta(minutes=day["minutes"] + 15)   # 15 minutes to get there and change
            gaps = [(a, b) for a, b in free_ranges(events, start_dt, end_dt) if b - a >= need]
            if gaps:
                if prefer == "morning":
                    start = gaps[0][0]
                elif prefer == "evening":
                    start = gaps[-1][1] - need
                else:                              # midday: the gap closest to 13:00
                    target = at(day["date"], "13:00")
                    best = min(gaps, key=lambda gap: abs((gap[0] - target).total_seconds()))
                    start = max(best[0], min(target, best[1] - need))
                entry["start"], entry["end"] = start, start + need
        suggestions.append(entry)
    return suggestions


def insights(sleep, load, ratio, protein_avg, protein_range, plan_days):
    """Plain-English observations from the numbers. Each is (tone, text)."""
    notes = []
    if sleep["nights"] >= 3:
        if sleep["average"] < 7:
            notes.append(("warn", f"Sleep averaged {sleep['average']:.1f} h. Muscle repair and memory consolidation both happen in sleep, so this is the first thing to fix."))
        else:
            notes.append(("good", f"Sleep averaged {sleep['average']:.1f} h."))
        if sleep["bedtime_spread"] and sleep["bedtime_spread"] > 60:
            notes.append(("warn", f"Bedtime varies by about {sleep['bedtime_spread']:.0f} minutes night to night. A steadier bedtime usually improves sleep quality more than a longer lie-in."))
    else:
        notes.append(("info", "Log at least three nights of sleep to see a pattern."))
    if load:
        week = load[-1]
        if week["strength"] < plan_days[0]:
            notes.append(("info", f"{week['strength']} of {plan_days[0]} planned strength sessions done this week."))
        else:
            notes.append(("good", f"All {plan_days[0]} planned strength sessions done this week."))
    if ratio and ratio > 1.3:
        notes.append(("warn", f"Running distance is {ratio:.1f} times your recent average. Sharp jumps are a common route to shin and knee trouble, so hold the distance steady next week."))
    if protein_avg and protein_range:
        if protein_avg < protein_range[0]:
            notes.append(("warn", f"Protein averaged {protein_avg:.0f} g a day against a {protein_range[0]} to {protein_range[1]} g range for muscle gain."))
        else:
            notes.append(("good", f"Protein averaged {protein_avg:.0f} g a day, inside your range."))
    return notes
