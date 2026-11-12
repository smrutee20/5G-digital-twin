"""
The radio formulas: received power, noise, SINR, the CQI table, throughput, and the KPIs used by tasks 2-7.
Every link UE <-> sector has one ray-traced path gain (averaged over the 100 MHz), so its power is the same on
every PRB; what changes from PRB to PRB is which other sectors transmit there (the interference).
"""
import numpy as np

from twin.scene import TX_POWER_DBM, NUM_PRB, SCS_HZ, NOISE_FIGURE_DB

PRB_HZ = 12 * SCS_HZ                            # one PRB = 12 subcarriers = 360 kHz
SLOT_S = 0.5e-3                                 # one slot at 30 kHz = 0.5 ms, 14 symbols
OVERHEAD = 0.14                                 # share of resource elements used by control and reference signals
BLER = 0.10                                     # link adaptation aims at 10 % block errors

# CQI table (TS 38.214 Table 5.2.2.1-3, up to 256QAM): bits per resource element for CQI 1..15
CQI_EFFICIENCY = np.array([0.1523, 0.3770, 0.8770, 1.4766, 1.9141, 2.4063, 2.7305, 3.3223,
                           3.9023, 4.5234, 5.1152, 5.5547, 6.2266, 6.9141, 7.4063])
GAP_DB = 3.0                                    # a real receiver needs about 3 dB more SINR than Shannon
CQI_MIN_SINR_DB = 10 * np.log10(2 ** CQI_EFFICIENCY - 1) + GAP_DB      # SINR needed for each CQI


def to_mw(dbm):
    return 10 ** (np.asarray(dbm) / 10)


def to_db(mw):
    return 10 * np.log10(np.maximum(mw, 1e-30))


def rsrp_dbm(path_gain_db):
    """RSRP = power of one resource element: 46 dBm shared by 273 x 12 subcarriers, plus the path gain."""
    return TX_POWER_DBM - 10 * np.log10(NUM_PRB * 12) + path_gain_db


def prb_power_mw(path_gain_db):
    """Power a UE receives on one PRB from each sector (46 dBm shared by 273 PRBs), in mW."""
    return to_mw(TX_POWER_DBM - 10 * np.log10(NUM_PRB) + path_gain_db)


def noise_mw():
    """Noise in one PRB: thermal noise (-174 dBm/Hz) over 360 kHz, plus the phone's noise figure."""
    return to_mw(-174 + 10 * np.log10(PRB_HZ) + NOISE_FIGURE_DB)


def sinr_all_on_db(rx_mw, serving, active):
    """SINR of each UE if every active sector transmits on every PRB (the worst case, full load)."""
    u = np.arange(len(serving))
    signal = rx_mw[u, serving]
    interference = (rx_mw * active).sum(1) - signal
    return to_db(signal / (interference + noise_mw()))


def bits_per_prb(sinr_db):
    """Bits one PRB carries in one slot: SINR -> CQI -> bits per resource element -> x 12 x 14, less overhead."""
    cqi = np.searchsorted(CQI_MIN_SINR_DB, sinr_db, side="right")          # 0 = too weak for any CQI
    efficiency = np.where(cqi > 0, CQI_EFFICIENCY[np.clip(cqi - 1, 0, 14)], 0.0)
    return efficiency * 12 * 14 * (1 - OVERHEAD) * (1 - BLER)


def kpis(result):
    """The numbers compared in tasks 3, 4, 6 and 7."""
    thr = result["throughput_mbps"]
    return {
        # a UE below -20 dB gets nothing either way; counting it as -20 dB stops one dead link (e.g. -180 dB,
        # no ray path at all) from swamping the mean
        "mean SINR (dB)": float(np.nanmean(np.maximum(result["sinr_db"], -20))),
        "mean throughput (Mbps)": float(thr.mean()),
        "5th-percentile throughput (Mbps)": float(np.percentile(thr, 5)),
        # averaged as power (mW), then shown in dBm: a UE with no interference at all adds 0 mW, not -300 dBm
        "mean interference (dBm per PRB)": float(to_db(np.nanmean(to_mw(result["interference_dbm"])))),
        "PRB utilisation (%)": float(100 * result["prb_utilisation"]),
    }
