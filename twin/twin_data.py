"""
The digital twin's data, in data/twin.json: the 3D campus buildings (OpenStreetMap), the 3 sites and 9 sectors,
the ray-traced RSRP map picture, and the 3 routes with the RSRP of every sector at every step.
All of it comes from the Sionna RT ray tracing of the earlier study; nothing is ray-traced here.
"""
import json
from pathlib import Path

TWIN = Path(__file__).resolve().parents[1] / "data" / "twin.json"


def get_twin():
    return json.loads(TWIN.read_text())
