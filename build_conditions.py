"""
Pulls every data source and writes conditions.json - the one file the
website will actually read. Each source is wrapped so that one broken feed
(the undocumented/scraped ones especially) doesn't take down the whole build;
failures are recorded in the output instead of raised.
"""
import datetime
import json
import traceback

import avalanche_center
import gfs_snowfall
import goes_satellite
import hoodoo
import mtbachelor
import nws_forecast
import odot_cams
import snotel_snow
import willamette_pass

OUTPUT_PATH = "conditions.json"


def safe(label, fn):
    try:
        return fn()
    except Exception as e:
        print(f"  [FAILED] {label}: {e}")
        traceback.print_exc()
        return {"error": str(e)}


def build_forecast():
    result = {}
    for name, (lat, lon) in nws_forecast.LOCATIONS.items():
        forecast = nws_forecast.get_forecast(lat, lon)
        forecast["lat"] = lat
        forecast["lon"] = lon
        result[name] = forecast
    return result


def build_bachelor_timeseries(mtbachelor_data):
    lat, lon = nws_forecast.LOCATIONS["Mt Bachelor"]

    # Match the NWS gridpoint's own elevation (7,638ft - the same number
    # shown everywhere else on the site for Mt Bachelor) rather than the
    # true summit, so the historical and forecast halves are describing the
    # same spot on the mountain as closely as the two sources allow. Using
    # the nearest NWS station here instead (a valley airport) was the bug
    # this replaced - wrong location and ~1,500-3,000ft lower.
    sensor_key = mtbachelor.closest_sensor_key(7638)
    historical_points = mtbachelor.get_24h_history(sensor_key)

    # The mountain's own sensor feed has been observed lagging several
    # hours behind real time (its last reading isn't always "now") -
    # bridge that gap with NWS's own gridpoint data for the same recent
    # hours instead of leaving a hole in the wind/temp history. Starts an
    # hour after the last real sensor reading (not on top of it) and is
    # capped so a very stale/broken sensor feed doesn't request an
    # unreasonably large NWS-only window.
    hours_backward = 0
    if historical_points:
        last_historical_time = datetime.datetime.fromisoformat(historical_points[-1]["time"])
        gap_hours = (datetime.datetime.now(datetime.timezone.utc) - last_historical_time).total_seconds() / 3600
        hours_backward = max(0, min(24, int(gap_hours) - 1))

    forecast_points = nws_forecast.get_hourly_forecast(lat, lon, hours_backward=hours_backward)

    # Bachelor's site has no hourly (or even 12hr) precip breakdown, just a
    # rolling 24hr total (the same figure used for the wind-rose card's
    # "Snowfall, 24 hr" stat) - splitting that single number into fake
    # sub-24hr buckets would be fabricated data. Instead, log one real
    # snapshot of it per run; the chart plots whatever genuine snapshots
    # have accumulated in the last 72 hours at their real recorded time.
    computed = ((mtbachelor_data or {}).get("latest_report") or {}).get("computed") or {}
    total_24h = computed.get("24_hour")
    snow_history = mtbachelor.record_snow_snapshot(total_24h)

    historical_precip_snapshots = [
        {"time": h["time"], "precip_in": h["snowfall_24h_in"]}
        for h in snow_history
    ]

    return {
        "hourly": historical_points + forecast_points,
        "historical_precip_snapshots": historical_precip_snapshots,
    }


def apply_hoodoo_live_wind(forecast_data, hoodoo_data):
    # NWS's gridpoint wind is a model value - Hoodoo has its own live weather
    # station telemetry (santiampsp.org), which is the real observed wind at
    # the mountain. Overwrite in place so every consumer of forecast_data
    # (wind-rose cards, map overlay) gets the corrected reading.
    hoodoo_forecast = (forecast_data or {}).get("Hoodoo")
    if not hoodoo_forecast or not hoodoo_data or "error" in hoodoo_data:
        return
    station_speed, station_direction = hoodoo.parse_wind(hoodoo_data.get("weather", {}).get("Wind"))
    if station_speed is not None and station_direction is not None:
        hoodoo_forecast["current"]["wind_speed_mph"] = station_speed
        hoodoo_forecast["current"]["wind_direction_deg"] = station_direction


