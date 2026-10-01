# 🌋 PELE

### Hawai'i Volcanoes Observatory Dashboard

**Live site:** [bdgroves.github.io/PELE](https://bdgroves.github.io/PELE)

---

> *"The coffee tastes like something crawled in the pot and died."*
>
> Harry Dalton never trusted a quiet volcano. The hot springs were too hot. The lake was too acidic. The trees were dying in patterns that crept downslope like the mountain was breathing wrong. He'd been to Colombia. He'd been to the Philippines. He knew what the prelude looked like — not the explosion itself, but the weeks before, when the data says *something is coming* and the town council says *you're going to hurt the economy.*
>
> In Dante's Peak, the USGS guy was right about everything and nobody listened until the church steeple was on fire. In the real world, it's more complicated. The USGS Hawaiian Volcano Observatory has been monitoring Kīlauea for over a century — longer than any other volcano observatory on Earth — and when they give a forecast window, they mean it — and when the pattern breaks and they say they can no longer model one, they mean that too. They've watched 54 episodes of this eruption cycle unfold since December 2024. They've calibrated their tiltmeters. They've mapped the inflate-deflate rhythm of a magma chamber that breathes like a sleeping giant. They know exactly how much microradian tilt means *tomorrow* versus *next week*.
>
> This is what real volcano monitoring looks like. Not Pierce Brosnan outrunning pyroclastic flows in a pickup truck. Real data. Real APIs. Real science. Served every hour by a GitHub Actions cron job.

---

## The Dashboard

PELE is a live monitoring dashboard for the six volcanoes of Hawai'i, built for a birthday trip to Hawai'i Volcanoes National Park in May 2026. It pulls real-time data from USGS APIs, embeds live HVO webcam feeds, and tracks the ongoing episodic lava fountaining eruption at Kīlauea — an eruption style not seen at the summit since the 1980s.

The trip came and went; the volcano didn't stop. As of October 2026, Episode 54 (August 25) is the most recent fountaining episode, and the pause since then is the longest of the whole eruption — more than twice the recent median. In mid-September six new vents opened on the crater's northwest wall and poured lava onto the floor without fountaining, and on October 1 HVO reported a shallow intrusion of magma under the summit, with a swarm of more than 30 summit earthquakes in a day. Nobody knows yet whether that ends with Episode 55 or with something new. The dashboard now tracks the pause itself, so you can watch the wait.

### Six Tabs, All the Bells and Whistles

| Tab | What It Does |
|-----|-------------|
| **Overview** | Alert status, next-episode tracker (pause length against the recent median and the record), 7-day and 24-hour earthquake counts with the summit share, YouTube V1cam livestream, latest HVO notice with the full update, live status of the other Hawaiian volcanoes |
| **Webcams** | Three YouTube livestream embeds (V1/V2/V3) auto-discovered via YouTube Data API, plus 9 Kīlauea and 3 Mauna Loa static webcam snapshots refreshed every few minutes from USGS servers |
| **Earthquakes** | Map of quakes within 100 km of Kīlauea (sized by magnitude, coloured by depth, with volcanoes coloured by alert level; dark, satellite and topo basemaps), a 30-day daily chart splitting summit quakes from everything else, region filters (summit, rift zones, deep Pāhala swarm, Mauna Loa, elsewhere) and a 24 h / 7 day / 30 day window. Stats, map and catalog follow the filter |
| **Volcano Profiles** | All 6 HVO-monitored Hawaiian volcanoes: Kīlauea, Mauna Loa, Hualālai, Mauna Kea, Haleakalā, and Kama'ehuakanaloa (the submarine seamount that will someday become Hawai'i's next island) |
| **Eruption Log** | Every episode from the USGS eruption table: fountain height and pause length charted episode by episode, totals (tallest fountain, lava volume), and a newest-first timeline that includes non-fountaining vent activity. Hand-written notes for Episodes 39–44 (Episode 43's 1,770-ft record fountain and others) sit under the USGS rows |
| **Visitor Hazards** | Vog, Pele's hair, tephra fall, volcanic gas, ground cracking — everything you need to know before walking up to an active volcano on your birthday |

---

## The Storm Chasers and the Volcano Watchers

> *"You've never seen it miss this house, and miss that house, and come after you."*

Jo Harding said that about tornadoes. Bill Paxton's face when he saw the F5 bearing down on them — that's the face of someone who has spent their whole career studying something from a safe distance and is now standing in the middle of it.

Twister understood something fundamental about field science: you can have all the instruments in the world, but at some point someone has to drive into the storm and put DOROTHY in the path of the funnel. The HVO scientists do the same thing. They hike across fresh tephra fields. They service webcams on the rim of a crater that has buried cameras under 30 feet of volcanic glass. When the V3cam got destroyed by Episode 38's lava fountain on December 6, 2025, they had a new one deployed in a safer spot within two weeks. A broad arcing fountain had extended over 600 meters and buried the camera. They went back.

The sequel understood it too. In Twisters, Tyler Owens wasn't just chasing storms for content — he was trying to prove you could weaken a tornado by seeding it at the right moment. The science was speculative, but the instinct was right: *get close enough to understand it, and maybe you can change the outcome*. That's what HVO's episodic forecasting model does. Forty-three episodes of observation have taught them the inflate-pause-overflow-fountain rhythm well enough to predict the next episode within a week-long window. They've earned that precision the hard way — by watching, measuring, and occasionally running.

> *"If you feel it, it's already too late."*

That's not from a movie. That's basic volcanology. By the time you feel the earthquake swarm, the magma is already moving. The dashboard exists so you can watch the tiltmeters and the tremor signals *before* you feel anything. So you can see the precursory overflows from the south vent on the V1cam livestream and know that the next fountaining episode is days away, not weeks.

---

## Architecture

Same pattern as the rest of the collection — [Sierra Streamflow](https://bdgroves.github.io/sierra-streamflow), [EDGAR](https://bdgroves.github.io/EDGAR), [brooksgroves.com](https://brooksgroves.com):

```
PELE/
├── .github/workflows/fetch.yml   ← Cron hourly at :15
├── data/
│   ├── earthquakes.json          ← 30-day USGS catalog, regions, daily counts
│   ├── episodes.json             ← USGS eruption-episode table, parsed
│   ├── volcanoes.json            ← HANS API alert levels
│   └── notices.json              ← HVO daily updates
├── fetch.py                      ← Python 3.12 stdlib only
├── index.html                    ← Plain HTML/CSS/JS, no frameworks
└── README.md
```

**The pattern:** `fetch.py` runs in GitHub Actions, pulls from USGS APIs, writes static JSON to `data/`. The frontend reads `data/` first, falls back to live client-side API calls if the cached data isn't available. Everything is plain HTML/CSS/JS. No build step. No npm. No React. Just files.

**Fallback:** If the Actions-generated earthquake JSON isn't available, the page queries the USGS FDSN API directly and sorts quakes into the same regions in the browser.

**No endtime:** The catalog query sets a start time and no end time. An earlier version passed today's *date* as the end time, which the API reads as midnight UTC, so the most recent hours of quakes never showed up. Fixed October 2026, the day a summit swarm was in exactly those hours.

**YouTube livestream auto-discovery:** On page load, JS hits the YouTube Data API to search for currently-live streams on the USGS channel, matches them to V1/V2/V3 by title, and embeds them as iframes. If the API call fails, clickable thumbnails with the latest webcam snapshots serve as fallback.

## Data Sources

| Source | Endpoint | Refresh |
|--------|----------|---------|
| **USGS Earthquake Hazards** | `earthquake.usgs.gov/fdsnws/event/1/query` | Hourly (Actions), live client-side fallback |
| **USGS HANS Public API** | `volcanoes.usgs.gov/hans-public/api/volcano/` | Hourly |
| **USGS HANS Notices** | `volcanoes.usgs.gov/hans-public/api/notice/` | Hourly |
| **USGS Kīlauea eruption table** | `usgs.gov/volcanoes/kilauea/science/eruption-information` | Hourly (HTML table parsed with the standard library) |
| **HVO Webcam Images** | `volcanoes.usgs.gov/observatories/hvo/cams/{ID}/images/M.jpg` | Every page load (updated every few minutes by USGS) |
| **YouTube Data API** | `googleapis.com/youtube/v3/search` | Every page load (discovers current livestream IDs) |
| **USGS YouTube Livestreams** | `youtube.com/@usgs/streams` | 24/7 live video from V1cam, V2cam, V3cam |

---

## The Eruption

Kīlauea began its current eruption on December 23, 2024 — Christmas Eve eve — from two vents in the southwest part of Halema'uma'u crater. It immediately established a pattern nobody had seen at the summit since Pu'u 'Ō'ō in the 1980s: episodic lava fountaining. Short bursts of spectacular fountains, generally lasting less than 12 hours, separated by inflationary pauses that stretch from days to weeks.

By late August 2026 the volcano had produced 54 episodes. Pauses stretched as it went: about 5 days apart in the first twenty episodes, about 13 by the summer of 2026. The tallest fountain, 540 m (1,770 ft) from the south vent, came in Episode 43 on March 10, 2026. The north vent fountain during Episode 42 reached approximately 300 meters — about 1,000 feet — visible from restaurants in Hilo. The V3cam on the south rim was destroyed by Episode 38 when a broad arcing fountain extended over 600 meters and buried it under 10 meters of tephra. HVO deployed a replacement within two weeks.

The eruption is within a closed area of the park. You can't walk up to it. But you can see the glow at night from the public viewing areas on Crater Rim Drive, and during a fountaining episode, the plume is visible from across the island. If you're in the park when the next episode kicks off, you'll know. Everyone on the island will know.

> *"What's the update on the mountain?"*
> *"She's just clearing her throat."*

---

## Named After

**Pele** (Pelehonuamea — "Pele of the red earth") is the Hawaiian elemental force of creation that manifests as molten lava. Halema'uma'u crater, within the summit caldera of Kīlauea, is her home. The episodic fountaining eruption happening right now is, in the Hawaiian understanding, Pele reshaping the land. The tephra that falls on Volcano Village — the glassy strands called Pele's hair, the tear-shaped droplets called Pele's tears — carry her name because they are, in every sense, pieces of her.

The USGS measures the eruption in microradians and tonnes of SO₂. The Hawaiian tradition measures it in stories that stretch back centuries. Both traditions agree on one thing: this mountain is alive, and it will do what it wants.

---

## The Collection

PELE joins a growing set of automated, data-driven dashboards:

| Project | What | Data |
|---------|------|------|
| **[PELE](https://bdgroves.github.io/PELE)** | Hawai'i Volcanoes Observatory Dashboard | USGS/HVO, earthquakes, webcams, alerts |
| **[EDGAR](https://bdgroves.github.io/EDGAR)** | Mariners & Rainiers Analytics Dashboard | pybaseball, mlb-statsapi, Statcast |
| **[Sierra Streamflow](https://bdgroves.github.io/sierra-streamflow)** | USGS Streamflow Monitor — 8 Sierra gages | USGS NWIS, 20-year historical |
| **[brooksgroves.com](https://brooksgroves.com)** | Personal web portal | GitHub Actions, Goodreads, Untappd, weather |

All share the same DNA: GitHub Actions writing static JSON, plain HTML/CSS/JS frontend, no frameworks, no build steps, hosted on GitHub Pages. Data pipelines that run while you sleep.

---

## Run Locally

```bash
# Fetch fresh data (Python 3.12, stdlib only)
python fetch.py

# Serve locally
python -m http.server 8000
# Open http://localhost:8000
```

---

*Data: USGS Hawaiian Volcano Observatory · USGS Earthquake Hazards Program · YouTube Data API · Public Domain*

*Built for a birthday trip to Hawai'i Volcanoes National Park · 2026*

*"The mountain is ready. The question is whether we are."*
