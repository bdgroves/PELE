#!/usr/bin/env python3
"""
PELE — Hawai'i Volcanoes Observatory Dashboard
Data fetcher: pulls earthquake catalog, volcano alert levels, and HVO
observatory messages from USGS APIs. Writes static JSON to data/ for
the frontend to consume client-side.

Uses Python 3.12 stdlib only (no pip dependencies).
"""

import json
import re
import html
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
import sys
import os

HST = timezone(timedelta(hours=-10))
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {"User-Agent": "PELE-Dashboard/1.0 (github.com/bdgroves/PELE)"}

# Set PELE_DEBUG=1 to dump raw HANS responses to data/_debug_*.json
DEBUG = os.environ.get("PELE_DEBUG") == "1"


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
            name = v.get("volcano_name", v.get("vName", v.get("volcanoName", "")))
            if any(h.lower() in name.lower() for h in hawaii_names):
                hawaii_volcanoes.append({
                    "name": name,
                    "alert_level": v.get("alert_level", v.get("alertLevel", "NORMAL")),
                    "color_code": v.get("color_code", v.get("colorCode", "GREEN")),
                    "observatory": v.get("obs_abbr", v.get("obsCode", "HVO")),
                    "latitude": v.get("latitude"),
                    "longitude": v.get("longitude"),
                    "elevation_m": v.get("elevationM", v.get("elevation")),
                })

    # Override/add from elevated data (more current)
    if elevated and isinstance(elevated, list):
        for v in elevated:
            name = v.get("volcano_name", v.get("vName", v.get("volcanoName", "")))
            if any(h.lower() in name.lower() for h in hawaii_names):
                alert = v.get("alert_level", v.get("alertLevel", "NORMAL"))
                color = v.get("color_code", v.get("colorCode", "GREEN"))
                # Update existing entry or add new one
                found = False
                for i, hv in enumerate(hawaii_volcanoes):
                    if hv["name"].lower() == name.lower():
                        hawaii_volcanoes[i]["alert_level"] = alert
                        hawaii_volcanoes[i]["color_code"] = color
                        found = True
                        break
                if not found:
                    hawaii_volcanoes.append({
                        "name": name,
                        "alert_level": alert,
                        "color_code": color,
                        "observatory": v.get("obs_abbr", "HVO"),
                    })

    # Preserve kilauea_episode if it exists in the current file
    kilauea_episode = None
    existing_path = os.path.join(DATA_DIR, "volcanoes.json")
    if os.path.exists(existing_path):
        try:
            with open(existing_path, encoding="utf-8") as f:
                existing = json.load(f)
                kilauea_episode = existing.get("kilauea_episode")
        except Exception:
            pass

    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "generated_hst": datetime.now(HST).strftime("%Y-%m-%d %H:%M HST"),
        "volcanoes": hawaii_volcanoes,
        "elevated_count": len(elevated) if elevated else 0,
    }

    if kilauea_episode is not None:
        output["kilauea_episode"] = kilauea_episode

    write_json("volcanoes.json", output)
    print(f"  ✓ Wrote volcanoes.json ({len(hawaii_volcanoes)} Hawaiian volcanoes)")