def build_snotel():
    result = {}
    for name, triplet in snotel_snow.SNOTEL_STATIONS.items():
        data = snotel_snow.get_snotel_data(triplet)
        readings = {}
        if data:
            for element in data[0].get("data", []):
                code = element["stationElement"]["elementCode"]
                key = "snow_depth_in" if code == "SNWD" else "swe_in"
                values = element.get("values", [])
                if values:
                    readings[key] = values[-1]["value"]
                    readings[key + "_date"] = values[-1]["date"]

        series = snotel_snow.get_snow_depth_series(triplet)
        readings.update(snotel_snow.compute_snow_depth_changes(series))

        result[name] = readings
    return result


def build_odot_cams():
    result = {}
    for name, device_name in odot_cams.CAMERAS.items():
        cams = odot_cams.get_cams(device_name)
        for cam in cams:
            cam["tripcheck_link"] = odot_cams.get_tripcheck_link(cam["cctv-url"])
        result[name] = cams
    return result


def build_mtbachelor():
    weather = mtbachelor.get_weather()
    for key, sensor in weather.get("sensors", {}).items():
        info = mtbachelor.SENSOR_INFO.get(key, {})
        sensor["display_name"] = info.get("name", key)
        sensor["elevation_ft"] = info.get("elevation_ft")

    return {
        "weather": weather,
        "latest_report": (mtbachelor.get_snow_report_text() or [None])[0],
        "webcams": {
            name: {"src": mtbachelor.get_cam_image_url(cam_id), "link": mtbachelor.get_cam_page_url(cam_id)}
            for cam_id, name in mtbachelor.WEBCAMS.items()
        },
    }


def build_hoodoo():
    return {
        "weather": hoodoo.get_weather(),
        "snow_totals": hoodoo.get_snow_totals(),
        "webcams": {
            label: {"src": hoodoo.get_cam_url(cam_id), "link": hoodoo.WEBCAMS_PAGE_URL}
            for cam_id, label in hoodoo.WEBCAMS.items()
        },
    }


def build_willamette_pass():
    html = willamette_pass.get_page_html()
    return {
        "forecast": willamette_pass.get_forecast(),
        "snow_totals": willamette_pass.get_snow_totals(html),
        "webcams": {
            label: {"src": src, "link": willamette_pass.WEBCAMS_PAGE_URL}
            for label, src in willamette_pass.get_webcams(html).items()
        },
    }


def build_snow_stake_cams(mtbachelor_data, hoodoo_data, willamette_data):
    # Same physical kind of shot (base-area/lodge view) at each of the three
    # resorts, side by side for a quick visual snow-depth comparison. Hoodoo
    # has no cam literally labeled "snow stake" - Base Area is the closest
    # equivalent there.
    return {
        "Mt. Bachelor (Snow Stake)": (mtbachelor_data or {}).get("webcams", {}).get("Snow Stake"),
        "Hoodoo (Base Area)": (hoodoo_data or {}).get("webcams", {}).get("Base Area"),
        "Willamette Pass (Base Area)": (willamette_data or {}).get("webcams", {}).get("Base Area"),
    }


def build_satellite():
    return {
        name: goes_satellite.get_image_info(sector_code)
        for name, sector_code in goes_satellite.SECTORS.items()
    }


WIND_ROSE_LOCATIONS = ["Mt Bachelor", "Hoodoo", "Willamette Pass"]


