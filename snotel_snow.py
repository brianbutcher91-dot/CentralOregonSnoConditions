import datetime

import requests

HEADERS = {
    "User-Agent": "CentralOregonConditions (brian.butcher.91@gmail.com)"
}

# NRCS AWDB REST API - station triplets are stationId:state:networkCode
# No dedicated "Mt Bachelor" SNOTEL exists; Irish Taylor is the closest
# station to the resort (~15 mi SW).
SNOTEL_STATIONS = {
    "Mt Bachelor area (Irish Taylor)": "545:OR:SNTL",
    "Three Creek / Tam McArthur (Three Creeks Meadow)": "815:OR:SNTL",
    "Santiam / Hoodoo (Hogg Pass)": "526:OR:SNTL",
    "Ochocos (Ochoco Meadows)": "671:OR:SNTL",
}


def get_snotel_data(station_triplet):
    url = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
    params = {
        "stationTriplets": station_triplet,
        "elements": "SNWD,WTEQ",  # snow depth, snow water equivalent
        "duration": "DAILY",
        "getFlags": "false",
        "beginDate": "-1",  # most recent
        "endDate": "-1",
    }
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()


def get_snow_depth_series(station_triplet, hours_back=60):
    # Hourly SNWD readings only get pushed when the value changes, so this
    # can come back sparse - that's fine, we just need enough history to
    # find "as of 12/24 hours ago" via a forward-fill lookup. Query window
    # uses our local clock and is intentionally generous (60hr for a 24hr
    # lookback) so a little timezone slop between us and the station doesn't
    # leave us short of data - the actual "now" for the delta math below is
    # anchored to the station's own latest timestamp instead, so it doesn't
    # matter what timezone we're running in.
    now = datetime.datetime.now()
    url = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
    params = {
        "stationTriplets": station_triplet,
        "elements": "SNWD",
        "duration": "HOURLY",
        "getFlags": "false",
        "beginDate": (now - datetime.timedelta(hours=hours_back)).strftime("%Y-%m-%d %H:%M"),
        "endDate": (now + datetime.timedelta(hours=12)).strftime("%Y-%m-%d %H:%M"),
    }
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return []
    element_data = data[0].get("data", [])
    return element_data[0].get("values", []) if element_data else []


def compute_snow_depth_changes(series):
    if not series:
        return {"change_12h_in": None, "change_24h_in": None}

    parsed = sorted(
        (datetime.datetime.strptime(v["date"], "%Y-%m-%d %H:%M"), v["value"])
        for v in series
    )
    # Anchor "now" to the station's own latest reading (station-local time)
    # rather than our clock, so no timezone conversion is needed at all.
    now = parsed[-1][0]
    current = parsed[-1][1]

    def value_as_of(target):
        candidates = [value for ts, value in parsed if ts <= target]
        return candidates[-1] if candidates else None

    val_12h = value_as_of(now - datetime.timedelta(hours=12))
    val_24h = value_as_of(now - datetime.timedelta(hours=24))

    return {
        "change_12h_in": round(current - val_12h, 1) if val_12h is not None else None,
        "change_24h_in": round(current - val_24h, 1) if val_24h is not None else None,
    }


def print_snow_report(location_name, data):
    print(f"\n=== {location_name} ===")
    if not data:
        print("No data returned.")
        return

    station_data = data[0]
    for element in station_data.get("data", []):
        code = element["stationElement"]["elementCode"]
        label = "Snow depth (in)" if code == "SNWD" else "Snow water equivalent (in)"
        values = element.get("values", [])
        if values:
            latest = values[-1]
            print(f"{label}: {latest['value']} (as of {latest['date']})")
        else:
            print(f"{label}: no recent readings")


if __name__ == "__main__":
    for name, triplet in SNOTEL_STATIONS.items():
        data = get_snotel_data(triplet)
        print_snow_report(name, data)

        changes = compute_snow_depth_changes(get_snow_depth_series(triplet))
        print(f"12hr change: {changes['change_12h_in']}\" | 24hr change: {changes['change_24h_in']}\"")