def _dump_debug(name, payload):
    """Dump raw HANS response for field inspection when PELE_DEBUG=1."""
    if not DEBUG or payload is None:
        return
    path = os.path.join(DATA_DIR, f"_debug_{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"  🐛 Wrote debug dump: {path}")


def _strip_html(s):
    """Strip HTML tags and decode entities. HANS returns rich HTML in summaries."""
    if not s:
        return ""
    # Drop <br>, </p>, </li> first so whitespace is preserved between blocks
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"</(p|li|div|h\d)>", " ", s, flags=re.IGNORECASE)
    # Strip remaining tags
    s = re.sub(r"<[^>]+>", "", s)
    # Decode entities (&nbsp;, &amp;, etc.)
    s = html.unescape(s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_notice(n, default_title):
    """
    Flatten HANS's shifting schema into one consistent shape.

    HANS returns a wrapper object with noticeSections containing
    per-observatory content. Prefer section-level synopsis (the
    short one-liner) for the message, fall back to summary.
    """
    if not isinstance(n, dict):
        return None

    # Pull the first meaningful section if present
    sections = n.get("noticeSections") or []
    first_section = sections[0] if sections else {}

    # Short human-readable message: prefer synopsis, then summary
    raw_message = (
        first_section.get("synopsis") or
        n.get("synopsis") or
        first_section.get("summary") or
        n.get("volcanic_activity_summary") or
        n.get("volcanicActivitySummary") or
        n.get("notice_text") or n.get("noticeText") or
        n.get("message") or n.get("text") or
        n.get("body") or n.get("description") or ""
    )
    message = _strip_html(raw_message)

    title = (
        n.get("noticeTitle") or n.get("notice_title") or
        n.get("title") or
        first_section.get("vName") or
        n.get("volcano_name") or n.get("volcanoName") or
        default_title
    )

    date = (
        n.get("sentUtc") or n.get("sent_utc") or
        n.get("pubDate") or n.get("sentDate") or
        n.get("sent") or n.get("issued") or
        n.get("issue_date") or ""
    )

    alert_level = (
        n.get("noticeHighestAlertLevel") or
        first_section.get("alertLevel") or
        n.get("alert_level") or n.get("alertLevel") or ""
    )

    color_code = (
        n.get("noticeHighestColorCode") or
        first_section.get("colorCode") or
        n.get("color_code") or n.get("colorCode") or ""
    )

    url = (
        n.get("noticeUrl") or n.get("notice_url") or
        first_section.get("vUrl") or n.get("url") or ""
    )

    notice_type = n.get("noticeType") or n.get("noticeTypeCd") or ""

    return {
        "title": title,
        "date": date,
        "alert_level": alert_level,
        "color_code": color_code,
        "message": message[:500] if message else "",
        "url": url,
        "notice_type": notice_type,
    }


def _collect_notices(vnum, volcano_name, default_title):
    """
    Pull from BOTH HANS endpoints for one volcano and merge.

    newestForVolcano tends to go stale during active eruptions —
    HVO sends Volcano Activity Notices to getNotices that don't
    always rewrite the 'newest' object. Hit both, merge, dedupe.
    """
    results = []
    # URL-encode volcano name (handles "Mauna Loa" space)
    encoded_name = urllib.parse.quote(volcano_name)
    debug_slug = volcano_name.lower().replace(" ", "_")

    # Endpoint 1: newestForVolcano — returns single wrapper object
    newest = fetch_json(
        f"https://volcanoes.usgs.gov/hans-public/api/volcano/newestForVolcano/{vnum}",
        f"Newest {volcano_name} notice"
    )
    _dump_debug(f"newest_{debug_slug}", newest)
    if newest:
        items = newest if isinstance(newest, list) else [newest]
        for n in items:
            norm = _normalize_notice(n, default_title)
            if norm:
                results.append(norm)

    # Endpoint 2: getNotices — returns list of wrapper objects
    recent = fetch_json(
        f"https://volcanoes.usgs.gov/hans-public/api/notice/getNotices"
        f"?volcanoName={encoded_name}&limit=5",
        f"{volcano_name} notices feed"
    )
    _dump_debug(f"notices_{debug_slug}", recent)
    if recent and isinstance(recent, list):
        for n in recent:
            norm = _normalize_notice(n, default_title)
            if norm:
                results.append(norm)

    # Dedupe on (date, notice_type) — same notice appears in both endpoints
    seen = set()
    deduped = []
    for r in results:
        if not r.get("message"):
            continue
        key = (r.get("date", ""), r.get("notice_type", ""), r.get("title", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    deduped.sort(key=lambda x: x.get("date", ""), reverse=True)

    got_response = (newest is not None) or (recent is not None)
    if got_response and not deduped:
        print(f"  ⚠ {volcano_name}: HANS returned data but no notices "
              f"extracted — likely schema change. Run with PELE_DEBUG=1 "
              f"to dump raw responses.")

    return deduped


def fetch_hvo_notices():
    """
    Fetch the latest HVO notices/updates for Kīlauea and Mauna Loa.

    Strategy:
      1. Always hit BOTH newestForVolcano AND getNotices — during
         ongoing eruptions, getNotices has newer messages that
         newestForVolcano doesn't surface.
      2. Merge + dedupe, sort desc by date.
      3. If the final list is empty but existing notices.json has
         content, preserve the old data rather than blanking
         the page (stale > blank).
    """
    print("\n📋 Fetching HVO notices...")

    # VNUM 332010 = Kīlauea, 332020 = Mauna Loa
    notices = _collect_notices(332010, "Kilauea", "Kīlauea Update")
    ml_notices = _collect_notices(332020, "Mauna Loa", "Mauna Loa Update")

    # Preserve-on-failure: if fetch returned nothing but we have
    # existing data, keep it rather than blanking the page.
    existing_path = os.path.join(DATA_DIR, "notices.json")
    if (not notices or not ml_notices) and os.path.exists(existing_path):
        try:
            with open(existing_path, encoding="utf-8") as f:
                existing = json.load(f)
            if not notices and existing.get("kilauea_notices"):
                print("  ⚠ Kīlauea fetch empty — preserving existing notices")
                notices = existing["kilauea_notices"]
            if not ml_notices and existing.get("mauna_loa_notices"):
                print("  ⚠ Mauna Loa fetch empty — preserving existing notices")
                ml_notices = existing["mauna_loa_notices"]
        except Exception as e:
            print(f"  ⚠ Could not read existing notices.json: {e}")

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
    if DEBUG:
        print("🐛 DEBUG mode — raw HANS responses will be dumped to data/_debug_*.json")
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
