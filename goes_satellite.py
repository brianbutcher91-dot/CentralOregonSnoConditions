import requests

HEADERS = {
    "User-Agent": "CentralOregonConditions (brian.butcher.91@gmail.com)"
}

# NOAA/NESDIS/STAR GOES-West (GOES-18) imagery CDN. Found via the sector
# viewer at star.nesdis.noaa.gov/GOES - "latest.jpg" is a stable alias each
# sector/band folder exposes, no key needed, CORS wide open. Directory
# browsing works directly against the CDN too (cdn.star.nesdis.noaa.gov/.../
# shows a real index), which is how each GIF_FILENAMES entry was confirmed.
BASE_URL = "https://cdn.star.nesdis.noaa.gov/GOES18/ABI"
BAND = "13"  # Clean Longwave IR - the standard IR channel for storm tracking

# "Pacific Northwest" for the close regional view, "North Pacific" for a
# macro view of storms still approaching from offshore, "PACUS" for GOES-
# West's full CONUS-equivalent product - STAR's own site labels this "Pacific
# U.S. (PACUS)" (see conus.php?sat=G18) since GOES-West doesn't have a sector
# literally named "conus" under ABI/SECTOR the way pnw/np do - it lives under
# its own ABI/CONUS path instead, hence the folder value below differing in
# shape from the other two.
SECTORS = {
    "Pacific Northwest": "SECTOR/pnw",
    "North Pacific (macro)": "SECTOR/np",
    "Pacific US (PACUS)": "CONUS",
}

# Animated loop GIFs, found via directory listing (cdn.star.nesdis.noaa.gov
# has no index page, but browsing straight to a folder shows one). Filename
# resolution differs per sector (pnw=600x600, np=900x540, CONUS=625x375), so
# these are looked up directly rather than templated like "latest.jpg".
GIF_FILENAMES = {
    "SECTOR/pnw": "GOES18-PNW-13-600x600.gif",
    "SECTOR/np": "GOES18-NP-13-900x540.gif",
    "CONUS": "GOES18-CONUS-13-625x375.gif",
}


def get_image_info(sector_code):
    url = f"{BASE_URL}/{sector_code}/{BAND}/{GIF_FILENAMES[sector_code]}"
    resp = requests.head(url, headers=HEADERS)
    resp.raise_for_status()
    return {
        "url": url,
        "last_modified": resp.headers.get("Last-Modified"),
    }


def print_info(sector_name, info):
    print(f"{sector_name}: {info['url']} (updated {info['last_modified']})")


if __name__ == "__main__":
    for name, sector_code in SECTORS.items():
        info = get_image_info(sector_code)
        print_info(name, info)
