"""KPI engine: SINR -> effective SINR -> CQI/MCS -> throughput, and summary metrics."""
import numpy as np

# TS 38.214 Table 5.2.2.1-3 (CQI table 2, up to 256QAM): spectral efficiency [bit/RE]
CQI_EFF = np.array([0.1523, 0.3770, 0.8770, 1.4766, 1.9141, 2.4063, 2.7305, 3.3223,
                    3.9023, 4.5234, 5.1152, 5.5547, 6.2266, 6.9141, 7.4063])
IMPL_GAP_DB = 3.0          # distance from Shannon of a practical receiver at 10% BLER
CQI_THR_DB = 10 * np.log10(2 ** CQI_EFF - 1) + IMPL_GAP_DB
MAX_SE = CQI_EFF[-1]


def db(x):
    return 10 * np.log10(np.maximum(x, 1e-30))


def lin(x_db):
    return 10 ** (np.asarray(x_db) / 10)


def effective_sinr(sinr_lin, axis=-1):
    """Mutual-information-style averaging over the PRBs of one transport block."""
    return 2 ** np.mean(np.log2(1 + sinr_lin), axis=axis) - 1


def cqi_from_sinr_db(s_db):
    return np.searchsorted(CQI_THR_DB, s_db, side="right")       # 0 = out of range


def efficiency_from_cqi(cqi):
    return np.where(cqi > 0, CQI_EFF[np.clip(cqi - 1, 0, 14)], 0.0)


def bits_per_prb(eff, cfg):
    c = cfg["carrier"]
    return eff * 12 * 14 * (1 - c["overhead"]) * (1 - c["bler_target"])


def shannon_se(sinr_lin):
    """Fast rate estimate used inside schedulers (capped at 256QAM)."""
    return np.minimum(np.log2(1 + sinr_lin / lin(IMPL_GAP_DB)), MAX_SE)


def jain(x):
    x = np.asarray(x, float)
    return x.sum() ** 2 / (len(x) * (x ** 2).sum() + 1e-12)


def summarize(res):
    """Scalar KPIs for one simulation run (one drop, one strategy)."""
    thr = res["thr_mbps"]
    return dict(
        mean_thr_mbps=thr.mean(), p5_thr_mbps=np.percentile(thr, 5), p50_thr_mbps=np.median(thr),
        sum_thr_mbps=thr.sum(), mean_sinr_db=np.mean(res["sinr_db"]),
        p5_sinr_db=np.percentile(res["sinr_db"], 5), mean_interf_dbm=np.mean(res["interf_dbm"]),
        prb_util_pct=100 * np.mean(res["prb_util"][res["loaded"]]), jain=jain(thr),
        outage_pct=100 * np.mean(thr < 1.0), mean_cqi=np.mean(res["cqi"]),
        cell_se_bps_hz=thr.sum() * 1e6 / res["bw_hz"] / max(res["loaded"].sum(), 1))
