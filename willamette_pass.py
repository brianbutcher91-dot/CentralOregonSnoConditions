import re

import requests

HEADERS = {
    "User-Agent": "CentralOregonConditions (brian.butcher.91@gmail.com)"
}

# No official API. weather.json is a static file their WordPress theme
# uploads periodically (found via devtools network tab) - gives NOAA
# forecast + last-updated timestamps but not snow totals.
WEATHER_JSON_URL = "https://www.willamettepass.ski/wp-content/uploads/sites/13/m-json/weather.json"

# Snow totals + webcams are server-rendered HTML on this page, not JSON -
# scraped with regex. Webcams are embedded live YouTube streams, not still
# images, so the "URL" here is a video ID that could change if the resort
# restarts the broadcast under a new stream.
WEBCAMS_PAGE_URL = "https://www.willamettepass.ski/weather-conditions-webcams/webcams/"

SNOW_TOTALS_PATTERN = re.compile(
    r'm-snow-totals-top m-highlight-color">\s*([^<]+?)\s*</div>\s*'
    r'<div class="m-snow-totals-label[^"]*">\s*([^<]+?)\s*</div>'
)

WEBCAM_PATTERN = re.compile(
    r'data-lazy-src="(https://www\.youtube\.com/embed/[^"?]+)[^"]*".*?'
    r'class="m-mt-60 has-m-h-small-font-size">\s*([^<]+?)\s*</div>',
    re.DOTALL,
)


def get_forecast():
    resp = requests.get(WEATHER_JSON_URL, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def get_page_html():
    resp = requests.get(WEBCAMS_PAGE_URL, headers=HEADERS)
    resp.raise_for_status()
    return resp.text


def get_snow_totals(html):
    return {label: value for value, label in SNOW_TOTALS_PATTERN.findall(html)}


def get_webcams(html):
    return {label: url for url, label in WEBCAM_PATTERN.findall(html)}


if __name__ == "__main__":
    forecast = get_forecast()
    print("=== Willamette Pass Forecast (NOAA) ===")
    print(f"Current: {forecast['current_temperature']}F, {forecast['current_weather']}")
    for day in forecast["forecast"][:4]:
        print(f"{day['day']}: {day['day_forecast']}")

    html = get_page_html()

    print("\n=== Snow Totals ===")
    for label, value in get_snow_totals(html).items():
        print(f"{label}: {value}")

    print("\n=== Webcams (live YouTube streams) ===")
    for label, url in get_webcams(html).items():
        print(f"{label}: {url}")
