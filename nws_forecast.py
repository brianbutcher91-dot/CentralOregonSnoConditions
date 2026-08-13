import datetime
import re

import requests

# NWS API requires a descriptive User-Agent (they'll block generic/blank ones)
HEADERS = {
    "User-Agent": "CentralOregonConditions (brian.butcher.91@gmail.com)"
}

# Coordinates for a few Central Oregon spots you can swap between.
# Order here drives the order of rows in the forecast table.
LOCATIONS = {
    "Mt Bachelor": (43.9792, -121.6886),
    "Tam McArthur Rim": (44.1017, -121.6224),
    "Hoodoo": (44.4090, -121.8720),
    "Paulina Peak": (43.7025, -121.2661),
    "Willamette Pass": (43.5975, -122.0339),
    "Tombstone Pass": (44.39548, -122.14151),
    "Ochoco Meadows": (44.4333, -120.3333),
    "Bend": (44.0582, -121.3153),
    "Sisters": (44.2909, -121.5490),
    "La Pine": (43.6716, -121.5040),
}


def _parse_valid_time(valid_time):
    # NWS interval format: "2026-08-07T10:00:00+00:00/PT10H" (start/ISO8601 duration)
    start_str, duration_str = valid_time.split("/")
    start = datetime.datetime.fromisoformat(start_str)
    match = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?", duration_str)
    days = int(match.group(1) or 0)
    hours = int(match.group(2) or 0)
    duration = datetime.timedelta(days=days, hours=hours)
    return start, start + duration


def _precip_amount_in(values, period_start, period_end):
    # quantitativePrecipitation is an accumulation per sub-interval (mm), on
    # its own schedule that doesn't line up with the 12hr periods - sum every
    # sub-interval that overlaps the period, prorating partial overlaps.
    total_mm = 0.0
    for entry in values:
        start, end = _parse_valid_time(entry["validTime"])
        overlap_start = max(start, period_start)
        overlap_end = min(end, period_end)
        if overlap_start < overlap_end:
            interval_seconds = (end - start).total_seconds()
            if interval_seconds > 0:
                overlap_seconds = (overlap_end - overlap_start).total_seconds()
                total_mm += entry["value"] * (overlap_seconds / interval_seconds)
    return round(total_mm / 25.4, 2)


def _value_at(values, target):
    # Grid data is a time series of {validTime, value} - find the interval
    # covering the target instant, falling back to the first (soonest) entry.
    for entry in values:
        start, end = _parse_valid_time(entry["validTime"])
        if start <= target < end:
            return entry["value"]
    return values[0]["value"] if values else None


def _current_value(values):
    return _value_at(values, datetime.datetime.now(datetime.timezone.utc))


def get_forecast(lat, lon):
    # Step 1: hit the /points endpoint to find the correct forecast office/grid
    points_url = f"https://api.weather.gov/points/{lat},{lon}"
    points_resp = requests.get(points_url, headers=HEADERS)
    points_resp.raise_for_status()
    points_data = points_resp.json()["properties"]

    # Step 2: hit the human-readable forecast endpoint (periods, elevation)
    forecast_resp = requests.get(points_data["forecast"], headers=HEADERS)
    forecast_resp.raise_for_status()
    forecast_props = forecast_resp.json()["properties"]

    # NWS reports elevation per gridpoint (from its terrain model), in meters
    elevation_ft = round(forecast_props["elevation"]["value"] * 3.28084)

    # Step 3: hit the raw gridpoint data for precise current wind direction
    # (degrees) and snow level - not available in the human-readable forecast.
    grid_resp = requests.get(points_data["forecastGridData"], headers=HEADERS)
    grid_resp.raise_for_status()
    grid_props = grid_resp.json()["properties"]

    wind_speed_kmh = _current_value(grid_props["windSpeed"]["values"])
    snow_level_m = _current_value(grid_props["snowLevel"]["values"])
    temp_c = _current_value(grid_props["temperature"]["values"])
    precip_values = grid_props["quantitativePrecipitation"]["values"]
    snow_level_values = grid_props["snowLevel"]["values"]

    periods = forecast_props["periods"]
    for period in periods:
        period_start = datetime.datetime.fromisoformat(period["startTime"])
        period_end = datetime.datetime.fromisoformat(period["endTime"])
        period["precipitationAmountIn"] = _precip_amount_in(precip_values, period_start, period_end)
        period_snow_level_m = _value_at(snow_level_values, period_start)
        period["snowLevelFt"] = round(period_snow_level_m * 3.28084) if period_snow_level_m is not None else None

    return {
        "elevation_ft": elevation_ft,
        "periods": periods,
        "current": {
            "wind_speed_mph": round(wind_speed_kmh * 0.621371) if wind_speed_kmh is not None else None,
            "wind_direction_deg": _current_value(grid_props["windDirection"]["values"]),
            "snow_level_ft": round(snow_level_m * 3.28084) if snow_level_m is not None else None,
            "temp_f": round(temp_c * 9 / 5 + 32) if temp_c is not None else None,
        },
    }


