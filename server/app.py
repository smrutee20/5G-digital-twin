"""
The Configure server: a small FastAPI app on localhost around the twin's Sionna RT scene.

  GET  /             the twin page (twin.html, made by python run.py), so the Configure tab can reach this server
  GET  /defaults     the default gNB and UE settings, the 9 sectors, ray counts, grid
  GET  /random_ues   n random outdoor UE positions
  GET  /check_position  is (x, y) inside a building? (moving a gNB)
  POST /simulate     sector settings + UE settings + UE list -> per-UE RSRP from every sector, serving sector, SINR,
                     LOS, and (optionally) the coverage map
  POST /timeline     Mobility tab: a walking route + a handover rule (A3 offset dB, time-to-trigger steps) -> the 5G
                     message timeline (run.py's network simulation on the route's saved, ray-traced RSRP; no tracing)

All Sionna work runs on one worker thread (the scene is reconfigured per request and is not thread-safe).
Start:  .venv/bin/python -m server      (http://127.0.0.1:8765)
"""
import asyncio
import time
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field, field_validator

from server import engine
from server.cache import LRU, MapCache, config_hash

ROOT = engine.ROOT
SECTOR_NAMES = [s["name"] for s in engine.default_sectors()]
RAY_CHOICES = (200_000, 1_000_000, 4_000_000)
DEFAULT_RAYS = 1_000_000                        # the page starts at the study's 1e6; 2e5 stays as a fast option


def _sionna_version():
    from importlib.metadata import version
    return version("sionna-rt")


# ---------------------------------------------------------------------- request shape
class Sector(BaseModel):
    name: str
    azimuth_deg: float = Field(ge=-360, le=360)
    downtilt_deg: float = Field(default=engine.GNB_DEFAULT["downtilt_deg"], ge=-20, le=60)
    height_m: float = Field(default=30.0, ge=2, le=150)
    power_dbm: float = Field(default=engine.GNB_DEFAULT["power_dbm"], ge=0, le=60)
    array: Literal["1x1", "4x4", "8x8", "16x16"] = "1x1"
    pattern: Literal["iso", "dipole", "tr38901"] = "tr38901"
    polarization: Literal["V", "H", "cross"] = "V"
    num_beams: int = Field(default=8, ge=1, le=64)
    # the gNB's position; leave out (None) for config.py's. Set for all 3 sectors of a moved gNB.
    x: float | None = Field(default=None, ge=engine.sc.AREA_X[0], le=engine.sc.AREA_X[1])
    y: float | None = Field(default=None, ge=engine.sc.AREA_Y[0], le=engine.sc.AREA_Y[1])

    @field_validator("name")
    @classmethod
    def known(cls, v):
        if v not in SECTOR_NAMES:
            raise ValueError(f"unknown sector {v}; expected one of {SECTOR_NAMES}")
        return v


class UESettings(BaseModel):
    pattern: Literal["iso", "dipole", "tr38901"] = "iso"
    array: Literal["1x1", "1x2", "2x2", "4x4"] = "1x1"
    polarization: Literal["V", "H", "cross"] = "V"
    height_m: float = Field(default=engine.UE_DEFAULT["height_m"], ge=0.5, le=30)
    noise_figure_db: float = Field(default=engine.UE_DEFAULT["noise_figure_db"], ge=0, le=20)


class UE(BaseModel):
    id: str
    x: float
    y: float


class SimulateRequest(BaseModel):
    sectors: list[Sector]
    ue: UESettings = UESettings()
    ues: list[UE] = Field(default_factory=list, max_length=500)
    coverage: bool = True
    threshold_dbm: float = -110.0
    rays: int = DEFAULT_RAYS
    scene: Literal["v1", "v2"] = "v1"          # v1 = the study's twin; v2 = drawings-corrected buildings + trees

    @field_validator("sectors")
    @classmethod
    def all_nine(cls, v):
        if sorted(s.name for s in v) != sorted(SECTOR_NAMES):
            raise ValueError(f"give every sector exactly once: {SECTOR_NAMES}")
        return sorted(v, key=lambda s: SECTOR_NAMES.index(s.name))

    @field_validator("rays")
    @classmethod
    def ray_choice(cls, v):
        if v not in RAY_CHOICES:
            raise ValueError(f"rays must be one of {RAY_CHOICES}")
        return v


# ---------------------------------------------------------------------- the worker (one thread owns the scene)
_pool = ThreadPoolExecutor(max_workers=1)
_state = {}
_ue_cache = LRU(50_000)
_map_cache = MapCache()


SCENE_LABEL = {"v1": "twin v1 (study, OSM buildings)",
               "v2": "twin v2 (buildings from the IITGN drawings + trees; vegetation loss to be calibrated)"}


def _twin(scene="v1"):
    if scene not in _state.setdefault("twins", {}):
        if not engine.sc.SCENES[scene].exists():
            raise HTTPException(404, f"scene {scene} is not built (run tasks/task9_scene_v2.py)")
        _state["twins"][scene] = engine.Twin(scene)
    _state.setdefault("version", _sionna_version())
    return _state["twins"][scene]


