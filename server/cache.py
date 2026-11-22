"""
Result caches, keyed by a hash of the configuration (so a repeated configuration returns at once).

  coverage maps  key = sector settings + UE height + rays (+ grid, seed, Sionna version); in memory and on disk
                 (server/cache/*.npz), because a map with 8 beams takes seconds
  per-UE results key = sector settings + UE settings + rays + the UE's position; in memory only. Moving one UE
                 re-traces only that UE.
"""
import hashlib
import json
from collections import OrderedDict
from pathlib import Path

import numpy as np

CACHE_DIR = Path(__file__).resolve().parent / "cache"


def config_hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:32]


class LRU:
    def __init__(self, size):
        self.size, self.data = size, OrderedDict()

    def get(self, key):
        if key in self.data:
            self.data.move_to_end(key)
            return self.data[key]
        return None

    def put(self, key, value):
        self.data[key] = value
        self.data.move_to_end(key)
        while len(self.data) > self.size:
            self.data.popitem(last=False)


class MapCache:
    """Coverage maps: memory first, then disk."""

    def __init__(self, size=32, directory=CACHE_DIR):
        self.mem, self.dir = LRU(size), Path(directory)

    def get(self, key):
        hit = self.mem.get(key)
        if hit is None and (self.dir / f"{key}.npz").exists():
            with np.load(self.dir / f"{key}.npz") as f:
                hit = (f["rsrp"], f["serving"])
            self.mem.put(key, hit)
        return hit

    def put(self, key, rsrp, serving):
        self.mem.put(key, (rsrp, serving))
        self.dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.dir / f"{key}.npz", rsrp=rsrp.astype(np.float32), serving=serving.astype(np.int8))
