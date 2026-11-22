"""
The campus around the radio twin, for the 3D view only (no effect on ray tracing): data/campus_context.json.

  python tools/campus_context.py        (after tasks/task9_scene_v2.py has built data/scene_v2.json)

From OpenStreetMap (data/osm_context.json, data/osm_buildings.json; (c) OpenStreetMap contributors, ODbL):
  roads and paths (ribbons, width by road class), lawns/grass/parks, forest, sports pitches, the running track,
  water and the river, parking; names of the main buildings (labels).
Zone colours: the master plan's legend (Green Campus Development Consortium master plan, p. 80); each building's zone
is assigned from its OSM name and type (rules in zone()); buildings that fit no rule are grey.
Buildings are coloured per vertex for both meshes: v1 (data/twin.json) and v2 (data/scene_v2.json).
Coordinates: twin local metres, x east, y north of 23.2107 N, 72.6872 E, 111 320 m per degree (as the twin's mesh).
"""
import base64
import json
import math
import re
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import Point, Polygon, shape

ROOT = Path(__file__).resolve().parents[1]
LAT0, LON0, M_PER_DEG = 23.2107, 72.6872, 111320.0
ZONES = {                                   # master plan legend colours, sampled from the legend swatches
    "academic": ("Academic", "#ffd29b"),
    "hostels": ("Student hostels", "#ffc33f"),
    "staff": ("Staff housing", "#ffff8d"),
    "common": ("Common facilities", "#ff9f6f"),
    "future": ("Future development", "#e7d3d2"),
    "school": ("School", "#e9e8e4"),
    "research": ("R & D, research, workers' housing", "#d19980"),
    "other": ("Not in the legend / unknown", "#c9c6c0"),
    "lalminar": ("Lal Minar (tower)", "#c4502f"),          # terracotta, not a master-plan zone
}
ROAD_WIDTH = {"tertiary": 9, "tertiary_link": 7, "unclassified": 7, "residential": 6, "service": 5, "track": 3.5,
              "cycleway": 2.5, "footway": 2, "path": 1.5}


def to_local(lat, lon):
    return ((lon - LON0) * M_PER_DEG * math.cos(math.radians(LAT0)), (lat - LAT0) * M_PER_DEG)


def coords(e):
    return [[round(v, 1) for v in to_local(p["lat"], p["lon"])] for p in e.get("geometry", []) if p]


def zone(name, kind, x, y):
    n = name.lower()
    if "lal minar" in n:
        return "lalminar"
    if re.search(r"hostel|mess|student lounge", n):
        return "hostels"
    if "research park" in n:
        return "research"
    if re.search(r"academic|auditorium|learning theatre", n) or (re.match(r"block 0\d$", n) and kind == "university"):
        return "academic"
    if re.match(r"block \d\d$", n) or kind in ("apartments", "house", "residential") or n == "apartments":
        return "staff"
    if re.search(r"sports|guest house|arcade|medical|bank|dispensary|cafe|bakery|teapost|amul|store|mahavir|chill|panchayat|library", n):
        return "common"
    return "other"


def osm_buildings():
    out = []
    for e in json.loads((ROOT / "data" / "osm_buildings.json").read_text())["elements"]:
        if e["type"] == "way" and len(e.get("geometry", [])) >= 4:
            t = e.get("tags", {})
            out.append(dict(poly=Polygon(coords(e)).buffer(0), name=" ".join(t.get("name", "").split()), kind=t.get("building", "")))
    return out


def mesh_colours(points, triangles, footprints):
    """Per-vertex RGB (uint8) of a building mesh: each connected part takes the zone of the footprint it stands in."""
    V = points.reshape(-1, 3); F = triangles.reshape(-1, 3)
    g = coo_matrix((np.ones(F.size), (np.repeat(F[:, 0], 3), F.ravel())), shape=(len(V), len(V)))
    n, lab = connected_components(g + g.T, directed=False)
    rgb = np.zeros((len(V), 3), np.uint8)
    for k in range(n):
        idx = lab == k
        c = Point(V[idx, 0].mean(), V[idx, 1].mean())
        best = min(footprints, key=lambda f: f["poly"].distance(c))
        z = zone(best["name"], best["kind"], c.x, c.y)
        rgb[idx] = [int(ZONES[z][1][i:i + 2], 16) for i in (1, 3, 5)]
    return base64.b64encode(rgb.tobytes()).decode()


def stadium(bounds, lanes):
    """A 400 m-style track ring (straights + semicircular ends) filling the OSM bounds; inner edge = lanes x 1.22 m in.
    Used when OSM returns only the relation's bounds: the shape is an approximation, its size and place are OSM's."""
    x0, y0 = to_local(bounds["minlat"], bounds["minlon"]); x1, y1 = to_local(bounds["maxlat"], bounds["maxlon"])
    cx, cy, w, L = (x0 + x1) / 2, (y0 + y1) / 2, abs(x1 - x0), abs(y1 - y0)

    def ring(r, half):
        pts = []
        for a in np.linspace(0, np.pi, 24):
            pts.append((cx + r * np.cos(a), cy + half + r * np.sin(a)))
        for a in np.linspace(np.pi, 2 * np.pi, 24):
            pts.append((cx + r * np.cos(a), cy - half + r * np.sin(a)))
        return pts + [pts[0]]
    outer, inner = Polygon(ring(w / 2, L / 2 - w / 2)), Polygon(ring(w / 2 - lanes * 1.22, L / 2 - w / 2))
    g = outer.difference(inner)
    r = lambda ring: [[round(x, 1), round(y, 1)] for x, y in ring.coords]
    return (dict(outer=r(g.exterior), holes=[r(h) for h in g.interiors]),     # the running track (oval ring)
            dict(outer=r(inner.exterior), holes=[]))                              # the football ground inside it


