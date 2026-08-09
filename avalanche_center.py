import requests

HEADERS = {
    "User-Agent": "CentralOregonConditions (brian.butcher.91@gmail.com)"
}

# Central Oregon Avalanche Center runs on the same public national platform
# as avalanche.org, used by avalanche centers across the US. No key needed.
BASE_URL = "https://api.avalanche.org/v2/public"
CENTER_ID = "COAA"

ZONES = {
    "Central Cascades": 2470,
    "Newberry": 2471,
}


def get_forecast(zone_id):
    resp = requests.get(
        f"{BASE_URL}/product",
        headers=HEADERS,
        params={"type": "forecast", "center_id": CENTER_ID, "zone_id": zone_id},
    )
    resp.raise_for_status()
    return resp.json()


def print_forecast(zone_name, data):
    print(f"\n=== {zone_name} Avalanche Forecast ===")
    print(f"Published: {data.get('published_time')}")
    print(f"Author: {data.get('author')}")

    danger = data.get("danger", [])
    if danger:
        for level in danger:
            print(f"{level.get('valid_day')} ({level.get('elevation_band')}): "
                  f"danger level {level.get('rating')}")
    else:
        print(f"Danger level: {data.get('danger_level_text', 'no rating')}")

    bottom_line = data.get("bottom_line", "")
    print(f"\nBottom line:\n{bottom_line}")


if __name__ == "__main__":
    for zone_name, zone_id in ZONES.items():
        forecast = get_forecast(zone_id)
        print_forecast(zone_name, forecast)
