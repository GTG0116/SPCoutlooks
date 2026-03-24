"""
fetch_outlooks.py
Downloads SPC outlook GeoJSON data for days 1-8.
"""

import json
import os
import sys
import time
import requests
from datetime import datetime, timezone

BASE_URL = "https://www.spc.noaa.gov/products/outlook"
EXT_URL  = "https://www.spc.noaa.gov/products/exper/day4-8"

# Each entry: (day, outlook_type, url, filename)
OUTLOOK_SOURCES = [
    # Day 1
    (1, "categorical",   f"{BASE_URL}/day1otlk_cat.nolyr.geojson",  "categorical.geojson"),
    (1, "tornado",       f"{BASE_URL}/day1otlk_torn.nolyr.geojson", "tornado.geojson"),
    (1, "wind",          f"{BASE_URL}/day1otlk_wind.nolyr.geojson", "wind.geojson"),
    (1, "hail",          f"{BASE_URL}/day1otlk_hail.nolyr.geojson", "hail.geojson"),
    # Day 2
    (2, "categorical",   f"{BASE_URL}/day2otlk_cat.nolyr.geojson",  "categorical.geojson"),
    (2, "tornado",       f"{BASE_URL}/day2otlk_torn.nolyr.geojson", "tornado.geojson"),
    (2, "wind",          f"{BASE_URL}/day2otlk_wind.nolyr.geojson", "wind.geojson"),
    (2, "hail",          f"{BASE_URL}/day2otlk_hail.nolyr.geojson", "hail.geojson"),
    # Day 3
    (3, "categorical",   f"{BASE_URL}/day3otlk_cat.nolyr.geojson",  "categorical.geojson"),
    (3, "probabilistic", f"{BASE_URL}/day3otlk_prob.nolyr.geojson", "probabilistic.geojson"),
    # Days 4-8 (extended, probabilistic only)
    (4, "probabilistic", f"{EXT_URL}/day4prob.geojson",  "probabilistic.geojson"),
    (5, "probabilistic", f"{EXT_URL}/day5prob.geojson",  "probabilistic.geojson"),
    (6, "probabilistic", f"{EXT_URL}/day6prob.geojson",  "probabilistic.geojson"),
    (7, "probabilistic", f"{EXT_URL}/day7prob.geojson",  "probabilistic.geojson"),
    (8, "probabilistic", f"{EXT_URL}/day8prob.geojson",  "probabilistic.geojson"),
]

HEADERS = {
    "User-Agent": "SPCOutlookViewer/1.0 (github.com/gtg0116/spcoutlooks)"
}


def fetch_geojson(url, retries=3, backoff=2):
    """Download a GeoJSON file with retry logic."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
            # Validate it's a FeatureCollection
            if data.get("type") not in ("FeatureCollection", "Feature"):
                raise ValueError(f"Unexpected GeoJSON type: {data.get('type')}")
            return data
        except Exception as e:
            print(f"  Attempt {attempt + 1}/{retries} failed for {url}: {e}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
    return None


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def fetch_all(output_root="output"):
    """Fetch all outlooks and save to output_root/day{N}/filename."""
    results = {}
    ensure_dir(output_root)

    for day, outlook_type, url, filename in OUTLOOK_SOURCES:
        day_dir = os.path.join(output_root, f"day{day}")
        ensure_dir(day_dir)
        dest = os.path.join(day_dir, filename)

        print(f"Fetching Day {day} {outlook_type}: {url}")
        data = fetch_geojson(url)

        if data is None:
            print(f"  FAILED – keeping existing file if present.")
            # Record as failed only if no existing file
            if not os.path.exists(dest):
                results.setdefault(day, {})[outlook_type] = None
            else:
                print(f"  Using cached: {dest}")
                results.setdefault(day, {})[outlook_type] = dest
            continue

        # Annotate with fetch metadata
        data["_meta"] = {
            "source_url": url,
            "fetched_utc": datetime.now(timezone.utc).isoformat(),
            "day": day,
            "outlook_type": outlook_type,
        }

        with open(dest, "w") as f:
            json.dump(data, f, separators=(",", ":"))

        print(f"  Saved → {dest} ({len(data.get('features', []))} features)")
        results.setdefault(day, {})[outlook_type] = dest

    return results


def write_manifest(results, output_root="output"):
    """Write manifest.json describing all available files."""
    manifest = {
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "days": {},
    }

    for day in range(1, 9):
        day_dir = os.path.join(output_root, f"day{day}")
        day_entry = {"available": [], "files": {}}

        for outlook_type in ("categorical", "tornado", "wind", "hail", "probabilistic"):
            geojson_path = os.path.join(day_dir, f"{outlook_type}.geojson")
            png_path = os.path.join(day_dir, f"{outlook_type}.png")
            if os.path.exists(geojson_path):
                day_entry["available"].append(outlook_type)
                day_entry["files"][outlook_type] = {
                    "geojson": f"output/day{day}/{outlook_type}.geojson",
                    "png": f"output/day{day}/{outlook_type}.png" if os.path.exists(png_path) else None,
                }

        interactive_path = os.path.join(day_dir, "interactive.html")
        if os.path.exists(interactive_path):
            day_entry["interactive"] = f"output/day{day}/interactive.html"

        manifest["days"][str(day)] = day_entry

    dest = os.path.join(output_root, "manifest.json")
    with open(dest, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest written → {dest}")
    return manifest


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "output"
    fetch_all(root)
    write_manifest({}, root)
