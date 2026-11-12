"""
Load the scenario configuration and derive common radio constants.

The config file is config/iitgn.yaml (IIT Gandhinagar campus) unless the DT_CONFIG
environment variable points elsewhere, e.g. DT_CONFIG=config/<name>.yaml. A config with
an `output_tag` writes to data/<tag>/ and results/<tag>/ so scenarios never overwrite
each other.
"""
import os
from pathlib import Path
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(os.environ.get("DT_CONFIG") or ROOT / "config" / "iitgn.yaml")
if not CONFIG_PATH.is_absolute():
    CONFIG_PATH = (Path.cwd() / CONFIG_PATH) if (Path.cwd() / CONFIG_PATH).exists() else ROOT / CONFIG_PATH

with open(CONFIG_PATH) as _f:
    _TAG = (yaml.safe_load(_f) or {}).get("output_tag")
DATA = ROOT / "data" / _TAG if _TAG else ROOT / "data"
RESULTS = ROOT / "results" / _TAG if _TAG else ROOT / "results"
FIG = RESULTS / "figures"
TAB = RESULTS / "tables"
for p in (DATA, FIG, TAB):
    p.mkdir(parents=True, exist_ok=True)


def load_config(path=None):
    with open(path or CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    c = cfg["carrier"]
    for k in ("frequency_hz", "bandwidth_hz", "scs_hz"):
        c[k] = float(c[k])
    c["prb_bw_hz"] = 12 * c["scs_hz"]
    c["slot_s"] = 1e-3 / (c["scs_hz"] / 15e3)
    # thermal noise per PRB at 290 K + receiver noise figure
    c["noise_prb_dbm"] = -174.0 + 10 * np.log10(c["prb_bw_hz"]) + c["noise_figure_db"]
    lo, hi = cfg["scene"]["area_xy"]
    cfg["scene"]["half"] = float(max(abs(lo), abs(hi)))
    xml = cfg["scene"].get("xml")
    if xml and not Path(xml).is_absolute():
        cfg["scene"]["xml"] = str(ROOT / xml)
    return cfg


def prb_offsets_hz(cfg, num_prb=None):
    """Baseband centre frequency of each PRB, relative to the carrier."""
    c = cfg["carrier"]
    k = np.arange(num_prb or c["num_prb"])
    return (k - (c["num_prb"] - 1) / 2) * c["prb_bw_hz"]
