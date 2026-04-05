#!/usr/bin/env python3
"""
PELE — Hawai'i Volcanoes Observatory Dashboard
Data fetcher: pulls earthquake catalog, volcano alert levels, and HVO
observatory messages from USGS APIs. Writes static JSON to data/ for
the frontend to consume client-side.

Uses Python 3.12 stdlib only (no pip dependencies).
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
import sys
import os

HST = timezone(timedelta(hours=-10))
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {"User-Agent": "PELE-Dashboard/1.0 (github.com/bdgroves/PELE)"}


def fetch_json(url, label=""):
    """Fetch JSON from a URL with basic error handling."""
    print(f"  Fetching {label or url}...")
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except (urllib.error.URLError, json.JSONDecodeError, Exception) as e:
        print(f"  ⚠ Error fetching {label}: {e}")
        return None


def fetch_earthquakes():
    """
    Fetch 7-day earthquake catalog within 100 km of Kīlauea summit
    from the USGS FDSN Event Web Service.
    """
    print("\n🌋 Fetching earthquake data...")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)

    url = (
        "https://earthquake.usgs.gov/fdsnws/event/1/query?"
        "format=geojson"
        f"&starttime={start.strftime('%Y-%m-%d')}"
        f"&endtime={end.strftime('%Y-%m-%d')}"
        "&latitude=19.421&longitude=-155.287"
        "&maxradiuskm=100"
        "&orderby=time"
        "&limit=500"
    )

    data = fetch_json(url, "USGS Earthquake Catalog")
    if not data or "features" not in data:
        print("  ⚠ No earthquake data returned")
        return

    quakes = data["features"]
    print(f"  ✓ {len(quakes)} earthquakes in past 7 days")

    # Compute summary stats
    mags = [q["properties"].get("mag") for q in quakes if q["properties"].get("mag") is not None]
    depths = [q["geometry"]["coordinates"][2] for q in quakes if q["geometry"]["coordinates"][2] is not None]

    summary = {
        "total": len(quakes),
        "largest_mag": max(mags) if mags else None,
        "avg_depth_km": round(sum(depths) / len(depths), 1) if depths else None,
        "m2_plus": len([m for m in mags if m >= 2.0]),
        "m3_plus": len([m for m in mags if m >= 3.0]),
        "period_start": start.strftime("%Y-%m-%d"),
        "period_end": end.strftime("%Y-%m-%d"),
    }

    # Trim to essential fields for smaller JSON
    trimmed = []
    for q in quakes:
        props = q["properties"]
        coords = q["geometry"]["coordinates"]
        trimmed.append({
            "mag": props.get("mag"),
            "place": props.get("place", "Unknown"),
            "time": props.get("time"),
            "depth": coords[2] if len(coords) > 2 else None,
            "lat": coords[1],
            "lon": coords[0],
            "type": props.get("type", "earthquake"),
            "url": props.get("url"),
        })

    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "generated_hst": datetime.now(HST).strftime("%Y-%m-%d %H:%M HST"),
        "summary": summary,
        "earthquakes": trimmed,
    }

    write_json("earthquakes.json", output)
    print(f"  ✓ Wrote earthquakes.json ({summary['total']} events, largest M{summary['largest_mag']})")


def fetch_volcano_alerts():
    """
    Fetch current volcano alert levels from the USGS Volcano Hazards
    HANS public API.
    """
    print("\n🔴 Fetching volcano alert levels...")

    # Elevated volcanoes (WATCH/ADVISORY/WARNING)
    elevated = fetch_json(
        "https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes",
        "Elevated volcanoes"
    )

    # All monitored volcanoes
    monitored = fetch_json(
        "https://volcanoes.usgs.gov/hans-public/api/volcano/getMonitoredVolcanoes",
        "Monitored volcanoes"
    )

    # Filter to Hawaiian volcanoes
    hawaii_names = {
        "Kilauea", "Kīlauea",
        "Mauna Loa",
        "Hualalai", "Hualālai",
        "Mauna Kea",
        "Haleakala", "Haleakalā",
        "Kamaʻehuakanaloa",
    }

    hawaii_volcanoes = []

    # Process monitored list first
    if monitored and isinstance(monitored, list):
        for v in monitored:
            name = v.get("vName", v.get("volcanoName", ""))
            if any(h.lower() in name.lower() for h in hawaii_names):
                hawaii_volcanoes.append({
                    "name": name,
                    "alert_level": v.get("alertLevel", v.get("alert_level", "NORMAL")),
                    "color_code": v.get("colorCode", v.get("color_code", "GREEN")),
                    "observatory": v.get("obsCode", "HVO"),
                    "latitude": v.get("latitude"),
                    "longitude": v.get("longitude"),
                    "elevation_m": v.get("elevationM", v.get("elevation")),
                })

    # Override with elevated data if available (more current)
    if elevated and isinstance(elevated, list):
        for v in elevated:
            name = v.get("vName", v.get("volcanoName", ""))
            if any(h.lower() in name.lower() for h in hawaii_names):
                # Update existing entry
                for i, hv in enumerate(hawaii_volcanoes):
                    if hv["name"].lower() == name.lower():
                        hawaii_volcanoes[i]["alert_level"] = v.get("alertLevel", v.get("alert_level", "NORMAL"))
                        hawaii_volcanoes[i]["color_code"] = v.get("colorCode", v.get("color_code", "GREEN"))
                        break

    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "generated_hst": datetime.now(HST).strftime("%Y-%m-%d %H:%M HST"),
        "volcanoes": hawaii_volcanoes,
        "elevated_count": len(elevated) if elevated else 0,
    }

    write_json("volcanoes.json", output)
    print(f"  ✓ Wrote volcanoes.json ({len(hawaii_volcanoes)} Hawaiian volcanoes)")


def fetch_hvo_notices():
    """
    Fetch the latest HVO notices/updates for Kīlauea from the
    HANS public API.
    """
    print("\n📋 Fetching HVO notices...")

    # Try the notice endpoint
    url = "https://volcanoes.usgs.gov/hans-public/api/notice/getNotices?volcanoName=Kilauea&limit=5"
    data = fetch_json(url, "HVO Notices (Kīlauea)")

    notices = []
    if data and isinstance(data, list):
        for n in data:
            notices.append({
                "title": n.get("title", ""),
                "date": n.get("pubDate", n.get("sentDate", "")),
                "alert_level": n.get("alertLevel", ""),
                "color_code": n.get("colorCode", ""),
                "message": n.get("noticeText", n.get("message", ""))[:500],  # truncate
                "url": n.get("noticeUrl", ""),
            })

    # Also try Mauna Loa
    url_ml = "https://volcanoes.usgs.gov/hans-public/api/notice/getNotices?volcanoName=Mauna%20Loa&limit=2"
    data_ml = fetch_json(url_ml, "HVO Notices (Mauna Loa)")

    ml_notices = []
    if data_ml and isinstance(data_ml, list):
        for n in data_ml:
            ml_notices.append({
                "title": n.get("title", ""),
                "date": n.get("pubDate", n.get("sentDate", "")),
                "alert_level": n.get("alertLevel", ""),
                "color_code": n.get("colorCode", ""),
                "message": n.get("noticeText", n.get("message", ""))[:500],
                "url": n.get("noticeUrl", ""),
            })

    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "generated_hst": datetime.now(HST).strftime("%Y-%m-%d %H:%M HST"),
        "kilauea_notices": notices,
        "mauna_loa_notices": ml_notices,
    }

    write_json("notices.json", output)
    print(f"  ✓ Wrote notices.json ({len(notices)} Kīlauea, {len(ml_notices)} Mauna Loa)")


def write_json(filename, data):
    """Write JSON with NaN sanitization."""
    path = os.path.join(DATA_DIR, filename)
    # NaN sanitization (learned the hard way on EDGAR)
    text = json.dumps(data, indent=2, default=str)
    text = text.replace(": NaN", ": null").replace(":NaN", ":null")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    print("=" * 60)
    print("PELE — Hawai'i Volcanoes Observatory Dashboard")
    print(f"Fetch started: {datetime.now(HST).strftime('%Y-%m-%d %H:%M:%S HST')}")
    print("=" * 60)

    fetch_earthquakes()
    fetch_volcano_alerts()
    fetch_hvo_notices()

    print("\n" + "=" * 60)
    print(f"✓ All data written to {DATA_DIR}")
    print(f"  Completed: {datetime.now(HST).strftime('%Y-%m-%d %H:%M:%S HST')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