def get_hourly_forecast(lat, lon, hours_forward=72, hours_backward=0):
    # Hourly-sampled from the same raw gridpoint data get_forecast() uses,
    # just walked forward hour by hour instead of per-12hr-period. Mostly
    # forecast-only - history has to come from a real station/sensor instead,
    # since NWS's forecast/gridpoint products don't retain days of the past
    # (see mtbachelor.get_24h_history for why the Mt Bachelor chart pairs
    # this with the mountain's own sensor data rather than a NWS station -
    # the nearest NWS station is a valley airport, wrong elevation/location).
    # hours_backward is the one exception: NWS's gridpoint series typically
    # starts a handful of hours before "now" as part of the same response
    # (this isn't an observation, just the model's own recent-past output),
    # which is real enough to bridge a gap left by the mountain's own sensor
    # feed lagging behind real-time - see build_bachelor_timeseries().
    points_url = f"https://api.weather.gov/points/{lat},{lon}"
    points_resp = requests.get(points_url, headers=HEADERS)
    points_resp.raise_for_status()
    points_props = points_resp.json()["properties"]

    now = datetime.datetime.now(datetime.timezone.utc)
    points = []

    grid_resp = requests.get(points_props["forecastGridData"], headers=HEADERS)
    grid_resp.raise_for_status()
    grid_props = grid_resp.json()["properties"]

    temp_values = grid_props["temperature"]["values"]
    wind_speed_values = grid_props["windSpeed"]["values"]
    wind_dir_values = grid_props["windDirection"]["values"]
    precip_values = grid_props["quantitativePrecipitation"]["values"]

    now_hour = now.replace(minute=0, second=0, microsecond=0)
    hour_start = now_hour - datetime.timedelta(hours=hours_backward)
    # _value_at() falls back to the first entry's value for any target
    # before the series starts, which would silently flat-extrapolate
    # backward instead of leaving a genuine gap - clamp the start so a
    # hours_backward request never reaches further back than the grid data
    # actually covers. The forward end time is anchored separately (not
    # derived from a fixed point count) so clamping the start never eats
    # into how far forward the forecast still reaches.
    earliest_starts = [_parse_valid_time(v[0]["validTime"])[0] for v in (temp_values, wind_speed_values) if v]
    if earliest_starts:
        hour_start = max(hour_start, min(earliest_starts).replace(minute=0, second=0, microsecond=0))

    end_time = now_hour + datetime.timedelta(hours=hours_forward)
    t = hour_start
    while t < end_time:
        temp_c = _value_at(temp_values, t)
        wind_kmh = _value_at(wind_speed_values, t)
        precip_in = _precip_amount_in(precip_values, t, t + datetime.timedelta(hours=1))
        points.append({
            "time": t.isoformat(),
            "temp_f": round(temp_c * 9 / 5 + 32, 1) if temp_c is not None else None,
            "wind_speed_mph": round(wind_kmh * 0.621371, 1) if wind_kmh is not None else None,
            "wind_direction_deg": _value_at(wind_dir_values, t),
            "precip_in": precip_in,
            "period": "forecast",
        })
        t += datetime.timedelta(hours=1)

    return points


def print_forecast(location_name, forecast, num_periods=4):
    print(f"\n=== {location_name} ({forecast['elevation_ft']} ft) ===")
    current = forecast["current"]
    print(f"Current: wind {current['wind_speed_mph']} mph @ {current['wind_direction_deg']}°, "
          f"snow level {current['snow_level_ft']} ft")
    for period in forecast["periods"][:num_periods]:
        print(f"{period['name']}: {period['temperature']}°{period['temperatureUnit']}, "
              f"{period['shortForecast']}, wind {period['windSpeed']} {period['windDirection']}")


if __name__ == "__main__":
    for name, (lat, lon) in LOCATIONS.items():
        forecast = get_forecast(lat, lon)
        print_forecast(name, forecast)
