"""
test_apple_health.py
====================
Purpose : Check the Apple Health parsing rules on a tiny hand-made export.
Run     : pytest -q
Note    : November 2026 UK time equals UTC, so the times below read the same in both.
"""

from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

from services.apple_health import build_sleep_nights, read_stream

TZ = ZoneInfo("Europe/London")
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=TZ)

XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<HealthData locale="en_GB">
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" value="HKCategoryValueSleepAnalysisAsleepCore" startDate="2026-11-02 23:30:00 +0000" endDate="2026-11-03 03:30:00 +0000"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" value="HKCategoryValueSleepAnalysisAwake" startDate="2026-11-03 03:30:00 +0000" endDate="2026-11-03 04:00:00 +0000"/>
 <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Watch" value="HKCategoryValueSleepAnalysisAsleepDeep" startDate="2026-11-03 04:00:00 +0000" endDate="2026-11-03 07:30:00 +0000"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="iPhone" unit="count" value="3000" startDate="2026-11-03 09:00:00 +0000" endDate="2026-11-03 09:30:00 +0000"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" unit="count" value="3200" startDate="2026-11-03 09:00:00 +0000" endDate="2026-11-03 09:30:00 +0000"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" unit="count" value="1000" startDate="2026-11-03 10:00:00 +0000" endDate="2026-11-03 10:10:00 +0000"/>
 <Record type="HKQuantityTypeIdentifierStepCount" sourceName="Watch" unit="count" value="5000" startDate="2026-01-01 09:00:00 +0000" endDate="2026-01-01 09:30:00 +0000"/>
 <Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="Watch" unit="count/min" value="52" startDate="2026-11-03 08:00:00 +0000" endDate="2026-11-03 08:00:00 +0000"/>
 <Workout workoutActivityType="HKWorkoutActivityTypeTraditionalStrengthTraining" duration="50" durationUnit="min" startDate="2026-11-03 17:00:00 +0000" endDate="2026-11-03 17:50:00 +0000"/>
</HealthData>"""


def parsed():
    return read_stream(BytesIO(XML), days=30, now=NOW)


def test_sleep_segments_merge_and_awake_is_excluded():
    night = parsed()["2026-11-03"]
    assert night["asleep_minutes"] == 450       # 240 + 210, the 30 awake minutes excluded
    assert night["sleep_start"] == "23:30"
    assert night["sleep_end"] == "07:30"


def test_steps_use_largest_source_not_the_sum():
    assert parsed()["2026-11-03"]["steps"] == 4200   # Watch 3200 + 1000, not 7200


def test_workout_minutes_and_label():
    day = parsed()["2026-11-03"]
    assert day["exercise_minutes"] == 50
    assert day["exercise_type"] == "Traditional Strength Training"


def test_resting_heart_rate_is_read():
    assert parsed()["2026-11-03"]["resting_hr"] == 52.0


def test_old_records_are_ignored():
    assert "2026-01-01" not in parsed()


def test_overlapping_sleep_sources_are_not_double_counted():
    a = (datetime(2026, 11, 2, 23, 0, tzinfo=TZ), datetime(2026, 11, 3, 7, 0, tzinfo=TZ))
    b = (datetime(2026, 11, 2, 23, 30, tzinfo=TZ), datetime(2026, 11, 3, 6, 30, tzinfo=TZ))
    assert build_sleep_nights([a, b])["2026-11-03"]["asleep_minutes"] == 480