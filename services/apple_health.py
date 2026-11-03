"""
apple_health.py
===============
Purpose : Read an Apple Health "Export All Health Data" zip and turn the last N days
          into one dict of fields per day, then save them with database.health.
Location: services/apple_health.py
Run     : python -m services.apple_health ~/Downloads/export.zip --days 30
Notes   : The export is one huge XML file, so it is streamed, never loaded whole.
          Steps, active energy and protein: sum per source per day, keep the largest
          source (avoids double counting iPhone and Watch).
          Sleep: overlapping segments are merged, gaps of 3 hours or more start a new
          sleep session, and each night is filed under the date you woke up.
          HRV here is SDNN (Apple's default). Other apps, Bevel included, may use a
          different method, so do not compare the numbers across apps.
"""

import argparse
import re
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import config
from database.health import init_health_table, save_daily_log

LOCAL_TZ = ZoneInfo(config.TIMEZONE)
SESSION_GAP = timedelta(hours=3)

STEPS = "HKQuantityTypeIdentifierStepCount"
ACTIVE_ENERGY = "HKQuantityTypeIdentifierActiveEnergyBurned"
PROTEIN = "HKQuantityTypeIdentifierDietaryProtein"
RESTING_HR = "HKQuantityTypeIdentifierRestingHeartRate"
HRV = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
ASLEEP_PREFIX = "HKCategoryValueSleepAnalysisAsleep"   # matches Core, Deep, REM, Unspecified

SUMMED = {STEPS, ACTIVE_ENERGY, PROTEIN}
WANTED = SUMMED | {RESTING_HR, HRV, SLEEP}


def parse_time(text):
    """'2026-11-03 07:12:00 +0000' -> timezone-aware datetime in UK time."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S %z").astimezone(LOCAL_TZ)


def _new_accumulator():
    return {
        "sleep": [],                                                    # (start, end) pairs
        "sums": defaultdict(lambda: defaultdict(lambda: defaultdict(float))),  # type > day > source
        "readings": defaultdict(lambda: defaultdict(list)),             # type > day > values
        "workouts": defaultdict(list),                                  # day > (minutes, type)
    }


def _handle_record(elem, cutoff, acc):
    kind = elem.get("type")
    # Cheap string checks first: the export has millions of records
    if kind not in WANTED or elem.get("endDate", "")[:10] < cutoff:
        return

    start = parse_time(elem.get("startDate"))
    end = parse_time(elem.get("endDate"))

    if kind == SLEEP:
        if elem.get("value", "").startswith(ASLEEP_PREFIX):
            acc["sleep"].append((start, end))
        return

    try:
        value = float(elem.get("value"))
    except (TypeError, ValueError):
        return

    day = start.date().isoformat()
    if kind in SUMMED:
        if kind == ACTIVE_ENERGY and elem.get("unit") == "kJ":
            value /= 4.184   # some locales store kilojoules
        acc["sums"][kind][day][elem.get("sourceName", "unknown")] += value
    else:
        acc["readings"][kind][day].append(value)


def _handle_workout(elem, cutoff, acc):
    if elem.get("startDate", "")[:10] < cutoff:
        return
    minutes = float(elem.get("duration") or 0)
    unit = elem.get("durationUnit", "min")
    if unit == "sec":
        minutes /= 60
    elif unit == "hr":
        minutes *= 60
    kind = elem.get("workoutActivityType", "").replace("HKWorkoutActivityType", "")
    day = parse_time(elem.get("startDate")).date().isoformat()
    acc["workouts"][day].append((minutes, kind))


def _merge(intervals):
    """Union of overlapping (start, end) intervals, sorted."""
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def build_sleep_nights(segments):
    """Group asleep segments into sessions. Returns {wake_date: fields}."""
    sessions = []
    for start, end in _merge(segments):
        minutes = (end - start).total_seconds() / 60
        if sessions and start - sessions[-1]["end"] < SESSION_GAP:
            sessions[-1]["end"] = end
            sessions[-1]["minutes"] += minutes
        else:
            sessions.append({"start": start, "end": end, "minutes": minutes})

    nights = {}
    for s in sessions:
        day = s["end"].date().isoformat()
        # If a nap and a night share a date, keep the longer one
        if day not in nights or s["minutes"] > nights[day]["asleep_minutes"]:
            nights[day] = {
                "sleep_start": s["start"].strftime("%H:%M"),
                "sleep_end": s["end"].strftime("%H:%M"),
                "asleep_minutes": round(s["minutes"]),
            }
    return nights


def _label(kind):
    """'TraditionalStrengthTraining' -> 'Traditional Strength Training'."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", kind) or "Workout"


def summarise(acc):
    """Collapse the accumulator into {day: {field: value}}."""
    days = {}

    def day(d):
        return days.setdefault(d, {})

    for d, fields in build_sleep_nights(acc["sleep"]).items():
        day(d).update(fields)

    for kind, field in ((STEPS, "steps"), (ACTIVE_ENERGY, "active_kcal"), (PROTEIN, "protein_g")):
        for d, by_source in acc["sums"][kind].items():
            day(d)[field] = round(max(by_source.values()))

    for kind, field in ((RESTING_HR, "resting_hr"), (HRV, "hrv_ms")):
        for d, values in acc["readings"][kind].items():
            day(d)[field] = round(mean(values), 1)

    for d, items in acc["workouts"].items():
        day(d)["exercise_minutes"] = round(sum(minutes for minutes, _ in items))
        day(d)["exercise_type"] = _label(max(items)[1])   # longest session names the day

    return days


def read_stream(stream, days=30, now=None):
    """Parse export.xml from a file-like object. `now` exists so tests can fix the date."""
    now = now or datetime.now(LOCAL_TZ)
    cutoff = (now - timedelta(days=days + 1)).strftime("%Y-%m-%d")
    acc = _new_accumulator()

    context = ET.iterparse(stream, events=("start", "end"))
    _, root = next(context)
    for event, elem in context:
        if event != "end":
            continue
        if elem.tag == "Record":
            _handle_record(elem, cutoff, acc)
        elif elem.tag == "Workout":
            _handle_workout(elem, cutoff, acc)
        else:
            continue
        root.clear()   # free memory as we go

    return summarise(acc)


def read_export(zip_path, days=30):
    """Open export.zip and read the XML inside without unpacking it."""
    with zipfile.ZipFile(zip_path) as archive:
        # Folder name varies by language, so match on the file name only
        name = next(
            (n for n in archive.namelist() if n.rsplit("/", 1)[-1] == "export.xml"),
            None,
        )
        if name is None:
            raise FileNotFoundError("export.xml not found inside the zip")
        with archive.open(name) as stream:
            return read_stream(stream, days)


def import_export(zip_path, days=30, db_path=None):
    """Read the export and save each day. Returns (saved, skipped)."""
    init_health_table(db_path)
    saved = skipped = 0
    for day, fields in sorted(read_export(zip_path, days).items()):
        try:
            save_daily_log(day, db_path=db_path, **fields)
            saved += 1
        except ValueError as error:
            skipped += 1
            print(f"Skipped {day}: {error}")
    return saved, skipped


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import an Apple Health export.zip")
    parser.add_argument("zip_path", help="path to export.zip")
    parser.add_argument("--days", type=int, default=30, help="how many recent days to import")
    args = parser.parse_args()

    saved, skipped = import_export(Path(args.zip_path).expanduser(), args.days)
    print(f"Saved {saved} days, skipped {skipped}.")