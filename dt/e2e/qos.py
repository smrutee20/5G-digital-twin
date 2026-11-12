"""
QoS model: standardized 5QI characteristics (TS 23.501 Table 5.7.4-1, excerpt) and the default
QoS flow of a PDU session as it appears at each element:
  * QoS rule      -> UE          (N1, PDU Session Establishment Accept)
  * QoS profile   -> NG-RAN      (N2 PDU Session Resource Setup Request Transfer, E1, F1)
  * QER           -> UPF         (N4 PFCP)
"""

FIVE_QI = {
    1: dict(resource_type="GBR", priority_level=20, pdb_ms=100, per=1e-2, example="Conversational voice"),
    5: dict(resource_type="Non-GBR", priority_level=10, pdb_ms=100, per=1e-6, example="IMS signalling"),
    8: dict(resource_type="Non-GBR", priority_level=80, pdb_ms=300, per=1e-6, example="Video (buffered streaming), TCP-based"),
    9: dict(resource_type="Non-GBR", priority_level=90, pdb_ms=300, per=1e-6, example="Video (buffered streaming), TCP-based"),
}


def default_flow(q):
    """The session's default QoS flow from the e2e.default_qos config block."""
    five_qi = int(q["five_qi"])
    return dict(qfi=1, five_qi=five_qi, **FIVE_QI[five_qi],
                arp=dict(priority_level=int(q["arp_priority"]), pre_emption_capability="NOT_PREEMPT",
                         pre_emption_vulnerability="PREEMPTABLE"))


def session_ambr(q):
    return dict(downlink=f"{q['session_ambr_dl_mbps']} Mbps", uplink=f"{q['session_ambr_ul_mbps']} Mbps")


def qos_rule(flow):
    """Default QoS rule sent to the UE (TS 24.501 §9.11.4.13): match-all filter -> QFI."""
    return dict(qri=1, default_rule=True, precedence=255, packet_filters="match-all", qfi=flow["qfi"])


def qos_profile(flow):
    """QoS Flow Level QoS Parameters sent to NG-RAN (TS 38.413 §9.3.1.12)."""
    return dict(qfi=flow["qfi"], five_qi=flow["five_qi"], arp=flow["arp"])
