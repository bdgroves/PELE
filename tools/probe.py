"""One-off probe run in Actions (the dev sandbox can't reach USGS).
Finds the live plot images USGS publishes for Kīlauea and checks every webcam URL.
Writes tools/probe_out.json."""
import json, re, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "PELE dashboard probe (github.com/bdgroves/PELE)"}
PAGES = [
    "https://www.usgs.gov/volcanoes/kilauea/science/past-week-monitoring-data-kilauea",
    "https://www.usgs.gov/volcanoes/kilauea/science/past-month-monitoring-data-kilauea",
    "https://www.usgs.gov/volcanoes/kilauea/science/past-year-monitoring-data-kilauea",
    "https://www.usgs.gov/volcanoes/kilauea/science/eruption-information",
    "https://www.usgs.gov/volcanoes/kilauea/summit-webcams",
    "https://www.usgs.gov/volcanoes/mauna-loa/webcams",
    "https://www.usgs.gov/volcanoes/mauna-loa/science/monitoring-data-mauna-loa",
]

def get(url, n=3_000_000):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, dict(r.headers), r.read(n)

def head(url):
    try:
        s, h, b = get(url, 2048)
        return {"url": url, "status": s, "type": h.get("Content-Type"), "len": h.get("Content-Length"),
                "modified": h.get("Last-Modified")}
    except Exception as e:
        return {"url": url, "error": str(e)[:200]}

out = {"pages": {}, "images": []}
found = set()
for p in PAGES:
    try:
        s, h, b = get(p)
        t = b.decode("utf-8", "replace")
        imgs = sorted(set(re.findall(r'https?://volcanoes\.usgs\.gov/[^"\'\s<>)]+\.(?:png|jpg|gif|jpeg)', t)))
        media = sorted(set(re.findall(r'/media/images/[a-z0-9-]+', t)))
        out["pages"][p] = {"status": s, "captures": imgs, "media": media}
        found.update(i.split("?")[0] for i in imgs)
        # follow media pages to their image files
        for m in media[:40]:
            try:
                _, _, mb = get("https://www.usgs.gov" + m)
                mt = mb.decode("utf-8", "replace")
                caps = set(re.findall(r'https?://volcanoes\.usgs\.gov/vsc/captures/[^"\'\s<>)]+', mt))
                title = re.search(r"<title>(.*?)</title>", mt, re.S)
                out["pages"][p].setdefault("media_caps", {})[m] = {"title": title.group(1).strip()[:120] if title else "", "caps": sorted(caps)}
                found.update(c.split("?")[0] for c in caps)
            except Exception as e:
                out["pages"][p].setdefault("media_caps", {})[m] = {"error": str(e)[:100]}
    except Exception as e:
        out["pages"][p] = {"error": str(e)[:200]}

cams = ["V1cam", "V2cam", "V3cam", "KWcam", "F1cam", "B1cam", "K2cam", "S2cam", "KPcam", "MOcam", "MLcam", "MKcam",
        "F2cam", "KOcam", "MUcam", "MTcam", "HMcam", "PEcam", "S1cam", "F3cam", "K3cam", "V4cam"]
for c in cams:
    found.add(f"https://volcanoes.usgs.gov/observatories/hvo/cams/{c}/images/M.jpg")
with ThreadPoolExecutor(8) as ex:
    out["images"] = list(ex.map(head, sorted(found)))
json.dump(out, open("tools/probe_out.json", "w"), indent=1)
print(json.dumps(out["images"], indent=1))
