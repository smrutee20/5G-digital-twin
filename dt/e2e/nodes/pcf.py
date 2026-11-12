"""PCF: access/mobility policy (AMF) and session-management policy with the default QoS (SMF)."""
from ..engine import Node
from ..qos import default_flow, session_ambr


class PCF(Node):
    kind = "PCF"

    def __init__(self, name, net, default_qos):
        super().__init__(name, net)
        self.q = default_qos

    def start(self):
        self.request("NRF", "SBI", "NF Registration", "Nnrf_NFManagement_NFRegister", lambda r: None,
                     nf_type=self.kind, nf_instance=self.name, services="npcf-am-policy-control, npcf-smpolicycontrol")

    def on_Npcf_AMPolicyControl_Create(self, m):
        self.reply(m, "Npcf_AMPolicyControl_Create_Response", status="201 Created", rfsp=1,
                   service_area_restriction="unrestricted")

    def on_Npcf_SMPolicyControl_Create(self, m):
        f = default_flow(self.q)
        # SM policy decision: authorized default QoS of the session + session AMBR
        self.reply(m, "Npcf_SMPolicyControl_Create_Response", status="201 Created",
                   sess_rules=dict(auth_def_qos=dict(five_qi=f["five_qi"], arp=f["arp"],
                                                     priority_level=f["priority_level"]),
                                   auth_sess_ambr=session_ambr(self.q)),
                   pcc_rules="default rule: match-all -> QoS data 5QI %d" % f["five_qi"])
