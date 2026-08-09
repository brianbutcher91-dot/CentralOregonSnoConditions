import re

import requests

HEADERS = {
    "User-Agent": "CentralOregonConditions (brian.butcher.91@gmail.com)"
}

# Hoodoo has no API of its own - its conditions page and webcams are both
# hosted by the volunteer-run Santiam Pass Ski Patrol site (santiampsp.org),
# an old-school Weather Display station page. Plain HTML, no JS/JSON, so it's
# scraped with regex rather than a JSON call. Small/stable site, unlikely to
# redesign, but still not an official API.
WEATHER_URL = "https://santiampsp.org/wx/weather.htm"

# All 8 images are hosted on santiampsp.org with no individual per-image
# page - Hoodoo's own public webcams page is where these are actually meant
# to be viewed, so every cam links there rather than to the raw image host.
WEBCAMS_PAGE_URL = "https://hoodoo.com/the-mountain/webcams/"

# cam id -> label, from hoodoo.com/the-mountain/webcams/
WEBCAMS = {
    16: "Base Area",
    3: "Top of Manzanita",
    2: "Top of Ed",
    4: "Top of Easy Rider",
    12: "Hoodoo Parking Lot",
    1: "Hoodoo Summit",
    "2b": 'Hayrick Butte & "Gripper" run from top of Ed chair',
    10: "Hoodoo Parking Lot View #2",
}

ROW_PATTERN = re.compile(
    r'<A HREF="weather9\.htm#\w+">\s*([^<]+?)\s*</A>\s*</TD>\s*'
    r'<TD ALIGN=CENTER>\s*<FONT SIZE="\+2">\s*([^<]+?)\s*</FONT>'
)

# The station's "Wind" field mixes full words ("West @ 6 MPH") and
# abbreviations ("WSW @ 8 MPH") depending on the reading - cover both.
COMPASS_TO_DEG = {
    "N": 0, "NORTH": 0,
    "NNE": 22.5,
    "NE": 45, "NORTHEAST": 45,
    "ENE": 67.5,
    "E": 90, "EAST": 90,
    "ESE": 112.5,
    "SE": 135, "SOUTHEAST": 135,
    "SSE": 157.5,
    "S": 180, "SOUTH": 180,
    "SSW": 202.5,
    "SW": 225, "SOUTHWEST": 225,
    "WSW": 247.5,
    "W": 270, "WEST": 270,
    "WNW": 292.5,
    "NW": 315, "NORTHWEST": 315,
    "NNW": 337.5,
}

WIND_PATTERN = re.compile(r"([A-Za-z]+)\s*@\s*([\d.]+)\s*MPH", re.I)

# The snow-depth row has a small trend table next to it (Max/Min/1-3-6-12-24
# Hr change), and separately a running season total ("Snowfall since Oct
# 1st"). No 48hr/7day figures exist anywhere on this site or Hoodoo's own -
# their conditions page is stale prose from last season, not a live feed.
SNOW_TREND_PATTERN = re.compile(
    r'<TR><TD><FONT size=-1 COLOR=#\w+>\s*([\w\s]+?)\s*</FONT></TD>\s*'
    r'<TD><FONT size=-1>\s*([^<]+?)\s*</FONT></TD></TR>'
)
SEASON_TOTAL_PATTERN = re.compile(
    r'Snowfall</A>\s*<FONT SIZE="-1">since Oct 1st</FONT>\s*<BR>([\d.]+)"'
)


def get_weather():
    resp = requests.get(WEATHER_URL, headers=HEADERS)
    resp.raise_for_status()
    return dict(ROW_PATTERN.findall(resp.text))


def get_snow_totals():
    resp = requests.get(WEATHER_URL, headers=HEADERS)
    resp.raise_for_status()
    html = resp.text

    trend = dict(SNOW_TREND_PATTERN.findall(html))
    season_match = SEASON_TOTAL_PATTERN.search(html)

    return {
        "trend": trend,  # e.g. {"24 Hr": "0.1\"", "12 Hr": "0.1\"", ...}
        "season_total_in": float(season_match.group(1)) if season_match else None,
    }


def parse_wind(wind_str):
    match = WIND_PATTERN.search(wind_str or "")
    if not match:
        return None, None
    direction_deg = COMPASS_TO_DEG.get(match.group(1).upper())
    return float(match.group(2)), direction_deg


def get_cam_url(cam_id):
    return f"https://santiampsp.org/wx/weather{cam_id}.jpg"


if __name__ == "__main__":
    print("=== Hoodoo / Santiam Pass Conditions ===")
    weather = get_weather()
    for label, value in weather.items():
        print(f"{label}: {value}")

    speed, direction = parse_wind(weather.get("Wind"))
    print(f"\nParsed wind: {speed} mph @ {direction}°")

    print("\n=== Snow Totals ===")
    print(get_snow_totals())

    print("\n=== Webcam still-image URLs ===")
    for cam_id, label in WEBCAMS.items():
        print(f"{label}: {get_cam_url(cam_id)}")
