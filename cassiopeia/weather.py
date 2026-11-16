"""
weather.py
==========
Purpose : Today's weather and a three-day outlook for config.WEATHER_PLACE.
Location: cassiopeia/weather.py
Used by : cassiopeia/briefing.py, cassiopeia/server.py
Data    : Open-Meteo (open-meteo.com), free and needs no key. Cached for 30 minutes.
"""

import requests

import config
from database import database as db

# World Meteorological Organization weather codes, grouped into plain words
CODES = {0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Freezing fog",
         51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
         66: "Freezing rain", 67: "Freezing rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
         80: "Light showers", 81: "Showers", 82: "Heavy showers", 85: "Snow showers", 86: "Snow showers",
         95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail"}


def describe(code):
    return CODES.get(code, "Unknown")


def shape(raw, place):
    """Turn Open-Meteo's answer into the small dictionary the app uses."""
    now, daily = raw.get("current", {}), raw.get("daily", {})
    days = []
    for i, day in enumerate(daily.get("time", [])[:3]):
        days.append({"day": day, "summary": describe(daily["weather_code"][i]),
                     "high": daily["temperature_2m_max"][i], "low": daily["temperature_2m_min"][i],
                     "rain_chance": daily["precipitation_probability_max"][i]})
    return {"place": place, "temperature": now.get("temperature_2m"), "feels_like": now.get("apparent_temperature"),
            "summary": describe(now.get("weather_code")), "wind_mph": now.get("wind_speed_10m"), "days": days,
            "error": None}


def get(force=False):
    """Current weather, or {"error": "..."} if the service cannot be reached."""
    place, latitude, longitude = config.WEATHER_PLACE
    key = f"weather:{latitude},{longitude}"
    if not force:
        cached = db.cache_get(key)
        if cached:
            return cached
    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
            "latitude": latitude, "longitude": longitude, "timezone": config.TIMEZONE, "forecast_days": 3,
            "wind_speed_unit": "mph",
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
        response.raise_for_status()
        data = shape(response.json(), place)
    except Exception as problem:
        stale = db.cache_get(key, allow_stale=True)
        return stale or {"place": place, "error": f"Weather unavailable: {str(problem)[:120]}", "days": []}
    db.cache_set(key, data, 30 * 60)
    return data


def one_line(data=None):
    data = data or get()
    if data.get("error"):
        return data["error"]
    today = data["days"][0] if data["days"] else {}
    return (f"{data['place']}: {data['summary']}, {data['temperature']:.0f}°C (feels {data['feels_like']:.0f}°C), "
            f"high {today.get('high', 0):.0f}°C, rain chance {today.get('rain_chance', 0)}%.")
