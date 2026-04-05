# 🌋 PELE — Hawai'i Volcanoes Observatory Dashboard

Live monitoring dashboard for Hawaiian volcanoes, built for a birthday trip to Hawai'i Volcanoes National Park.

**Live site:** [bdgroves.github.io/PELE](https://bdgroves.github.io/PELE)

## Features

- **Overview** — Real-time Kīlauea alert status (WATCH/ORANGE), eruption episode tracking, earthquake summary, embedded USGS YouTube livestream
- **Webcams** — All 9 Kīlauea summit cams + 3 Mauna Loa cams with direct links to USGS live feeds
- **Earthquakes** — 7-day seismicity catalog within 100 km of Kīlauea summit, magnitude color-coding, summary statistics
- **Volcano Profiles** — All 6 HVO-monitored Hawaiian volcanoes: Kīlauea, Mauna Loa, Hualālai, Mauna Kea, Haleakalā, Kama'ehuakanaloa
- **Eruption Log** — Timeline of the episodic fountaining episodes since December 23, 2024
- **Visitor Hazards** — Safety info for park visitors: vog, Pele's hair, tephra fall, volcanic gas, ground cracking

## Architecture

Same pattern as the rest of the collection:

```
fetch.py          → Python 3.12 stdlib, pulls USGS APIs
data/*.json       → Static JSON written by GitHub Actions
index.html        → Plain HTML/CSS/JS, reads data/ with live API fallback
.github/workflows → Cron every 6 hours
```

## Data Sources

| Source | API | What |
|--------|-----|------|
| USGS Earthquake Hazards | `earthquake.usgs.gov/fdsnws/event/1/query` | 7-day seismicity catalog |
| USGS HANS Public API | `volcanoes.usgs.gov/hans-public/api/volcano/` | Volcano alert levels |
| USGS HANS Notices | `volcanoes.usgs.gov/hans-public/api/notice/` | HVO daily updates |
| HVO Webcam Network | `usgs.gov/volcanoes/kilauea/webcams` | Live webcam links |
| USGS YouTube | `youtube.com/@usgs/streams` | Kīlauea summit livestream |

## Named After

**Pele** (Pelehonuamea) — the Hawaiian elemental force of creation that appears as red molten lava. Halema'uma'u crater is her home.

## GitHub Actions

The `fetch.yml` workflow runs every 6 hours to pull fresh data from USGS APIs. The frontend reads from `data/` JSON first, falling back to live client-side API calls if the static data isn't available.

---

*Data: USGS Hawaiian Volcano Observatory · USGS Earthquake Hazards Program · Public Domain*
