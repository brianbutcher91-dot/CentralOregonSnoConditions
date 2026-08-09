import os
import re

import requests
from dotenv import load_dotenv

# Reads .env locally (gitignored, see .env.example) - in GitHub Actions this
# is a no-op since .env doesn't exist there and the real value comes from a
# repo secret injected as a normal environment variable instead.
load_dotenv()
ODOT_API_KEY = os.environ["ODOT_API_KEY"]

# TripCheck's own single-camera viewer takes their internal picture id
# ("pid"), not ODOT's device-id - it's embedded in the image filename
# (".../Sisters_pid653.jpg" -> 653), not a separate API field. Confirmed
# working: https://www.tripcheck.com/Pages/View-Custom-Cameras/?CamIds=653
TRIPCHECK_PID_PATTERN = re.compile(r"_pid(\d+)\.\w+$", re.IGNORECASE)


def get_tripcheck_link(cctv_url):
    match = TRIPCHECK_PID_PATTERN.search(cctv_url)
    if not match:
        return "https://www.tripcheck.com/"
    return f"https://www.tripcheck.com/Pages/View-Custom-Cameras/?CamIds={match.group(1)}"

HEADERS = {
    "Ocp-Apim-Subscription-Key": ODOT_API_KEY,
    "Accept": "application/json",
}

# DeviceName does a "contains" search. Pulling by name instead of RouteId
# keeps this to just the handful of cams we actually want instead of every
# cam on US20/OR58 (30+ cams).
CAMERAS = {
    # "Century" alone also matches an unrelated Portland-area device
    # ("Cornell Rd at Century Blvd") - "Century Dr" is specific enough to
    # only match the Century Drive cams near Mt. Bachelor.
    "Century Drive": "Century Dr",
    "Santiam Pass": "Santiam Pass",
    "Tombstone Pass": "Tombstone",
    "Willamette Pass": "Willamette Pass",
}


def get_cams(device_name):
    url = "https://api.odot.state.or.us/tripcheck/Cctv/Inventory"
    params = {"DeviceName": device_name}
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()["CCTVInventoryRequest"]


def print_cams(location_name, cams):
    print(f"\n=== {location_name} ===")
    for cam in cams:
        print(f"{cam['device-name']} (MP {cam['milepoint']}): {cam['cctv-url']}")


if __name__ == "__main__":
    for name, device_name in CAMERAS.items():
        cams = get_cams(device_name)
        print_cams(name, cams)