async def _run(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(_pool, fn, *args)


def _ray_note(rays):
    return (f"{rays:.0e} rays per sector".replace("e+0", "e") + f", {engine.sc.MAX_BOUNCES} bounces + diffraction"
            + (" (interactive preview; the study used 1e6)" if rays < 1_000_000 else ""))


def _sector_dict(s):
    """The sector as a dict; x and y only when the gNB was moved, so the default settings (and their cache key)
    stay exactly as before positions were configurable."""
    d = s.model_dump()
    if d["x"] is None or d["y"] is None or np.allclose((d["x"], d["y"]), engine.sector_xy(d["name"]), atol=1e-3):
        d.pop("x"), d.pop("y")
    return d


def _simulate(req: SimulateRequest):
    t0 = time.time()
    tw = _twin(req.scene)
    sectors = [_sector_dict(s) for s in req.sectors]
    ue = req.ue.model_dump()
    common = dict(sectors=sectors, rays=req.rays, seed=engine.sc.SEED, sionna=_state["version"], scene=req.scene)
    ue_key = config_hash(dict(common, ue=ue))

    # ---- per-UE results (only the UEs not already cached are traced)
    xy = np.array([[u.x, u.y] for u in req.ues], float).reshape(-1, 2)
    keys = [config_hash((ue_key, round(u.x, 2), round(u.y, 2))) for u in req.ues]
    todo = [i for i, k in enumerate(keys) if _ue_cache.get(k) is None]
    if todo:
        tr = tw.trace_ues(sectors, ue, xy[todo], rays=req.rays)
        indoor = tw.height_below(xy[todo]) > 0.5
        for j, i in enumerate(todo):
            _ue_cache.put(keys[i], dict(rsrp=tr["rsrp_dbm"][j], avg=tr["avg_beam_dbm"][j], beam=tr["best_beam"][j],
                                        los=tr["los"][j], los_clear=tr["los_clear"][j], indoor=bool(indoor[j])))
    rows = [_ue_cache.get(k) for k in keys]
    ues = []
    if rows:
        rsrp = np.array([r["rsrp"] for r in rows])
        serving, sinr = engine.serving_and_sinr(rsrp, np.array([r["avg"] for r in rows]), ue["noise_figure_db"])
        for u, r, s, q in zip(req.ues, rows, serving, sinr):
            angles = {sec["name"]: engine.beams.beam_angles_deg(sec["num_beams"]) for sec in sectors}
            ues.append(dict(
                id=u.id, x=u.x, y=u.y, indoor=r["indoor"],
                rsrp_dbm={n: round(float(v), 2) for n, v in zip(SECTOR_NAMES, r["rsrp"])},
                los={n: bool(v) for n, v in zip(SECTOR_NAMES, r["los"])},
                los_clear_of_trees={n: bool(v) for n, v in zip(SECTOR_NAMES, r["los_clear"])},
                best_beam={n: int(b) for n, b in zip(SECTOR_NAMES, r["beam"])},
                serving=SECTOR_NAMES[s], sinr_db=round(float(q), 2),
                serving_beam_deg=(None if sectors[s]["array"] == "1x1"
                                  else round(float(angles[SECTOR_NAMES[s]][r["beam"][s]]), 1))))

    # ---- coverage map
    cov, cache_state = None, ("hit" if not todo else "miss") if req.ues else "n/a"
    if req.coverage:
        map_key = config_hash(dict(common, ue_height_m=ue["height_m"], grid=tw.grid))
        hit = _map_cache.get(map_key)
        cache_state = "hit" if hit is not None and cache_state in ("hit", "n/a") else "miss"
        if hit is None:
            hit = tw.coverage(sectors, ue["height_m"], rays=req.rays)
            _map_cache.put(map_key, *hit)
        best, serving = hit
        out = tw.outdoor_cells()
        pct = float(100 * (best[out] > req.threshold_dbm).mean())
        gnb = engine.describe(sectors)
        cov = dict(
            grid=tw.grid, rows="row 0 = southernmost (y ascending); column 0 = westernmost",
            rsrp_dbm=[None if not o else round(float(v), 1) for v, o in zip(best.ravel(), out.ravel())],
            serving=[int(s) if o else -1 for s, o in zip(serving.ravel(), out.ravel())],
            outdoor_cells=int(out.sum()), threshold_dbm=req.threshold_dbm, pct_above_threshold=round(pct, 1),
            gnb_assumptions=gnb,
            ue_assumptions=f"UE {ue['height_m']:g} m, 1x1 iso (Sionna's radio map ignores the UE array)",
            label=(f"Coverage (RSRP > {req.threshold_dbm:g} dBm): {pct:.1f} % of outdoor area with {gnb}; "
                   f"{_ray_note(req.rays)}; {SCENE_LABEL[req.scene]}"),
            scene=req.scene,
            ue_antenna_note=(None if (ue["array"], ue["pattern"]) == ("1x1", "iso") else
                             f"The map assumes a 1x1 iso UE; the per-UE numbers use the chosen "
                             f"{ue['array']} {ue['pattern']} UE."))
    return dict(assumptions=f"{engine.describe(sectors, ue)}; {_ray_note(req.rays)}; {SCENE_LABEL[req.scene]}", scene=req.scene,
                rays=req.rays, ues=ues, coverage=cov, cache=cache_state, elapsed_s=round(time.time() - t0, 2),
                sector_names=SECTOR_NAMES)


# ---------------------------------------------------------------------- the app
@asynccontextmanager
async def _lifespan(app):
    """Load the scene and pre-compute the default coverage map in the background (a cache hit when the tab opens)."""
    req = SimulateRequest(sectors=[Sector(**s) for s in engine.default_sectors()])
    asyncio.get_running_loop().run_in_executor(_pool, _simulate, req)
    yield


app = FastAPI(title="IITGN 5G twin: Configure", lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])  # file:// page


