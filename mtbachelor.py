import datetime
import json
import os

import requests

# Undocumented internal API that mtbachelor.com's own site JS calls (found via
# browser devtools Network tab, not an official published API). No auth needed,
# but this can break or change without notice if the resort redesigns their site.
BASE_URL = "https://api.mtbachelor.com/api/v1"

HEADERS = {
    "User-Agent": "CentralOregonConditions (brian.butcher.91@gmail.com)"
}

# Webcam IDs, taken from the numbers in /the-mountain/webcams/ page links
# (e.g. "live-cam-1" -> id 1). Confirmed working: 1, 8, 12, 13.
# id 13 is labeled "West Village Area" in-frame and matches the site's own
# "watch the snow pile up on our West Village snow stake" description.
WEBCAMS = {
    1: "Base of Pine Marten Lift",
    8: "Summit",
    12: "Mid-Mountain",
    13: "West Village",
    14: "Snow Stake",
}

# The weather-forecast API's sensor keys (snowplot, pine, etc.) aren't
# human-readable and don't include elevation. Both come from the site's own
# "LIVE TEMPERATURES & WIND" display, which lists elevation per station but
# doesn't expose it through the API - hardcoded here from that page.
SENSOR_INFO = {
    "snowplot": {"name": "West Village", "elevation_ft": 6300},
    "sunrise": {"name": "Sunrise", "elevation_ft": 7300},
    "pine": {"name": "Pine Marten", "elevation_ft": 7800},
    "cloudChaser": {"name": "Cloud Chaser", "elevation_ft": 7700},
    "northwest": {"name": "Northwest", "elevation_ft": 8000},
    "summit": {"name": "Summit", "elevation_ft": 9065},
}


def get_weather():
    resp = requests.get(f"{BASE_URL}/dor/weather-forecast", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def get_snow_report_text():
    resp = requests.get(
        f"{BASE_URL}/dor/drupal/snow-reports",
        headers=HEADERS,
        params={"sort": "date", "direction": "desc"},
    )
    resp.raise_for_status()
    return resp.json()


def print_weather(data):
    print("\n=== Mt. Bachelor Current Conditions ===")
    print(f"Current temp: {data['current']['temperature']}F")

    print("\n--- Live station readings ---")
    for name, sensor in data.get("sensors", {}).items():
        temp = sensor.get("temperature")
        wind = sensor.get("wind", {})
        print(f"{name}: {temp}F, wind avg {wind.get('average')} mph, "
              f"max {wind.get('high')} mph")

    print("\n--- Forecast ---")
    for day in data.get("forecast", [])[:4]:
        print(f"{day['day']}: {day['temperature_low']}-{day['temperature_high']}F, "
              f"{day['description_short']}, wind {day['wind_speed']} mph {day['wind_direction']}")


def print_snow_report(reports):
    if not reports:
        print("\nNo snow report available.")
        return
    latest = reports[0]
    print(f"\n=== Latest Mountain Report ({latest['date']}) ===")
    print(latest["report"])


def get_cam_image_url(cam_id):
    return f"{BASE_URL}/cams/mtn/{cam_id}"


def get_cam_page_url(cam_id):
    return f"https://www.mtbachelor.com/the-mountain/webcams/live-cam-{cam_id}/"


def closest_sensor_key(target_elevation_ft):
    return min(SENSOR_INFO, key=lambda key: abs(SENSOR_INFO[key]["elevation_ft"] - target_elevation_ft))


def get_24h_history(sensor_key):
    # Only 24hr of history is available here (checked for 48/72hr and 7-day
    # variants - all 404), unlike the multi-day NWS forecast this pairs with.
    # No precipitation field either - this is a wind/temp sensor, not a gauge.
    resp = requests.get(f"{BASE_URL}/dor/24-hour-weather", headers=HEADERS)
    resp.raise_for_status()
    readings = resp.json().get(sensor_key, [])  # API returns newest-first
    points = [
        {
            "time": r["timestamp"],
            "temp_f": float(r["temperature"]) if r.get("temperature") is not None else None,
            "wind_speed_mph": float(r["windSpeedAvg"]) if r.get("windSpeedAvg") is not None else None,
            "wind_direction_deg": float(r["windDirAvg"]) if r.get("windDirAvg") is not None else None,
            "precip_in": None,
            "period": "historical",
        }
        for r in readings
    ]
    return sorted(points, key=lambda p: p["time"])


# Bachelor's site only ever exposes a rolling 24hr snowfall total (see
# build_conditions.build_bachelor_timeseries) - no hourly or 12hr breakdown
# exists anywhere in their data. Rather than fabricate a split of that single
# number, this logs one real snapshot of it per run to a small local file, so
# the timeseries chart's historical precip panel can plot genuine readings at
# their actual recorded time. Starts empty and fills in over repeated builds.
SNOW_HISTORY_PATH = "bachelor_snow_history.json"
SNOW_HISTORY_MAX_HOURS = 72
SNOW_HISTORY_MIN_INTERVAL_HOURS = 1


def load_snow_history():
    if not os.path.exists(SNOW_HISTORY_PATH):
        return []
    try:
        with open(SNOW_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def record_snow_snapshot(snowfall_24h_in):
    # Called once per build_conditions.py run. Throttled to roughly hourly
    # regardless of how often the build actually runs, so the log's
    # resolution matches the rest of the chart instead of clumping snapshots
    # together if the build is run repeatedly in quick succession (e.g. while
    # testing, or once a scheduled job runs every few minutes).
    history = load_snow_history()
    now = datetime.datetime.now(datetime.timezone.utc)

    should_append = snowfall_24h_in is not None
    if should_append and history:
        last_time = datetime.datetime.fromisoformat(history[-1]["time"])
        if (now - last_time).total_seconds() < SNOW_HISTORY_MIN_INTERVAL_HOURS * 3600:
            should_append = False

    if should_append:
        history.append({"time": now.isoformat(), "snowfall_24h_in": snowfall_24h_in})

    cutoff = now - datetime.timedelta(hours=SNOW_HISTORY_MAX_HOURS)
    history = [h for h in history if datetime.datetime.fromisoformat(h["time"]) >= cutoff]

    with open(SNOW_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

    return history


if __name__ == "__main__":
    weather = get_weather()
    print_weather(weather)

    reports = get_snow_report_text()
    print_snow_report(reports)

    print("\n=== Webcam still-image URLs ===")
    for cam_id, name in WEBCAMS.items():
        print(f"{name}: {get_cam_image_url(cam_id)}")
