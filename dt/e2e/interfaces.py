"""
Named interfaces of the end-to-end model and which element types each one may connect.
A message on any other pair of element types is rejected (catches wiring mistakes).
"""

SBI_NFS = {"AMF", "SMF", "AUSF", "UDM", "NRF", "PCF"}

INTERFACES = {
    "Uu":        {"UE", "RU"},          # air interface (RACH, RRC with NAS inside, PDSCH/PUSCH)
    "fronthaul": {"RU", "DU"},          # O-RAN 7.2x eCPRI C/U-plane
    "F1-C":      {"DU", "CU-CP"},       # F1AP (TS 38.473)
    "F1-U":      {"DU", "CU-UP"},       # GTP-U / NR-U (TS 38.425)
    "E1":        {"CU-CP", "CU-UP"},    # E1AP (TS 38.463)
    "Xn-C":      {"CU-CP"},             # XnAP between two gNBs (TS 38.423): handover preparation, release
    "Xn-U":      {"CU-UP"},             # GTP-U data forwarding between two gNBs during handover
    "N2":        {"CU-CP", "AMF"},      # NGAP (TS 38.413), carries NAS (N1)
    "N3":        {"CU-UP", "UPF"},      # GTP-U
    "N4":        {"SMF", "UPF"},        # PFCP (TS 29.244)
    "N6":        {"UPF", "DN"},         # IP to the data network
    "SBI":       SBI_NFS,               # HTTP/2 service-based interface between core NFs
}

DESCRIPTION = {
    "Uu": "UE <-> RU, air interface", "fronthaul": "RU <-> DU, O-RAN 7.2x eCPRI",
    "F1-C": "DU <-> CU-CP, F1AP", "F1-U": "DU <-> CU-UP, GTP-U/NR-U", "E1": "CU-CP <-> CU-UP, E1AP",
    "Xn-C": "gNB CU-CP <-> gNB CU-CP, XnAP", "Xn-U": "gNB CU-UP <-> gNB CU-UP, GTP-U data forwarding",
    "N2": "CU-CP <-> AMF, NGAP", "N3": "CU-UP <-> UPF, GTP-U", "N4": "SMF <-> UPF, PFCP",
    "N6": "UPF <-> data network, IP", "SBI": "core NF <-> core NF, HTTP/2 (Nnrf, Nausf, Nudm, Npcf, Nsmf, Namf)",
}

# 3GPP reference points realised over the SBI (TS 23.501 §4.2.7)
_REF = {frozenset({"AMF", "SMF"}): "N11", frozenset({"AMF", "AUSF"}): "N12", frozenset({"AUSF", "UDM"}): "N13",
        frozenset({"AMF", "UDM"}): "N8", frozenset({"SMF", "UDM"}): "N10", frozenset({"SMF", "PCF"}): "N7",
        frozenset({"AMF", "PCF"}): "N15"}


def check_link(interface, kind_a, kind_b):
    allowed = INTERFACES.get(interface)
    if allowed is None:
        raise ValueError(f"unknown interface {interface}")
    if interface == "SBI":
        ok = kind_a in allowed and kind_b in allowed and kind_a != kind_b
    elif len(allowed) == 1:                     # Xn: two elements of the same type (two gNBs)
        ok = kind_a == kind_b and kind_a in allowed
    else:
        ok = {kind_a, kind_b} == allowed
    if not ok:
        raise ValueError(f"{kind_a} -> {kind_b} is not a legal {interface} link")


def latency_key(interface):
    return "F1" if interface.startswith("F1") else "Xn" if interface.startswith("Xn") else interface


def ref_point(interface, kind_a, kind_b):
    if interface != "SBI":
        return None
    if "NRF" in (kind_a, kind_b):
        return "Nnrf"
    return _REF.get(frozenset({kind_a, kind_b}))