@app.get("/defaults")
async def defaults():
    return dict(gnb=engine.GNB_DEFAULT, ue=engine.UE_DEFAULT, sectors=engine.default_sectors(),
                gnb_xy=engine.site_xy(), rays=DEFAULT_RAYS, ray_choices=list(RAY_CHOICES), study_rays=engine.sc.RAYS_PER_SECTOR,
                grid_m=engine.GRID_M, threshold_dbm=-110.0, frequency_hz=engine.sc.FREQUENCY_HZ,
                bandwidth_hz=engine.sc.BANDWIDTH_HZ, num_prb=engine.sc.NUM_PRB,
                category="A predictive digital twin of the IITGN campus 5G radio network.",
                scenes={k: dict(label=v, available=engine.sc.SCENES[k].exists()) for k, v in SCENE_LABEL.items()})


@app.get("/random_ues")
async def random_ues(n: int = 20, seed: int = 1, scene: Literal["v1", "v2"] = "v1"):
    if not 1 <= n <= 500:
        raise HTTPException(422, "n must be 1..500")
    xy = await _run(lambda: _twin(scene).random_ues(n, seed))
    return dict(ues=[dict(x=round(float(x), 2), y=round(float(y), 2)) for x, y in xy])


@app.get("/check_position")
async def check_position(x: float, y: float, scene: Literal["v1", "v2"] = "v1"):
    """Is (x, y) inside a building? (for moving a gNB in the Configure tab)"""
    inside_area = engine.sc.AREA_X[0] <= x <= engine.sc.AREA_X[1] and engine.sc.AREA_Y[0] <= y <= engine.sc.AREA_Y[1]
    roof = float(await _run(lambda: _twin(scene).height_below(np.array([[x, y]]))[0]))
    return dict(x=x, y=y, inside_building=roof > 0.5, roof_m=round(roof, 1), inside_area=inside_area)


@app.post("/simulate")
async def simulate(req: SimulateRequest):
    return await _run(_simulate, req)


# ---------------------------------------------------------------------- Mobility tab: handover rule -> timeline
class TimelineRequest(BaseModel):
    route: int
    offset_db: float = Field(default=3.0, ge=0, le=20)        # the study: 3 dB
    ttt_steps: int = Field(default=2, ge=1, le=20)            # the study: 2 steps


_timelines = LRU(64)


def _walk_routes():
    """The routes the page walks: task 10's v2 routes if saved (as run.py does), else data/twin.json's."""
    import json
    f = ROOT / "data" / "study_v2" / "walk_routes.json"
    if "walk" not in _state:
        _state["walk"] = json.loads(f.read_text())["routes"] if f.exists() else \
            json.loads((ROOT / "data" / "twin.json").read_text())["routes"]
    return _state["walk"]


def _timeline(req: TimelineRequest):
    import run                                                        # the page's own network simulation
    key = (req.route, round(req.offset_db, 2), req.ttt_steps)
    hit = _timelines.get(key)
    if hit is None:
        route = next((r for r in _walk_routes() if r["id"] == req.route), None)
        if route is None:
            raise HTTPException(404, f"no route {req.route}")
        net, _ = run.simulate(route, SECTOR_NAMES, req.offset_db, req.ttt_steps)
        log = net.log
        ho = [dict(step=e["step"], target=e["fields"]["target_cell"]) for e in log if e.get("message") == "HandoverRequest"]
        hit = dict(route=req.route, offset_db=req.offset_db, ttt_steps=req.ttt_steps, xn_handovers=ho,
                   log=run.page_log(log))
        _timelines.put(key, hit)
    return hit


@app.post("/timeline")
async def timeline(req: TimelineRequest):
    return await asyncio.to_thread(_timeline, req)        # pure Python, not on the Sionna worker thread


@app.get("/")
async def page():
    page = ROOT / "twin.html"
    if page.exists():
        # no-store: run.py rewrites twin.html, and a cached copy would hide the change (old tabs, old buttons)
        return FileResponse(page, headers={"Cache-Control": "no-store"})
    return HTMLResponse("twin.html not found: run <code>.venv/bin/python run.py</code> first, then reload.", 404)

