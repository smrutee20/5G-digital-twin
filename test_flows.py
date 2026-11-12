"""
Small test: on every route, every flow taught in class appears with its messages in the right order, and the
handovers happen where the twin's A3 rule says (route 2: the study's 4 handovers at 12, 40, 56 and 92 m).
Run:  python test_flows.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from twin.twin_data import get_twin
from run import simulate

# The messages of each flow, in the order taught (other messages may come in between).
TAUGHT = {
    1: ["SSB", "MIB", "SIB1", "RandomAccessPreamble", "RandomAccessResponse", "RRCSetupRequest", "RRCSetup"],
    2: ["RRCSetupComplete[RegistrationRequest]", "InitialUEMessage[RegistrationRequest]",
        "Nausf_UEAuthentication_Authenticate", "Nudm_UEAuthentication_Get", "DeconcealSUCI", "DeconcealSUCI_Response",
        "DLInformationTransfer[AuthenticationRequest]", "ULInformationTransfer[AuthenticationResponse]",
        "DLInformationTransfer[SecurityModeCommand]", "ULInformationTransfer[SecurityModeComplete]",
        "Nnssf_NSSelection_Get", "DLInformationTransfer[RegistrationAccept]",
        "ULInformationTransfer[RegistrationComplete]"],
    3: ["ULInformationTransfer[PDUSessionEstablishmentRequest]", "Nsmf_PDUSession_CreateSMContext",
        "PFCPSessionEstablishmentRequest", "PFCPSessionEstablishmentResponse", "Namf_Communication_N1N2MessageTransfer",
        "PDUSessionResourceSetupRequest[PDUSessionEstablishmentAccept]",
        "RRCReconfiguration[PDUSessionEstablishmentAccept]", "PDUSessionResourceSetupResponse",
        "Nsmf_PDUSession_UpdateSMContext", "PFCPSessionModificationRequest"],
    4: ["PUSCH", "GTP_U", "IPPacket", "IPPacket", "GTP_U", "PDSCH"],
    5: ["MeasurementReport", "HandoverRequest", "HandoverRequestAcknowledge", "RRCReconfiguration",
        "RandomAccessPreamble", "RRCReconfigurationComplete", "PathSwitchRequest", "Nsmf_PDUSession_UpdateSMContext",
        "PFCPSessionModificationRequest", "EndMarker", "PathSwitchRequestAcknowledge", "UEContextRelease"],
    6: ["UEContextReleaseRequest", "RRCRelease", "IPPacket", "PFCPSessionReportRequest",
        "Namf_Communication_N1N2MessageTransfer", "Paging", "Paging", "RandomAccessPreamble",
        "RRCSetupComplete[ServiceRequest]", "InitialUEMessage[ServiceRequest]",
        "InitialContextSetupRequest[ServiceAccept]", "PFCPSessionModificationRequest", "GTP_U", "PDSCH"],
}
STUDY_HANDOVERS_M = {1: [], 2: [12, 40, 56, 92], 3: [64, 80]}      # from the earlier study (event A3, 3 dB, 2 steps)


def in_order(expected, names):
    """True if the expected messages appear in `names` in this order."""
    i = 0
    for n in names:
        if i < len(expected) and n == expected[i]:
            i += 1
    return i == len(expected)


twin = get_twin()
sectors = [s["name"] for s in twin["sectors"]]
failed = 0


def check(ok, what):
    global failed
    failed += not ok
    print("ok  " if ok else "FAIL", what)


for route in twin["routes"]:
    net, ue = simulate(route, sectors)
    msgs = [e for e in net.log if e["kind"] == "msg"]
    name = lambda e: e["message"] + (f"[{e['nas']}]" if e["nas"] else "")
    r = f"route {route['id']}:"
    for flow, expected in TAUGHT.items():
        names = [name(e) for e in msgs if e["flow"] == flow]
        if flow == 5 and not STUDY_HANDOVERS_M[route["id"]]:
            check(not names, f"{r} flow 5 absent (no handover on this route)")
            continue
        # flow 5 happens once per handover: check each one separately
        groups = [names] if flow != 5 else [[name(e) for e in msgs if e["flow"] == 5 and e["step"] == s]
                                            for s in sorted({e["step"] for e in msgs if e["flow"] == 5})]
        check(all(in_order(expected, g) for g in groups), f"{r} flow {flow} in the taught order")
    where = [e["step"] * 2 for e in msgs if e["message"] == "HandoverRequest"]
    check(where == STUDY_HANDOVERS_M[route["id"]], f"{r} Xn handovers at {where} m, as in the study")
    check(not any("supi" in e["fields"] for e in msgs if e["interface"] in ("Uu", "N2")),
          f"{r} the SUPI is never sent over the radio (Uu) or to the gNB (N2)")
    check(ue.received and ue.received[-1]["app"] == "chat message", f"{r} after paging, the chat message arrives")

print("\nall checks passed" if not failed else f"\n{failed} check(s) failed")
sys.exit(1 if failed else 0)