def _parse_inches(text):
    if not text:
        return None
    cleaned = text.replace('"', "").replace("”", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _bachelor_snowfall(mtbachelor_data):
    # No 12hr figure exists in Bachelor's own data model - it jumps from
    # "overnight" straight to 24hr.
    computed = ((mtbachelor_data or {}).get("latest_report") or {}).get("computed") or {}
    return {
        "snowfall_12h_in": None,
        "snowfall_24h_in": computed.get("24_hour"),
        "snowfall_48h_in": computed.get("48_hour"),
    }


def _hoodoo_snowfall(hoodoo_data):
    # Santiam Pass Ski Patrol's trend table tops out at 24hr - no 48hr figure
    # exists anywhere for Hoodoo.
    trend = ((hoodoo_data or {}).get("snow_totals") or {}).get("trend") or {}
    return {
        "snowfall_12h_in": _parse_inches(trend.get("12 Hr")),
        "snowfall_24h_in": _parse_inches(trend.get("24 Hr")),
        "snowfall_48h_in": None,
    }


def _willamette_snowfall(willamette_data):
    # No 12hr figure in Willamette Pass's snow-totals widget - it goes
    # straight from 24hr to 48hr.
    totals = (willamette_data or {}).get("snow_totals") or {}
    return {
        "snowfall_12h_in": None,
        "snowfall_24h_in": _parse_inches(totals.get("24 Hr")),
        "snowfall_48h_in": _parse_inches(totals.get("48 Hr")),
    }


def build_wind_roses(forecast_data, mtbachelor_data, hoodoo_data, willamette_data):
    snowfall_by_location = {
        "Mt Bachelor": _bachelor_snowfall(mtbachelor_data),
        "Hoodoo": _hoodoo_snowfall(hoodoo_data),
        "Willamette Pass": _willamette_snowfall(willamette_data),
    }

    result = {}
    for name in WIND_ROSE_LOCATIONS:
        loc = (forecast_data or {}).get(name)
        if not loc or "current" not in loc:
            continue
        today = loc["periods"][0] if loc.get("periods") else {}
        result[name] = {
            "elevation_ft": loc["elevation_ft"],
            "temp_f": loc["current"].get("temp_f"),
            "wind_speed_mph": loc["current"]["wind_speed_mph"],
            "wind_direction_deg": loc["current"]["wind_direction_deg"],
            "snow_level_ft": loc["current"]["snow_level_ft"],
            "precip_chance_today": today.get("probabilityOfPrecipitation", {}).get("value"),
            **snowfall_by_location.get(name, {}),
        }
    return result


def build_avalanche():
    return {
        name: avalanche_center.get_forecast(zone_id)
        for name, zone_id in avalanche_center.ZONES.items()
    }


def main():
    print("Building conditions.json...")

    mtbachelor_data = safe("Mt. Bachelor", build_mtbachelor)
    hoodoo_data = safe("Hoodoo", build_hoodoo)
    willamette_data = safe("Willamette Pass", build_willamette_pass)

    forecast_data = safe("NWS forecast", build_forecast)
    apply_hoodoo_live_wind(forecast_data, hoodoo_data)

    data = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "forecast": forecast_data,
        "wind_roses": build_wind_roses(forecast_data, mtbachelor_data, hoodoo_data, willamette_data),
        "bachelor_timeseries": safe("Bachelor timeseries", lambda: build_bachelor_timeseries(mtbachelor_data)),
        "snotel": safe("SNOTEL", build_snotel),
        "odot_cams": safe("ODOT cams", build_odot_cams),
        "mtbachelor": mtbachelor_data,
        "hoodoo": hoodoo_data,
        "willamette_pass": willamette_data,
        "snow_stake_cams": build_snow_stake_cams(mtbachelor_data, hoodoo_data, willamette_data),
        "satellite": safe("GOES Satellite", build_satellite),
        "gfs_snowfall": safe("GFS Snowfall", gfs_snowfall.build_snowfall_gif),
        "avalanche": safe("Avalanche Center", build_avalanche),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
