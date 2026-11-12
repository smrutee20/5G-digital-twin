"""
Build a Sionna RT scene of any real place from OpenStreetMap building footprints.

    footprints (OSM Overpass API, or a GeoJSON exported from overpass-turbo.eu)
      -> local metric coordinates around a chosen centre (east = +x, north = +y)
      -> each building extruded to its height (OSM 'height', else 'building:levels', else a default)
      -> merged triangle meshes (PLY) per ITU material + a ground plane
      -> Mitsuba scene XML that sionna.rt.load_scene() reads
      -> scene_meta.json (origin, extent, buildings, suggested gNB sites)

Simplifications: buildings are prisms (flat roofs); vegetation, terrain and building
interiors are not modelled; inner courtyards of OSM multipolygons are kept.
"""
import os
import json
import math
from pathlib import Path

import numpy as np

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
LEVEL_HEIGHT_M = 3.3


# --------------------------------------------------------------------------- input
def fetch_osm(lat, lon, size_m, timeout=120):
    """Download building footprints in a size_m x size_m box around (lat, lon) as GeoJSON-like features."""
    import requests
    half = size_m / 2
    dlat = half / 111_320.0
    dlon = half / (111_320.0 * math.cos(math.radians(lat)))
    s, w, n, e = lat - dlat, lon - dlon, lat + dlat, lon + dlon
    q = f"""[out:json][timeout:{timeout}];
(way["building"]({s},{w},{n},{e}); relation["building"]["type"="multipolygon"]({s},{w},{n},{e}););
out geom;"""
    last = None
    for url in OVERPASS_URLS:
        try:
            # overpass-api.de answers 406 to requests without an identifying User-Agent
            r = requests.post(url, data={"data": q}, timeout=timeout + 30,
                              headers={"User-Agent": "5g-dt-project/1.0 (course project scene builder)"})
            r.raise_for_status()
            return overpass_to_features(r.json())
        except Exception as exc:            # try the next mirror
            last = exc
    raise RuntimeError(
        f"Could not reach the Overpass API ({last}). If this machine has no internet access, "
        "export the buildings as GeoJSON from https://overpass-turbo.eu on your laptop, copy the "
        "file over and pass it with --geojson.")


def overpass_to_features(js):
    feats = []
    for el in js.get("elements", []):
        tags = el.get("tags", {})
        if el["type"] == "way" and "geometry" in el:
            ring = [(p["lon"], p["lat"]) for p in el["geometry"]]
            feats.append(dict(outer=[ring], inner=[], tags=tags, id=f"w{el['id']}"))
        elif el["type"] == "relation":
            outer = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in el.get("members", [])
                     if m.get("role") == "outer" and "geometry" in m]
            inner = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in el.get("members", [])
                     if m.get("role") == "inner" and "geometry" in m]
            if outer:
                feats.append(dict(outer=outer, inner=inner, tags=tags, id=f"r{el['id']}"))
    return feats


def load_geojson(path):
    """GeoJSON FeatureCollection (e.g. overpass-turbo 'Export -> GeoJSON') with Polygon/MultiPolygon buildings."""
    js = json.loads(Path(path).read_text())
    feats = []
    for f in js["features"]:
        g, tags = f.get("geometry") or {}, f.get("properties", {}) or {}
        tags = tags.get("tags", tags)
        polys = [g["coordinates"]] if g.get("type") == "Polygon" else \
            g["coordinates"] if g.get("type") == "MultiPolygon" else []
        for p in polys:
            feats.append(dict(outer=[[tuple(c[:2]) for c in p[0]]], inner=[[tuple(c[:2]) for c in r] for r in p[1:]],
                              tags=tags, id=str(f.get("id", len(feats)))))
    return feats


# --------------------------------------------------------------------------- geometry
def to_local(lonlat, lat0, lon0):
    a = np.asarray(lonlat, float)
    x = (a[:, 0] - lon0) * 111_320.0 * math.cos(math.radians(lat0))
    y = (a[:, 1] - lat0) * 111_320.0
    return np.c_[x, y]


def building_height(tags, default_h):
    for key in ("height", "building:height"):
        v = tags.get(key)
        if v:
            try:
                return max(3.0, float(str(v).lower().replace("m", "").strip().split()[0]))
            except ValueError:
                pass
    lv = tags.get("building:levels")
    if lv:
        try:
            return max(3.0, float(lv) * LEVEL_HEIGHT_M + 1.0)
        except ValueError:
            pass
    return default_h


def polygons_local(feats, lat0, lon0, half, default_h):
    """Shapely polygons in local metres, clipped to the scene box, with heights."""
    from shapely.geometry import Polygon, box
    from shapely.validation import make_valid
    clip = box(-half, -half, half, half)
    out = []
    for f in feats:
        h = building_height(f["tags"], default_h)
        holes = [to_local(r, lat0, lon0) for r in f["inner"] if len(r) >= 4]
        for ring in f["outer"]:
            if len(ring) < 4:
                continue
            try:
                p = make_valid(Polygon(to_local(ring, lat0, lon0), holes)).intersection(clip)
            except Exception:
                continue
            for g in getattr(p, "geoms", [p]):
                if g.geom_type == "Polygon" and g.area > 8.0:          # drop sheds / slivers < 8 m^2
                    out.append(dict(poly=g.simplify(0.3), h=h, tags=f["tags"], id=f["id"]))
    return out


