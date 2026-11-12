"""
Tasks 1-2 outputs: scenario figures, coverage maps, the channel database table,
and per-UE RAN measurements (RSRP, RSRQ, SINR, CQI) derived from the twin.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from dt.config import load_config, DATA, FIG, TAB
from dt.channel import ChannelSet, uma_pathloss_db
from dt.kpi import db, lin, cqi_from_sinr_db
from dt.plotstyle import plt, save, SITE_COLOR, CAT, SEQ, INK2, GRID

cfg = load_config()
c, r = cfg["carrier"], cfg["ran"]
ch = ChannelSet.load(DATA / "twin_pool.npz")
hot = np.array(ch.meta["is_hotspot"])
cov = np.load(DATA / "coverage.npz")
lo, hi = cfg["scene"]["area_xy"]
p_re = r["tx_power_dbm"] - 10 * np.log10(c["num_prb"] * 12) + r["bf_gain_db"]

# ---------------------------------------------------------------- parameter table (Task 1)
params = [
    ("Scene", f"'{cfg['scene']['name']}': OpenStreetMap building footprints extruded to prisms "
              f"(tools/build_scene.py), ITU-R P.2040 materials"),
    ("Area of interest", f"{hi-lo} m x {hi-lo} m"),
    ("Carrier / band", f"{c['frequency_hz']/1e9:.1f} GHz (n78)"),
    ("Bandwidth / SCS / PRBs", f"{c['bandwidth_hz']/1e6:.0f} MHz / {c['scs_hz']/1e3:.0f} kHz / {c['num_prb']}"),
    ("Slot duration", f"{c['slot_s']*1e3:.1f} ms"),
    ("gNB sites x sectors", f"{len(r['sites'])} sites, {len(ch.ru_names)} RUs"),
    *[(f"Site {s['name']}: position / height / sector azimuths",
       f"({s['xy'][0]:.0f}, {s['xy'][1]:.0f}) m / {s.get('height_m', r['height_m'])} m / "
       + "/".join(f"{a:g}" for a in s.get("sector_azimuths_deg", r["sector_azimuths_deg"])) + " deg")
      for s in r["sites"]],
    ("RU downtilt", f"{r['downtilt_deg']} deg"),
    ("RU Tx power", f"{r['tx_power_dbm']} dBm over 100 MHz ({p_re:.1f} dBm per RE)"),
    ("RU antenna", "3GPP TR 38.901 sector element, 8 dBi, 65 deg HPBW, V-pol"),
    ("UE height / antenna / NF", f"{cfg['ue']['height_m']} m / isotropic / {c['noise_figure_db']} dB"),
    ("Noise per PRB", f"{c['noise_prb_dbm']:.1f} dBm"),
    ("Ray tracer (twin)", "max depth {max_depth}, {samples_per_src:.0e} rays/RU, diffraction={diffraction}, edge={edge_diffraction}".format(**cfg["raytracing"]["twin"])),
    ("Ray tracer (physical)", "max depth {max_depth}, {samples_per_src:.0e} rays/RU, diffraction={diffraction}, diffuse={diffuse_reflection}".format(**cfg["raytracing"]["physical"])),
    ("Link abstraction", "MI-based effective SINR -> CQI (TS 38.214 Table 5.2.2.1-3) -> 10% BLER"),
    ("Traffic", "Full buffer, downlink"),
]
pd.DataFrame(params, columns=["Parameter", "Value"]).to_csv(TAB / "t1_parameters.csv", index=False)

# ---------------------------------------------------------------- helpers
pg = cov["pg"]                                            # [R, ny, nx]
cc = cov["centers"]
ext = [cc[..., 0].min(), cc[..., 0].max(), cc[..., 1].min(), cc[..., 1].max()]
bld = cov["hmap"] > 0.5
hx = cov["hx"]


def buildings(ax, alpha=1.0):
    ax.imshow(np.where(bld, cov["hmap"], np.nan), origin="lower", cmap="Greys", vmin=-20, vmax=60,
              extent=[hx[0], hx[-1], hx[0], hx[-1]], alpha=alpha, zorder=2)


def rus(ax):
    for i, name in enumerate(ch.ru_names):
        x, y = ch.ru_pos[i, :2]
        a = np.deg2rad(ch.ru_az[i])
        col = SITE_COLOR[name[0]]
        ax.annotate("", xy=(x + 45 * np.cos(a), y + 45 * np.sin(a)), xytext=(x, y),
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=2), zorder=5)
    for s in r["sites"]:
        ax.scatter(*s["xy"], s=90, color=SITE_COLOR[s["name"]], edgecolor="white", lw=2, zorder=6)
        ax.annotate(f"Site {s['name']}", s["xy"], xytext=(8, -14), textcoords="offset points",
                    fontsize=9, weight="bold", zorder=7)


def frame(ax, title):
    ax.set_xlim(lo - 30, hi + 30); ax.set_ylim(lo - 30, hi + 30); ax.set_aspect("equal")
    ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]"); ax.set_title(title, loc="left"); ax.grid(False)


# ---------------------------------------------------------------- Fig 1: scenario
fig, ax = plt.subplots(figsize=(7, 7))
buildings(ax)
ax.scatter(*ch.pos[~hot, :2].T, s=5, color=INK2, alpha=0.6, label="UE candidate positions", zorder=3)
ax.scatter(*ch.pos[hot, :2].T, s=5, color=CAT[4], label="Hotspot positions (what-if)", zorder=3)
rus(ax)
ax.legend(loc="upper left", markerscale=3)
frame(ax, f"Digital-twin scenario: {len(r['sites'])} gNB sites, {len(ch.ru_names)} sectors")
save(fig, FIG / "fig01_scenario.png")

# ---------------------------------------------------------------- Fig 2: best-server RSRP and SINR maps
rsrp_map = p_re + db(pg.max(0))
tot = pg.sum(0)
noise_re = lin(c["noise_prb_dbm"]) / 12
sinr_map = db(pg.max(0) * lin(p_re) / ((tot - pg.max(0)) * lin(p_re) + noise_re))
covered = pg.max(0) > 0
fig, axs = plt.subplots(1, 2, figsize=(13, 6))
for ax, m, lab, vr in [(axs[0], rsrp_map, "SS-RSRP [dBm]", (-125, -65)),
                       (axs[1], sinr_map, "Downlink geometry SINR, full load [dB]", (-10, 30))]:
    im = ax.imshow(np.where(covered, m, np.nan), origin="lower", extent=ext, cmap=SEQ,
                   vmin=vr[0], vmax=vr[1], zorder=1)
    buildings(ax); rus(ax)
    frame(ax, lab.split(" [")[0] + " (best server)")
    fig.colorbar(im, ax=ax, shrink=0.75, label=lab)
save(fig, FIG / "fig02_coverage_rsrp_sinr.png")

# best-server site map
best = np.argmax(pg, 0)
site_of = ch.ru_site[best]
fig, ax = plt.subplots(figsize=(7, 7))
cmap = ListedColormap([SITE_COLOR[s["name"]] for s in r["sites"]])
ax.imshow(np.where(covered, site_of, np.nan), origin="lower", extent=ext, cmap=cmap, alpha=0.45,
          vmin=-0.5, vmax=2.5, zorder=1)
buildings(ax); rus(ax)
ax.legend(handles=[Line2D([], [], marker="s", ls="", color=SITE_COLOR[s["name"]], ms=10,
                          label=f"Served by site {s['name']}") for s in r["sites"]], loc="upper left")
frame(ax, "Best-server areas from the twin (shaped by the buildings, not by distance)")
save(fig, FIG / "fig03_best_server.png")

# ---------------------------------------------------------------- channel database (Task 2)
uni = ~hot
table = ch.subset(np.where(uni)[0]).to_table(cfg)
table.to_csv(TAB / "t2_channel_database.csv", index=False)

# ---------------------------------------------------------------- Fig 4: RSRP vs distance
d3 = ch.dist().ravel()
rsrp = (p_re + ch.pg_db).ravel()
los = ch.los.ravel()
found = ch.rt_found.ravel()
fig, ax = plt.subplots(figsize=(8, 5))
ax.scatter(d3[~los & found], rsrp[~los & found], s=6, color=CAT[1], alpha=0.5, label="NLOS (ray-traced)")
ax.scatter(d3[~found], rsrp[~found], s=4, color="#b8b7b0", alpha=0.4, label="NLOS (38.901 fill: no or implausibly weak traced path)")
ax.scatter(d3[los], rsrp[los], s=8, color=CAT[0], alpha=0.8, label="LOS")
dd = np.linspace(20, d3.max(), 200)
for l, ls, lab in [(True, "-", "38.901 UMa LOS"), (False, "--", "38.901 UMa NLOS")]:
    ax.plot(dd, p_re + 8 - uma_pathloss_db(dd, dd, c["frequency_hz"], los=l), ls, color=INK2, lw=1.5, label=lab)
ax.set_xlabel("3D distance RU -> UE [m]"); ax.set_ylabel("SS-RSRP [dBm]")
ax.set_ylim(-170, -50)
ax.set_title("Same distance, very different signal: site-specific propagation", loc="left")
ax.legend(loc="upper right", fontsize=8)
save(fig, FIG / "fig04_rsrp_vs_distance.png")

# ---------------------------------------------------------------- Fig 5: frequency selectivity
ds = ch.delay_spread_ns
best_ru = np.argmax(ch.pg_db, 1)
ds_b = ds[np.arange(ch.U), best_ru]
los_b = ch.los[np.arange(ch.U), best_ru]
i_los = np.where(los_b & ch.rt_found[np.arange(ch.U), best_ru])[0]
i_los = i_los[np.argsort(ds_b[i_los])[len(i_los) // 2]]
i_nl = np.where(~los_b & ch.rt_found[np.arange(ch.U), best_ru])[0]
i_nl = i_nl[np.argsort(ds_b[i_nl])[int(0.9 * len(i_nl))]]
fig, axs = plt.subplots(1, 2, figsize=(13, 4.2))
k = np.arange(c["num_prb"])
for i, lab, col in [(i_nl, "NLOS link", CAT[1]), (i_los, "LOS link", CAT[0])]:
    h = db(ch.H2[i, best_ru[i]])
    axs[0].plot(k, h - h.mean(), color=col,
                label=f"{lab}: UE {i} -> {ch.ru_names[best_ru[i]]}, delay spread {ds_b[i]:.0f} ns")
axs[0].set_xlabel("PRB index"); axs[0].set_ylabel("|H(k)|^2 relative to mean [dB]")
axs[0].set_title("Channel frequency response across the 100 MHz carrier", loc="left")
axs[0].legend(fontsize=8, loc="lower left")
multi = ch.num_paths >= 2
for m, lab, col in [(ch.los & multi, "LOS", CAT[0]), (~ch.los & ch.rt_found & multi, "NLOS", CAT[1])]:
    v = np.sort(ds[m]); axs[1].plot(v, np.linspace(0, 1, len(v)), color=col, label=lab)
axs[1].set_xscale("log"); axs[1].set_xlabel("RMS delay spread [ns]"); axs[1].set_ylabel("CDF")
axs[1].set_title("Delay spread of ray-traced links (>= 2 paths)", loc="left"); axs[1].legend()
save(fig, FIG / "fig05_frequency_selectivity.png")

# ---------------------------------------------------------------- per-UE RAN measurements
P = lin(p_re) * ch.H2.mean(-1)                                  # received power per RE, mW
best = np.argmax(P, 1)
Pb = P[np.arange(ch.U), best]
rssi_rb = 12 * P.sum(1) + lin(c["noise_prb_dbm"])                 # full-load RSSI per RB
sinr = Pb / (P.sum(1) - Pb + noise_re)
meas = pd.DataFrame(dict(
    ue_id=np.arange(ch.U), x=ch.pos[:, 0].round(1), y=ch.pos[:, 1].round(1), hotspot=hot,
    best_ru=np.array(ch.ru_names)[best], los_to_best=ch.los[np.arange(ch.U), best],
    rsrp_dbm=db(Pb).round(1), rsrq_db=db(Pb / rssi_rb).round(1), sinr_db=db(sinr).round(1),
    cqi=cqi_from_sinr_db(db(sinr)),
    second_best_margin_db=np.round(np.sort(ch.pg_db, 1)[:, -1] - np.sort(ch.pg_db, 1)[:, -2], 1),
    nearest_site_is_best=ch.ru_site[best] == np.argmin(
        np.linalg.norm(ch.pos[:, None, :2] - np.array([s["xy"] for s in r["sites"]])[None], axis=-1), 1)))
meas.to_csv(TAB / "t2_ue_measurements.csv", index=False)

summary = dict(
    links=int(ch.U * len(ch.ru_names)), los_fraction=float(ch.los.mean()),
    rt_path_found_fraction=float(ch.rt_found.mean()),
    best_server_los_fraction=float(meas.los_to_best.mean()),
    best_server_not_nearest_site_pct=float(100 * (~meas.nearest_site_is_best).mean()),
    median_rsrp_dbm=float(meas.rsrp_dbm.median()), median_sinr_db=float(meas.sinr_db.median()),
    median_ds_los_ns=float(np.median(ds[ch.los & multi])), median_ds_nlos_ns=float(np.median(ds[~ch.los & ch.rt_found & multi])),
    median_paths_per_link=float(np.median(ch.num_paths[ch.rt_found])),
    rsrp_range_p5_p95_at_150_200m_db=float(np.subtract(*np.percentile(rsrp[(d3 > 150) & (d3 < 200) & found], [95, 5]))),
)
json.dump(summary, open(TAB / "t2_summary.json", "w"), indent=2)
print(json.dumps(summary, indent=2))
