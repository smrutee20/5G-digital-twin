"""
The demo's data, in data/twin.json: the 3D campus buildings (OpenStreetMap), the 3 sites and 9 sectors, the RSRP
map picture on the ground, and the 3 routes with the RSRP and line of sight of every sector at every step.
The routes are written by task 5 (tasks/task5_mobility.py), with the current ray-tracing code, so the demo and
task 5 use the same route data. The buildings and the RSRP map picture come from the earlier study.
"""
import json
from pathlib import Path

TWIN = Path(__file__).resolve().parents[1] / "data" / "twin.json"


def get_twin():
    return json.loads(TWIN.read_text())


def save_routes(rsrp_dbm, los):
    """Replace the routes' signal data with task 5's: rsrp_dbm and los are [route, step, sector]."""
    twin = get_twin()
    for r, route in enumerate(twin["routes"]):
        route["rsrp"] = [[float(v) for v in step] for step in rsrp_dbm[r]]   # exact, so the demo's A3 decisions match
        route["los"] = [[bool(v) for v in step] for step in los[r]]
        route["traced"] = [[True] * len(step) for step in rsrp_dbm[r]]    # every value is ray-traced now
    TWIN.write_text(json.dumps(twin, separators=(",", ":")))


DEMO_TASKS = TWIN.parent / "demo_tasks.json"


def save_demo_part(name, part):
    """Tasks 1, 6 and 7 (full study) save what the demo's Scenario box and tabs show into data/demo_tasks.json."""
    saved = json.loads(DEMO_TASKS.read_text()) if DEMO_TASKS.exists() else {}
    saved[name] = part
    DEMO_TASKS.write_text(json.dumps(saved, separators=(",", ":")))
