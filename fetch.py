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
import html.parser

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


# Named areas for tagging earthquakes. Simple distance rules, documented in the
# README; the point is a readable label, not a seismological classification.
KILAUEA_SUMMIT = (19.406, -155.283)    # Halemaʻumaʻu
MAUNA_LOA_SUMMIT = (19.475, -155.608)
PAHALA = (19.200, -155.480)            # long-running deep swarm under Pāhala


def _km(a, b):
    from math import radians, sin, cos, asin, sqrt
    la1, lo1, la2, lo2 = map(radians, (a[0], a[1], b[0], b[1]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * asin(sqrt(h))


def _region(lat, lon, depth):
    p = (lat, lon)
    if _km(p, KILAUEA_SUMMIT) <= 6:
        return "Kīlauea summit"
    if depth is not None and depth >= 20 and _km(p, PAHALA) <= 20:
        return "Pāhala (deep)"
    if _km(p, KILAUEA_SUMMIT) <= 25:
        return "Kīlauea rift zones"
    if _km(p, MAUNA_LOA_SUMMIT) <= 25:
        return "Mauna Loa"
    return "Elsewhere on the island"


def fetch_earthquakes():
    """
    30-day earthquake catalog within 100 km of Kīlauea summit from the USGS
    FDSN Event Web Service. No endtime: the service then returns everything up
    to now. (An endtime of today's *date* means midnight UTC and silently
    dropped the most recent hours.)
    """
    print("\n🌋 Fetching earthquake data...")
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=30)
    url = (
        "https://earthquake.usgs.gov/fdsnws/event/1/query?"
        "format=geojson"
        f"&starttime={start.strftime('%Y-%m-%dT%H:%M:%S')}"
        "&latitude=19.421&longitude=-155.287"
        "&maxradiuskm=100"
        "&orderby=time"
        "&limit=5000"
    )
    data = fetch_json(url, "USGS Earthquake Catalog (30 days)")
    if not data or "features" not in data:
        print("  ⚠ No earthquake data returned — keeping the existing file")
        return

    trimmed = []
    for q in data["features"]:
        props = q["properties"]
        coords = q["geometry"]["coordinates"]
        depth = coords[2] if len(coords) > 2 else None
        trimmed.append({
            "mag": props.get("mag"),
            "place": props.get("place", "Unknown"),
            "time": props.get("time"),
            "depth": depth,
            "lat": round(coords[1], 4),
            "lon": round(coords[0], 4),
            "region": _region(coords[1], coords[0], depth),
            "type": props.get("type", "earthquake"),
            "url": props.get("url"),
        })

    def stats(qs):
        mags = [q["mag"] for q in qs if q["mag"] is not None]
        depths = [q["depth"] for q in qs if q["depth"] is not None]
        return {
            "total": len(qs),
            "largest_mag": max(mags) if mags else None,
            "avg_depth_km": round(sum(depths) / len(depths), 1) if depths else None,
            "m2_plus": len([m for m in mags if m >= 2.0]),
            "m3_plus": len([m for m in mags if m >= 3.0]),
        }

    cutoff7 = (now - timedelta(days=7)).timestamp() * 1000
    last7 = [q for q in trimmed if (q["time"] or 0) >= cutoff7]
    summary = stats(last7)
    summary.update(period_start=(now - timedelta(days=7)).isoformat(), period_end=now.isoformat())
    summary_30 = stats(trimmed)

    # Daily counts by HST day, oldest first, with the regional split
    days = [(now.astimezone(HST) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    daily = {d: {"date": d, "total": 0, "m2_plus": 0, "summit": 0} for d in days}
    for q in trimmed:
        if q["time"] is None:
            continue
        d = datetime.fromtimestamp(q["time"] / 1000, tz=HST).strftime("%Y-%m-%d")
        if d in daily:
            daily[d]["total"] += 1
            daily[d]["m2_plus"] += 1 if (q["mag"] or 0) >= 2 else 0
            daily[d]["summit"] += 1 if q["region"] == "Kīlauea summit" else 0
    regions = {}
    for q in last7:
        regions[q["region"]] = regions.get(q["region"], 0) + 1

    output = {
        "generated": now.isoformat(),
        "generated_hst": now.astimezone(HST).strftime("%Y-%m-%d %H:%M HST"),
        "summary": summary,
        "summary_30d": summary_30,
        "regions_7d": regions,
        "daily": list(daily.values()),
        "earthquakes": trimmed,
    }
    write_json("earthquakes.json", output)
    print(f"  ✓ Wrote earthquakes.json ({len(trimmed)} in 30 days, {summary['total']} in 7)")


VOLCANO_INFO = {   # Smithsonian GVP summit coordinates and elevation (m)
    "kilauea":         {"latitude": 19.421, "longitude": -155.287, "elevation_m": 1222},
    "mauna loa":       {"latitude": 19.475, "longitude": -155.608, "elevation_m": 4169},
    "hualalai":        {"latitude": 19.692, "longitude": -155.870, "elevation_m": 2521},
    "mauna kea":       {"latitude": 19.820, "longitude": -155.470, "elevation_m": 4207},
    "haleakala":       {"latitude": 20.708, "longitude": -156.250, "elevation_m": 3055},
    "kamaehuakanaloa": {"latitude": 18.920, "longitude": -155.270, "elevation_m": -975},
}


def _plain(name):
    """'Kīlauea' -> 'kilauea', 'Kamaʻehuakanaloa' -> 'kamaehuakanaloa'."""
    import unicodedata
    n = unicodedata.normalize("NFKD", str(name or ""))
    return "".join(c for c in n if (c.isascii() and c.isalnum()) or c == " ").lower().strip()


def _volcano_info(name):
    p = _plain(name)
    return next((v for k, v in VOLCANO_INFO.items() if k in p), None)


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

    # HANS's monitored list doesn't carry coordinates for these, so fill them
    # from the Smithsonian GVP summit locations (they don't move).
    for hv in hawaii_volcanoes:
        info = _volcano_info(hv["name"])
        if info:
            for k, v in info.items():
                if hv.get(k) is None:
                    hv[k] = v
    # Hawaiian volcanoes above NORMAL (the old count was every elevated
    # volcano in the U.S.).
    elevated_hi = [hv for hv in hawaii_volcanoes
                   if str(hv.get("alert_level", "")).upper() not in ("NORMAL", "UNASSIGNED", "")]

    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "generated_hst": datetime.now(HST).strftime("%Y-%m-%d %H:%M HST"),
        "volcanoes": hawaii_volcanoes,
        "elevated_count": len(elevated_hi),
        "elevated_us_count": len(elevated) if elevated else 0,
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


def _normalize_notice(n, default_title, volcano=None):
    """
    Flatten HANS's shifting schema into one consistent shape.

    HANS returns a wrapper object with noticeSections containing
    per-observatory content. Prefer section-level synopsis (the
    short one-liner) for the message, fall back to summary.
    """
    if not isinstance(n, dict):
        return None

    # Pull the section for this volcano. HVO's monthly updates cover every
    # Hawaiian volcano in one notice; taking the first section filed a
    # Haleakalā paragraph under Mauna Loa.
    sections = n.get("noticeSections") or []
    first_section = sections[0] if sections else {}
    if volcano and sections:
        want = _plain(volcano)
        match = next((sec for sec in sections if want in _plain(sec.get("vName") or sec.get("volcanoName") or "")), None)
        if match is None:
            return None
        first_section = match

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
        "detail": _strip_html(first_section.get("summary") or n.get("summary") or "")[:4000],
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
            norm = _normalize_notice(n, default_title, volcano_name)
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
            norm = _normalize_notice(n, default_title, volcano_name)
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


# ── Eruption episodes ─────────────────────────────────────────────────────────
# USGS keeps a table of every fountaining episode on Kīlauea's eruption page.
# Reading it each run keeps the episode count, log and pause lengths current
# instead of hand-edited. If the page changes shape, the last good copy stays.
EPISODES_URL = "https://www.usgs.gov/volcanoes/kilauea/science/eruption-information"
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul",
                                         "aug", "sep", "oct", "nov", "dec"], 1)}