def extrude(buildings):
    import trimesh
    meshes = []
    for b in buildings:
        try:
            m = trimesh.creation.extrude_polygon(b["poly"], b["h"])
            if len(m.faces):
                meshes.append(m)
        except Exception:
            pass
    return trimesh.util.concatenate(meshes) if meshes else None


def ground_plane(half, margin=60.0):
    import trimesh
    s = half + margin
    v = np.array([[-s, -s, 0], [s, -s, 0], [s, s, 0], [-s, s, 0]], float)
    return trimesh.Trimesh(vertices=v, faces=[[0, 1, 2], [0, 2, 3]], process=False)


# --------------------------------------------------------------------------- site suggestion
def suggest_sites(buildings, n_sites=3, mast_m=4.0, min_h=20.0, seed=0):
    """
    Rooftop sites spread over the campus: k-means on building centroids (weighted by
    footprint area), then the tallest building near each cluster centre hosts a mast.
    """
    c = np.array([[b["poly"].centroid.x, b["poly"].centroid.y] for b in buildings])
    w = np.array([b["poly"].area for b in buildings])
    h = np.array([b["h"] for b in buildings])
    rng = np.random.default_rng(seed)
    cent = c[rng.choice(len(c), n_sites, replace=False, p=w / w.sum())]
    for _ in range(50):
        lab = np.argmin(((c[:, None] - cent[None]) ** 2).sum(-1), 1)
        cent = np.array([np.average(c[lab == k], axis=0, weights=w[lab == k]) if (lab == k).any() else cent[k]
                         for k in range(n_sites)])
    sites = []
    for k in range(n_sites):
        d = np.linalg.norm(c - cent[k], axis=1)
        near = np.where(d < np.percentile(d, 15))[0]
        j = near[np.argmax(h[near])]
        sites.append(dict(name=chr(65 + k), xy=[round(float(c[j, 0]), 1), round(float(c[j, 1]), 1)],
                          height_m=round(float(max(h[j] + mast_m, min_h)), 1),
                          host_building=buildings[j]["tags"].get("name", buildings[j]["id"])))
    return sites


# --------------------------------------------------------------------------- main entry
XML = """<scene version="2.1.0">
    <bsdf type="itu-radio-material" id="mat_building">
        <string name="type" value="{bmat}"/>
        <float name="thickness" value="0.2"/>
    </bsdf>
    <bsdf type="itu-radio-material" id="mat_ground">
        <string name="type" value="{gmat}"/>
        <float name="thickness" value="1.0"/>
    </bsdf>
    <shape type="ply" id="mesh-buildings">
        <string name="filename" value="meshes/buildings.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat_building" name="bsdf"/>
    </shape>
    <shape type="ply" id="mesh-ground">
        <string name="filename" value="meshes/ground.ply"/>
        <boolean name="face_normals" value="true"/>
        <ref id="mat_ground" name="bsdf"/>
    </shape>
</scene>
"""


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_scene(out_dir, lat, lon, size_m, feats, default_h=12.0, n_sites=3,
                building_material="concrete", ground_material="medium_dry_ground", name="scene"):
    out = Path(out_dir)
    (out / "meshes").mkdir(parents=True, exist_ok=True)
    half = size_m / 2
    blds = polygons_local(feats, lat, lon, half, default_h)
    if not blds:
        raise RuntimeError("No buildings found in the requested area.")
    mesh = extrude(blds)
    mesh.export(out / "meshes" / "buildings.ply")
    ground_plane(half).export(out / "meshes" / "ground.ply")
    (out / f"{name}.xml").write_text(XML.format(bmat=building_material, gmat=ground_material))
    sites = suggest_sites(blds, n_sites)
    heights = np.array([b["h"] for b in blds])
    meta = dict(name=name, origin_lat=lat, origin_lon=lon, size_m=size_m, num_buildings=len(blds),
                height_tagged_pct=round(100 * float(np.mean([("height" in b["tags"]) or ("building:levels" in b["tags"])
                                                              for b in blds])), 1),
                median_height_m=float(np.median(heights)), max_height_m=float(heights.max()),
                built_area_pct=round(100 * sum(b["poly"].area for b in blds) / size_m ** 2, 1),
                building_material=building_material, ground_material=ground_material,
                suggested_sites=sites,
                # project-relative, so the metadata stays valid when the project folder moves
                scene_xml=os.path.relpath((out / f"{name}.xml").resolve(), PROJECT_ROOT))
    (out / "scene_meta.json").write_text(json.dumps(meta, indent=2))
    fp = [dict(id=b["id"], h=b["h"], name=b["tags"].get("name", ""),
               xy=np.round(np.asarray(b["poly"].exterior.coords), 1).tolist()) for b in blds]
    (out / "footprints.json").write_text(json.dumps(fp))
    return meta
