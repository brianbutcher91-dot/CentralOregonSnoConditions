"""
GFS 72-hour snowfall (snow depth change) forecast, animated. Source is
NCEP's Model Analyses and Guidance site (mag.ncep.noaa.gov) - found by
working through its own model/area/product picker (GFS -> CONUS ->
Precipitation -> "Snow Depth Change from F00") and reading the resulting
requests: each forecast hour is its own static GIF, not one pre-built
animation, e.g.:
  https://mag.ncep.noaa.gov/data/gfs/{cycle}/conus/snodpth_chng/gfs_conus_{fhr:03d}_snodpth_chng.gif
"cycle" is one of 00/06/12/18 - not a date-stamped run, just a rolling slot
that gets overwritten in place once that synoptic hour's run finishes
processing (confirmed via Last-Modified headers: requesting all four at once
shows three from today and one still holding yesterday's run, whichever
hasn't completed yet). There's also no pre-cropped Pacific Northwest/Oregon
region upstream - GFS on MAG only offers whole-CONUS or broader Pacific-wide
areas - so unlike the GOES satellite sectors (which link straight to NOAA's
own ready-made images), this crops and reassembles the frames itself into
one real animated GIF, saved locally and served as a static site asset.
"""
import datetime
import io
from email.utils import parsedate_to_datetime

import requests
from PIL import Image, ImageDraw, ImageFont

HEADERS = {
    "User-Agent": "CentralOregonConditions (brian.butcher.91@gmail.com)"
}

BASE_URL = "https://mag.ncep.noaa.gov/data/gfs"
AREA = "conus"
LAYER = "snodpth_chng"
CYCLES = ["00", "06", "12", "18"]

# Every 3 hours out to 72 (24 frames) - matches the common convention for
# these accumulation loops and keeps the per-build download count
# reasonable; each frame is a running total since forecast hour 0, so
# hourly resolution wouldn't add much over 3-hourly for a "watch the total
# grow" animation.
FORECAST_HOURS = list(range(3, 73, 3))

# Pixel box (left, top, right, bottom) cropping MAG's full-CONUS frame
# (1280x1024) down to a "Northwest US" regional view - WA/OR/ID plus enough
# surrounding context (western MT/WY, UT, NV, N-CA, a strip of Pacific
# Ocean) to read well, matching the framing of tropicaltidbits.com's own
# "nwus" GFS region (a reference the user pointed to after the initial,
# much tighter WA/OR-only crop felt too zoomed in). Found by downloading one
# frame and eyeballing state-border pixel positions against it - MAG's map
# projection and framing is identical across every cycle and forecast hour,
# so this box doesn't need to be recomputed per run.
PNW_CROP_BOX = (100, 150, 570, 540)

OUTPUT_PATH = "gfs_snowfall_pnw.gif"

# Sampled directly from a real frame's legend swatches (RGB at the center of
# each color band), in the same high-to-low order the source image uses.
# Each entry is the lower bound (inches) of that color's band.
LEGEND = [
    (72.0, "#FFE4DC"), (60.0, "#FFAEB9"), (48.0, "#FFA54F"), (36.0, "#FF7F00"),
    (30.0, "#EE4000"), (24.0, "#CD0000"), (18.0, "#CD8500"), (15.0, "#FFD700"),
    (12.0, "#FFFF00"), (10.0, "#912CEE"), (8.0, "#8B008B"), (6.0, "#FF00FF"),
    (4.0, "#008B00"), (3.0, "#00CD00"), (2.0, "#00FF00"), (1.0, "#104E8B"),
    (0.5, "#00B2EE"), (0.1, "#00EEEE"),
]


def _frame_url(cycle, forecast_hour):
    return f"{BASE_URL}/{cycle}/{AREA}/{LAYER}/gfs_{AREA}_{forecast_hour:03d}_{LAYER}.gif"


def _pick_cycle():
    # Each of the 4 daily slots always resolves to *some* file (whichever
    # run last completed for that slot), so freshness has to be compared
    # via Last-Modified rather than treating a 200 as "this cycle is new".
    best_cycle, best_mtime = None, None
    for cycle in CYCLES:
        url = _frame_url(cycle, FORECAST_HOURS[-1])
        resp = requests.head(url, headers=HEADERS)
        if resp.status_code != 200 or "Last-Modified" not in resp.headers:
            continue
        mtime = parsedate_to_datetime(resp.headers["Last-Modified"])
        if best_mtime is None or mtime > best_mtime:
            best_cycle, best_mtime = cycle, mtime
    if best_cycle is None:
        raise RuntimeError("No GFS snow depth change cycle available on MAG")
    return best_cycle, best_mtime


def _init_time(cycle, cycle_mtime):
    # cycle_mtime is when the run *finished processing* (a few hours after
    # it actually started), not the model's init/valid-time-zero. The real
    # init hour is exactly the cycle slot (00/06/12/18 UTC); the date is
    # whatever date cycle_mtime falls on, unless processing happened to
    # finish just after UTC midnight relative to an init that started the
    # day before - in which case step back a day.
    init = cycle_mtime.astimezone(datetime.timezone.utc).replace(
        hour=int(cycle), minute=0, second=0, microsecond=0)
    if init > cycle_mtime:
        init -= datetime.timedelta(days=1)
    return init


def _label_frame(frame, init_dt, forecast_hour):
    # Crop deliberately excludes MAG's own title bar (it's centered across
    # the full 1280px-wide source frame, so our narrower crop would only
    # ever show a truncated fragment of it) - stamp a real, correctly
    # computed valid-time label instead of trying to preserve a slice of
    # NOAA's original text.
    valid_time = init_dt + datetime.timedelta(hours=forecast_hour)
    text = f"+{forecast_hour}h - valid {valid_time.strftime('%a %b %d, %H:%M UTC')}"

    draw = ImageDraw.Draw(frame)
    font = ImageFont.load_default(size=15)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    pad = 4
    draw.rectangle([0, 0, right - left + pad * 2, bottom - top + pad * 2], fill=(255, 255, 255))
    draw.text((pad, pad), text, fill=(0, 0, 0), font=font)
    return frame


def build_snowfall_gif():
    cycle, cycle_mtime = _pick_cycle()
    init_dt = _init_time(cycle, cycle_mtime)

    frames = []
    for hour in FORECAST_HOURS:
        resp = requests.get(_frame_url(cycle, hour), headers=HEADERS)
        resp.raise_for_status()
        frame = Image.open(io.BytesIO(resp.content)).convert("RGB").crop(PNW_CROP_BOX)
        frame = _label_frame(frame, init_dt, hour)
        frames.append(frame)

    frames[0].save(
        OUTPUT_PATH,
        save_all=True,
        append_images=frames[1:],
        duration=250,
        loop=0,
    )

    return {
        "path": OUTPUT_PATH,
        "cycle_run_at": init_dt.isoformat(),
        "forecast_hours": FORECAST_HOURS,
        "legend": LEGEND,
    }


if __name__ == "__main__":
    info = build_snowfall_gif()
    print(f"Wrote {info['path']} - cycle run at {info['cycle_run_at']}, "
          f"{len(info['forecast_hours'])} frames ({info['forecast_hours'][0]}-{info['forecast_hours'][-1]}h)")