class _Tables(__import__("html.parser").parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._row, self._cell, self._depth = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([]); self._depth += 1
        elif tag == "tr" and self._depth:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip()); self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row and self.tables:
                self.tables[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _hst_iso(text):
    """'Jan 12, 2026 - 8:22 a.m.' -> '2026-01-12T08:22:00-10:00' (None if unparseable)."""
    m = re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})\D+?(\d{1,2}):(\d{2})\s*([ap])\.?\s*m", text or "", re.I)
    if not m:
        return None
    mon = _MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    h = int(m.group(4)) % 12 + (12 if m.group(6).lower() == "p" else 0)
    try:
        return datetime(int(m.group(3)), mon, int(m.group(2)), h, int(m.group(5)), tzinfo=HST).isoformat()
    except ValueError:
        return None


def _num(text):
    m = re.search(r"-?\d+(?:\.\d+)?", (text or "").replace(",", ""))
    return float(m.group()) if m else None


def fetch_episodes():
    print("\n🔥 Fetching eruption episode table...")
    path = os.path.join(DATA_DIR, "episodes.json")
    req = urllib.request.Request(EPISODES_URL, headers={**HEADERS, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            page = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  ⚠ Could not fetch episode table ({e}) — keeping the existing file")
        return
    parser = _Tables(); parser.feed(page)
    table = next((t for t in parser.tables if t and any("episode" in c.lower() for c in t[0])), None)
    if not table:
        _dump_debug("episodes_page", {"tables": parser.tables[:5]})
        print("  ⚠ No episode table found — keeping the existing file")
        return
    head = [c.lower() for c in table[0]]

    def col(*keys):
        return next((i for i, h in enumerate(head) if all(k in h for k in keys)), None)

    ci = {"episode": col("episode"), "start": col("start"), "end": col("pause", "date"),
          "duration": col("episode", "duration"), "pause_after": col("pause", "duration"),
          "height": col("height"), "volume": col("volume"), "notes": col("note")}
    episodes, events = [], []
    for row in table[1:]:
        get = lambda k: row[ci[k]] if ci[k] is not None and ci[k] < len(row) else ""
        ep_txt = get("episode")
        rec = {
            "episode": int(_num(ep_txt)) if re.fullmatch(r"\s*\d+\s*", ep_txt or "") else None,
            "start": get("start"), "end": get("end"),
            "start_iso": _hst_iso(get("start")), "end_iso": _hst_iso(get("end")),
            "duration": get("duration"), "duration_h": _num(get("duration")),
            "pause_after": get("pause_after"),
            "height_m": _num(get("height")), "volume_mm3": _num(get("volume")),
            "notes": get("notes"),
        }
        (episodes if rec["episode"] is not None else events).append(rec)
    episodes.sort(key=lambda r: r["episode"])
    if len(episodes) < 10:
        print(f"  ⚠ Only {len(episodes)} episodes parsed — keeping the existing file")
        return

    # Pauses: end of one episode to the start of the next, in days
    pauses = []
    for a, b in zip(episodes, episodes[1:]):
        if a["end_iso"] and b["start_iso"]:
            pauses.append(round((datetime.fromisoformat(b["start_iso"]) - datetime.fromisoformat(a["end_iso"])).total_seconds() / 86400, 1))
    recent = sorted(pauses[-10:])
    last = episodes[-1]
    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source": EPISODES_URL,
        "columns": table[0],
        "episodes": episodes,
        "events": events,
        "summary": {
            "count": len(episodes),
            "last_episode": last["episode"],
            "last_start_iso": last["start_iso"],
            "last_end_iso": last["end_iso"],
            "last_height_m": last["height_m"],
            "pauses_days": pauses,
            "median_pause_last10_days": recent[len(recent) // 2] if recent else None,
            "longest_pause_days": max(pauses) if pauses else None,
        },
    }
    write_json("episodes.json", output)
    print(f"  ✓ Wrote episodes.json ({len(episodes)} episodes, {len(events)} other events; last = {last['episode']})")


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
    fetch_episodes()

    print("\n" + "=" * 60)
    print(f"✓ All data written to {DATA_DIR}")
    print(f"  Completed: {datetime.now(HST).strftime('%Y-%m-%d %H:%M:%S HST')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
