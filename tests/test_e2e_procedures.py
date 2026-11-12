"""
Test: initial registration and PDU session establishment for ONE UE, with 3GPP message names.

    python tests/test_e2e_procedures.py        # runs the checks and prints the message sequence
    python -m pytest tests/ -s                 # same, if pytest is installed

References: TS 23.502 §4.2.2.2.2 (registration), §4.3.2.2.1 (PDU session establishment),
TS 33.501 §6.1.3.2 (5G-AKA), TS 38.401 §8.1 / §8.9 (gNB-internal F1/E1 flows).
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dt.config import load_config, DATA      # noqa: E402
from dt.e2e import E2ENetwork                # noqa: E402

UE = "UE00"
_RUN = {}


def run_one_ue():
    """Build the network with a single UE and run 300 ms (enough for both procedures + some data)."""
    if "net" not in _RUN:
        cfg = copy.deepcopy(load_config())
        cfg["e2e"].update(num_ues=1, duration_ms=300, attach_start_ms=10, attach_window_ms=1)
        _RUN["net"] = E2ENetwork(cfg, DATA).run()
    return _RUN["net"]


def kind(net, name):
    return net.net.nodes[name].kind


def ue_messages(net, procedures):
    return [r for r in net.trace.records if r.get("ue") == UE and r["procedure"] in procedures]


def assert_in_order(net, records, expected):
    """Every expected step must appear, in this order (other messages may sit in between)."""
    i = 0
    for step, (src, dst, iface, msg, extra) in enumerate(expected, 1):
        while i < len(records):
            r = records[i]
            i += 1
            if (kind(net, r["src"]), kind(net, r["dst"]), r["interface"], r["message"]) == (src, dst, iface, msg) \
                    and all(r.get(k) == v for k, v in extra.items()):
                break
        else:
            raise AssertionError(f"step {step} missing or out of order: {src} -> {dst} {iface} {msg} {extra}")


def first(net, **match):
    return next(r for r in net.trace.records if all(r.get(k) == v for k, v in match.items()))


# --------------------------------------------------------------------------- 1. initial registration
REGISTRATION = [
    ("UE", "RU", "Uu", "RandomAccessPreamble", {}),
    ("RU", "UE", "Uu", "RandomAccessResponse", {}),
    ("UE", "RU", "Uu", "RRCSetupRequest", {}),
    ("DU", "CU-CP", "F1-C", "InitialULRRCMessageTransfer", {"rrc": "RRCSetupRequest"}),
    ("CU-CP", "DU", "F1-C", "DLRRCMessageTransfer", {"rrc": "RRCSetup"}),
    ("RU", "UE", "Uu", "RRCSetup", {}),
    ("UE", "RU", "Uu", "RRCSetupComplete", {"nas": "RegistrationRequest"}),
    ("CU-CP", "AMF", "N2", "InitialUEMessage", {"nas": "RegistrationRequest"}),
    ("AMF", "AUSF", "SBI", "Nausf_UEAuthentication_Authenticate", {}),
    ("AUSF", "UDM", "SBI", "Nudm_UEAuthentication_Get", {}),
    ("UDM", "AUSF", "SBI", "Nudm_UEAuthentication_Get_Response", {}),
    ("AUSF", "AMF", "SBI", "Nausf_UEAuthentication_Authenticate_Response", {"status": "201 Created"}),
    ("AMF", "CU-CP", "N2", "DownlinkNASTransport", {"nas": "AuthenticationRequest"}),
    ("RU", "UE", "Uu", "DLInformationTransfer", {"nas": "AuthenticationRequest"}),
    ("UE", "RU", "Uu", "ULInformationTransfer", {"nas": "AuthenticationResponse"}),
    ("CU-CP", "AMF", "N2", "UplinkNASTransport", {"nas": "AuthenticationResponse"}),
    ("AMF", "AUSF", "SBI", "Nausf_UEAuthentication_Authenticate", {"operation": "5g-aka-confirmation"}),
    ("AUSF", "UDM", "SBI", "Nudm_UEAuthentication_ResultConfirmation", {}),
    ("AUSF", "AMF", "SBI", "Nausf_UEAuthentication_Authenticate_Response", {"auth_result": "AUTHENTICATION_SUCCESS"}),
    ("AMF", "CU-CP", "N2", "DownlinkNASTransport", {"nas": "SecurityModeCommand"}),
    ("UE", "RU", "Uu", "ULInformationTransfer", {"nas": "SecurityModeComplete"}),
    ("AMF", "UDM", "SBI", "Nudm_UECM_Registration", {}),
    ("AMF", "UDM", "SBI", "Nudm_SDM_Get", {}),
    ("AMF", "UDM", "SBI", "Nudm_SDM_Subscribe", {}),
    ("AMF", "PCF", "SBI", "Npcf_AMPolicyControl_Create", {}),
    ("AMF", "CU-CP", "N2", "InitialContextSetupRequest", {"nas": "RegistrationAccept"}),
    ("CU-CP", "DU", "F1-C", "UEContextSetupRequest", {"rrc": "SecurityModeCommand"}),
    ("RU", "UE", "Uu", "SecurityModeCommand", {}),
    ("UE", "RU", "Uu", "SecurityModeComplete", {}),
    ("RU", "UE", "Uu", "RRCReconfiguration", {"nas": "RegistrationAccept"}),
    ("UE", "RU", "Uu", "RRCReconfigurationComplete", {}),
    ("UE", "RU", "Uu", "ULInformationTransfer", {"nas": "RegistrationComplete"}),
    ("CU-CP", "AMF", "N2", "InitialContextSetupResponse", {}),
    ("CU-CP", "AMF", "N2", "UplinkNASTransport", {"nas": "RegistrationComplete"}),
]


def test_initial_registration():
    net = run_one_ue()
    recs = ue_messages(net, {"Initial Access", "Registration"})
    assert_in_order(net, recs, REGISTRATION)
    ue, amf = net.ues[0], net.net.nodes["AMF"]
    assert ue.mm_state == "REGISTERED" and amf.ctx[UE]["state"] == "REGISTERED"
    # the UE sent a concealed identity; the UDM's SIDF resolved it to the SUPI
    reg = first(net, ue=UE, interface="N2", message="InitialUEMessage")
    assert reg["mobile_identity"] == ue.suci != ue.supi
    assert first(net, ue=UE, message="Nudm_UEAuthentication_Get_Response")["supi"] == ue.supi
    assert amf.ctx[UE]["supi"] == ue.supi
    # NAS security is set up before Registration Accept; the UE got a 5G-GUTI
    t_smc = first(net, ue=UE, interface="N2", nas="SecurityModeCommand")["t_ms"]
    t_acc = first(net, ue=UE, interface="N2", nas="RegistrationAccept")["t_ms"]
    assert t_smc < t_acc and ue.guti and ue.guti.startswith("5g-guti")


# --------------------------------------------------------------------------- 2. PDU session establishment
PDU_SESSION = [
    ("UE", "RU", "Uu", "ULInformationTransfer", {"nas": "ULNASTransport", "nas_sm": "PDUSessionEstablishmentRequest"}),
    ("CU-CP", "AMF", "N2", "UplinkNASTransport", {"nas_sm": "PDUSessionEstablishmentRequest"}),
    ("AMF", "SMF", "SBI", "Nsmf_PDUSession_CreateSMContext", {}),
    ("SMF", "UDM", "SBI", "Nudm_UECM_Registration", {}),
    ("SMF", "UDM", "SBI", "Nudm_SDM_Get", {"dataset_names": "sm-data"}),
    ("SMF", "UDM", "SBI", "Nudm_SDM_Subscribe", {}),
    ("SMF", "AMF", "SBI", "Nsmf_PDUSession_CreateSMContext_Response", {"status": "201 Created"}),
    ("SMF", "PCF", "SBI", "Npcf_SMPolicyControl_Create", {}),
    ("PCF", "SMF", "SBI", "Npcf_SMPolicyControl_Create_Response", {}),
    ("SMF", "UPF", "N4", "PFCPSessionEstablishmentRequest", {}),
    ("UPF", "SMF", "N4", "PFCPSessionEstablishmentResponse", {}),
    ("SMF", "AMF", "SBI", "Namf_Communication_N1N2MessageTransfer", {"n1_sm_msg": "PDUSessionEstablishmentAccept"}),
    ("AMF", "CU-CP", "N2", "PDUSessionResourceSetupRequest", {}),
    ("CU-CP", "CU-UP", "E1", "BearerContextSetupRequest", {}),
    ("CU-UP", "CU-CP", "E1", "BearerContextSetupResponse", {}),
    ("CU-CP", "DU", "F1-C", "UEContextModificationRequest", {}),
    ("DU", "CU-CP", "F1-C", "UEContextModificationResponse", {}),
    ("CU-CP", "CU-UP", "E1", "BearerContextModificationRequest", {}),
    ("CU-UP", "CU-CP", "E1", "BearerContextModificationResponse", {}),
    ("RU", "UE", "Uu", "RRCReconfiguration", {"nas": "DLNASTransport", "nas_sm": "PDUSessionEstablishmentAccept"}),
    ("UE", "RU", "Uu", "RRCReconfigurationComplete", {}),
    ("CU-CP", "AMF", "N2", "PDUSessionResourceSetupResponse", {}),
    ("AMF", "SMF", "SBI", "Nsmf_PDUSession_UpdateSMContext", {}),
    ("SMF", "UPF", "N4", "PFCPSessionModificationRequest", {}),
    ("UPF", "SMF", "N4", "PFCPSessionModificationResponse", {}),
    ("SMF", "AMF", "SBI", "Nsmf_PDUSession_UpdateSMContext_Response", {}),
]


def test_pdu_session_establishment():
    net = run_one_ue()
    assert_in_order(net, ue_messages(net, {"PDU Session Establishment"}), PDU_SESSION)
    ue = net.ues[0]
    assert ue.session == "ACTIVE"

    # UPF selection: recorded in the N4 request; the single UE gets the UPF local to its tracking area
    est = first(net, ue=UE, message="PFCPSessionEstablishmentRequest")
    sel = est["upf_selection"]
    assert sel["selected"] == est["dst"] == "UPF-EDGE"
    assert {c["upf"] for c in sel["candidates"]} == {"UPF-EDGE", "UPF-CENTRAL"}

    # QoS flow QFI 1 / 5QI 9 at every element: UPF (QER), NG-RAN (N2 QoS profile, F1 DRB), UE (QoS rule)
    assert est["create_qer"][0]["five_qi"] == 9 and est["create_qer"][0]["qfi"] == 1
    n2 = first(net, ue=UE, message="PDUSessionResourceSetupRequest")["pdu_session_resource_setup_list_su_req"][0]
    flow = n2["transfer"]["qos_flow_setup_request_list"][0]
    assert (flow["qfi"], flow["five_qi"], flow["resource_type"]) == (1, 9, "Non-GBR")
    f1 = first(net, ue=UE, message="UEContextModificationRequest")["drbs_to_be_setup"][0]
    assert f1["qos"]["five_qi"] == 9 and f1["flows_mapped_to_drb"] == [1]
    assert ue.qos_rules[0]["qfi"] == 1 and ue.qos_rules[0]["default_rule"]

    # N3 GTP-U tunnel: UL TEID allocated by the UPF, DL TEID by the CU-UP, and the data actually uses them
    ul_teid = first(net, ue=UE, message="PFCPSessionEstablishmentResponse")["created_pdr"][0]["local_f_teid"]["teid"]
    assert n2["transfer"]["ul_ngu_up_tnl_information"]["gtp_teid"] == ul_teid
    e1 = first(net, ue=UE, message="BearerContextSetupResponse")["pdu_session_resource_setup_list"][0]
    dl_teid = e1["ng_dl_up_tnl_information"]["gtp_teid"]
    mod = first(net, ue=UE, message="PFCPSessionModificationRequest")["update_far"][0]
    assert est["create_far"][1]["apply_action"] == "BUFF" and mod["apply_action"] == "FORW"
    assert mod["forwarding_parameters"]["outer_header_creation"]["teid"] == dl_teid
    assert first(net, ue=UE, interface="N3", message="G-PDU", direction="UL")["teid"] == ul_teid
    dl = first(net, ue=UE, interface="N3", message="G-PDU", direction="DL")
    assert dl["teid"] == dl_teid and dl["qfi"] == 1
    assert ue.ue_ip and ue.ue_ip.startswith("10.45.") and ue.rx_bytes > 0


# --------------------------------------------------------------------------- printing
def print_sequence(net):
    detail_keys = ("rrc", "nas", "nas_sm", "uu", "operation", "status")
    procs = ["Initial Access", "Registration", "PDU Session Establishment"]
    short = {"Initial Access": "ACCESS", "Registration": "REG", "PDU Session Establishment": "PDU",
             "User Plane UL": "UP-UL", "User Plane DL": "UP-DL"}
    ue_recs = [r for r in net.trace.records if r.get("ue") == UE]
    # control plane, then the first uplink request and the first downlink batch along the user-plane path
    first_dl_epoch = next(r["epoch"] for r in ue_recs if r["procedure"] == "User Plane DL")
    recs = [r for r in ue_recs if r["procedure"] in procs or r["procedure"] == "User Plane UL"
            or (r["procedure"] == "User Plane DL" and r.get("epoch") == first_dl_epoch)]
    print(f"Message sequence for {UE} ({len(recs)} messages; NAS = 5GMM, NAS-SM = 5GSM inside NAS transport)\n")
    print(f"{'#':>3} {'t [ms]':>8}  {'proc':<6} {'source':>12} -> {'destination':<12} {'interface':<9} {'message':<47} detail")
    for i, r in enumerate(recs, 1):
        d = ", ".join(f"{k}={r[k]}" for k in detail_keys if k in r)
        if "bytes" in r:
            d = ", ".join(x for x in (d, f"bytes={r['bytes']}", f"teid={r['teid']}" if "teid" in r else "",
                                      f"qfi={r['qfi']}" if "qfi" in r else "") if x)
        if r["message"] == "PFCPSessionEstablishmentRequest":
            d = f"UPF selected: {r['upf_selection']['selected']}; QER QFI 1 / 5QI {r['create_qer'][0]['five_qi']}"
        if r["message"] == "PDUSessionResourceSetupRequest":
            f = r["pdu_session_resource_setup_list_su_req"][0]["transfer"]
            d = (f"QoS flow QFI {f['qos_flow_setup_request_list'][0]['qfi']} 5QI "
                 f"{f['qos_flow_setup_request_list'][0]['five_qi']}, UL N3 TEID {f['ul_ngu_up_tnl_information']['gtp_teid']}")
        print(f"{i:3d} {r['t_ms']:8.2f}  {short[r['procedure']]:<6} {r['src']:>12} -> {r['dst']:<12} "
              f"{r['interface']:<9} {r['message']:<47} {d}")


if __name__ == "__main__":
    net = run_one_ue()
    print_sequence(net)
    print()
    for t in (test_initial_registration, test_pdu_session_establishment):
        t()
        print(f"PASS  {t.__name__}")