def short(name):
    name = re.split(r",| and ", name)[0]
    name = re.sub(r"\(.*?\)|IIT Gandhinagar|IITGN", "", name).strip()
    return name


def main():
    ctx = json.loads((ROOT / "data" / "osm_context.json").read_text())["elements"]
    roads, areas, track, river_lines = [], [], [], []
    for e in ctx:
        t = e.get("tags", {})
        if e["type"] == "way" and "highway" in t:
            w = ROAD_WIDTH.get(t["highway"])
            if w:
                roads.append(dict(w=w, kind="path" if w < 3 else "road", pts=coords(e)))
            continue
        if e["type"] == "relation" and t.get("leisure") == "track":
            for m in e.get("members", []):
                pts = [[round(v, 1) for v in to_local(p["lat"], p["lon"])] for p in m.get("geometry", []) if p]
                if len(pts) > 1:
                    track.append(pts)
            if not e.get("members") and "bounds" in e:          # only the bounds came back: draw a standard track
                ring, infield = stadium(e["bounds"], int(t.get("lanes", 6)))
                areas.append(dict(kind="track", sport="athletics", approx=True, pts=ring))
                areas.append(dict(kind="football", sport="soccer", approx=True, pts=infield))   # the football ground inside
            continue
        if e["type"] != "way":
            continue
        if t.get("waterway") == "river":
            river_lines.append(coords(e)); continue
        kind = ("water" if t.get("natural") == "water" or "water" in t else
                "pitch" if t.get("leisure") in ("pitch", "playground") else
                "lawn" if t.get("landuse") in ("grass", "meadow", "recreation_ground") or t.get("natural") == "grassland"
                or t.get("leisure") == "park" else
                "forest" if t.get("landuse") == "forest" or t.get("natural") in ("wood", "scrub") else
                "parking" if t.get("amenity") == "parking" else None)
        pts = coords(e)
        if kind and len(pts) >= 4 and pts[0] == pts[-1]:
            areas.append(dict(kind=kind, pts=pts, sport=t.get("sport", "")))

    fps = osm_buildings()
    # labels: the buildings of the twin shown on the page (v2: OSM names + Lal Minar), else OSM's
    v2fp = ROOT / "scenes" / "iitgn_v2" / "footprints.geojson"
    named = ([dict(poly=shape(f["geometry"]), name=f["properties"]["name"]) for f in json.loads(v2fp.read_text())["features"]]
             if v2fp.exists() else fps)
    labels, seen = [], set()
    for f in sorted(named, key=lambda f: -f["poly"].area):
        nm = short(f["name"])
        if not nm or nm.lower() in seen or re.match(r"block \d\d$", nm.lower()):
            continue
        if f["poly"].area < 900 and not re.search(r"arcade|medical|lounge|library|lal minar", nm.lower()):
            continue
        seen.add(nm.lower()); c = f["poly"].representative_point()
        labels.append([nm, round(c.x, 1), round(c.y, 1)])
    staff = [f["poly"].centroid for f in fps if re.match(r"block \d\d$", f["name"].lower())]
    if staff:
        labels.append(["Staff housing", round(float(np.mean([p.x for p in staff])), 1), round(float(np.mean([p.y for p in staff])), 1)])

    twin = json.loads((ROOT / "data" / "twin.json").read_text())["buildings"]
    v1_pts = np.frombuffer(base64.b64decode(twin["points"]), np.float32); v1_tri = np.frombuffer(base64.b64decode(twin["triangles"]), np.uint32)
    out = dict(roads=roads, areas=areas, track=track, river_lines=river_lines, labels=labels,
               zones={k: dict(label=v[0], color=v[1]) for k, v in ZONES.items()},
               colors_v1=mesh_colours(v1_pts, v1_tri, fps),
               source="OpenStreetMap contributors (ODbL), fetched 2026-11-22; zone colours: IITGN master plan legend")
    v2 = ROOT / "data" / "scene_v2.json"
    if v2.exists():
        b = json.loads(v2.read_text())["buildings"]
        fp2 = [dict(poly=shape(f["geometry"]), name=f["properties"]["name"], kind="")
               for f in json.loads((ROOT / "scenes" / "iitgn_v2" / "footprints.geojson").read_text())["features"]]
        kinds = {f["name"]: f["kind"] for f in fps}
        for f in fp2:
            f["kind"] = kinds.get(f["name"], "")
        out["colors_v2"] = mesh_colours(np.frombuffer(base64.b64decode(b["points"]), np.float32),
                                        np.frombuffer(base64.b64decode(b["triangles"]), np.uint32), fp2)
    bcsv = ROOT / "scenes" / "iitgn_v2" / "buildings.csv"
    if bcsv.exists():                                        # for the page's Info panel
        import csv
        rows = list(csv.DictReader(open(bcsv)))
        lm = [r for r in rows if r["name"] == "Lal Minar"]
        out["v2_summary"] = dict(buildings=len(rows), from_drawings=sum(r["footprint_source"].startswith("drawing") for r in rows),
                                 g3_m=14, floor_m=3.5, lal_minar_m=float(lm[0]["height_m"]) if lm else None,
                                 lal_minar_source=lm[0]["footprint_source"] if lm else None)
    (ROOT / "data" / "campus_context.json").write_text(json.dumps(out, separators=(",", ":")))
    from collections import Counter
    print(f"roads {len(roads)}, areas {dict(Counter(a['kind'] for a in areas))}, track lines {len(track)}, "
          f"river lines {len(river_lines)}, labels {len(labels)}: {', '.join(l[0] for l in labels)}")
    zc = Counter(zone(f["name"], f["kind"], 0, 0) for f in fps); print("zones (OSM buildings):", dict(zc))


if __name__ == "__main__":
    main()
