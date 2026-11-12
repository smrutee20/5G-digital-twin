"""
Task 1: the scenario. Load the IITGN campus in Sionna RT with 3 sites x 3 sectors and list every radio and
environment parameter used.        Run:  python tasks/task1_scenario.py   (add --quick for a fast check)
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from twin import scene as sc
from twin.twin_data import save_demo_part


def count_buildings(ply_path):
    """Buildings = groups of triangles that share corners in the building mesh."""
    raw = ply_path.read_bytes()
    header, body = raw.split(b"end_header\n", 1)
    n_points = int(re.search(rb"element vertex (\d+)", header)[1])
    n_faces = int(re.search(rb"element face (\d+)", header)[1])
    faces = np.frombuffer(body[n_points * 12:], dtype=[("n", "u1"), ("i", "<i4", 3)], count=n_faces)["i"]
    group = np.arange(n_points)                       # every corner starts in its own group
    while True:                                       # each triangle pulls its 3 corners into the smallest group
        smallest = group[faces].min(axis=1)
        new = group.copy()
        np.minimum.at(new, faces.ravel(), np.repeat(smallest, 3))
        new = new[new]                                # follow the chain to the group's smallest corner
        if (new == group).all():
            return len(np.unique(group[faces[:, 0]]))
        group = new


# 1. load the campus and put a transmitter on each sector
scene = sc.load()
data, results = sc.folders()

# 2. the environment: materials from the scene file, size of the building mesh, extent of the scene
xml = sc.SCENE_XML.read_text()
materials = re.findall(r'name="type" value="([^"]+)"', xml)                    # building, then ground
ply = (sc.SCENE_XML.parent / "meshes" / "buildings.ply").read_bytes()[:400].decode("latin-1")
triangles = int(re.search(r"element face (\d+)", ply)[1])
buildings = count_buildings(sc.SCENE_XML.parent / "meshes" / "buildings.ply")
box = scene.mi_scene.bbox()
extent = [round(float(box.max[i] - box.min[i])) for i in range(3)]

# 3. everything in one table
params = {
    "scene": "IIT Gandhinagar campus, buildings from OpenStreetMap (centre 23.2107 N, 72.6872 E)",
    "scene size (m, x / y / z)": extent,
    "buildings": buildings,
    "building mesh (triangles)": triangles,
    "building material": materials[0],
    "ground material": materials[1],
    "carrier frequency (GHz)": sc.FREQUENCY_HZ / 1e9,
    "bandwidth (MHz)": sc.BANDWIDTH_HZ / 1e6,
    "subcarrier spacing (kHz)": sc.SCS_HZ / 1e3,
    "PRBs": sc.NUM_PRB,
    "transmit power per sector (dBm)": sc.TX_POWER_DBM,
    "sector antenna": f"{sc.SECTOR_ANTENNA} (3GPP TR 38.901), downtilt {sc.DOWNTILT_DEG} deg",
    "UE antenna, height": f"{sc.UE_ANTENNA}, {sc.UE_HEIGHT_M} m",
    "UE noise figure (dB)": sc.NOISE_FIGURE_DB,
    "ray tracing": f"up to {sc.MAX_BOUNCES} reflections, diffraction {sc.DIFFRACTION}, "
                   f"{sc.RAYS_PER_SECTOR:,} rays per sector",
    "UE area (m)": {"x": sc.AREA_X, "y": sc.AREA_Y},
    "sites": {s: {"x, y (m)": v["xy"], "height (m)": v["height_m"], "sectors point to (deg)": v["sectors_deg"]}
              for s, v in config.SITES.items()},
    "sectors in the scene": list(scene.transmitters),
}

# 4. print it and save it for the report (and, in the full study, for the demo's Scenario box)
for k, v in params.items():
    print(f"{k:34s} {v}")
(results / "task1_parameters.json").write_text(json.dumps(params, indent=2))
if not sc.quick():
    heights = sorted({v["height_m"] for v in config.SITES.values()})
    save_demo_part("scenario", {
        "sites": len(config.SITES), "sectors": len(config.sectors()), "mast height (m)": heights,
        "frequency (GHz)": sc.FREQUENCY_HZ / 1e9, "bandwidth (MHz)": sc.BANDWIDTH_HZ / 1e6, "PRBs": sc.NUM_PRB,
        "power per sector (dBm)": sc.TX_POWER_DBM, "buildings": buildings, "scene (m)": extent[:2]})
print(f"\nsaved {results / 'task1_parameters.json'}")
