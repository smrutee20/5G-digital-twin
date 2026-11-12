"""
UDM: subscriber data (with its UDR), authentication vectors (ARPF) incl. SUCI de-concealment (SIDF),
and serving-NF registration (UECM) for the AMF and SMF.
"""
from ..engine import Node


class UDM(Node):
    kind = "UDM"

    def __init__(self, name, net, subscribers):
        super().__init__(name, net)
        self.subscribers = subscribers          # suci -> supi (the SIDF's private-key view)
        self.amf_reg, self.smf_reg, self.subs = {}, {}, []

    def start(self):
        self.request("NRF", "SBI", "NF Registration", "Nnrf_NFManagement_NFRegister", lambda r: None,
                     nf_type=self.kind, nf_instance=self.name, services="nudm-ueau, nudm-uecm, nudm-sdm")

    def on_Nudm_UEAuthentication_Get(self, m):
        supi = self.subscribers[m.payload["supi_or_suci"]]         # SIDF: SUCI -> SUPI
        self.reply(m, "Nudm_UEAuthentication_Get_Response", status="200 OK", auth_type="5G_AKA", supi=supi,
                   authentication_vector=dict(av_type="5G_HE_AKA", rand="RAND", autn="AUTN", xres_star="XRES*",
                                              kausf="KAUSF"))

    def on_Nudm_UEAuthentication_ResultConfirmation(self, m):
        self.reply(m, "Nudm_UEAuthentication_ResultConfirmation_Response", status="201 Created")

    def on_Nudm_UECM_Registration(self, m):
        p = m.payload
        if "amf_instance_id" in p:
            self.amf_reg[p["supi"]] = p["amf_instance_id"]
        else:
            self.smf_reg[(p["supi"], p["pdu_session_id"])] = p["smf_instance_id"]
        self.reply(m, "Nudm_UECM_Registration_Response", status="201 Created")

    def on_Nudm_SDM_Get(self, m):
        names = m.payload["dataset_names"]
        data = {}
        if "am-data" in names:
            data["am_data"] = dict(gpsis="msisdn", nssai="default SST 1", subscribed_ue_ambr="2 Gbps / 1 Gbps")
        if "smf-select-data" in names:
            data["smf_selection_data"] = "SST 1 -> DNN internet"
        if "sm-data" in names:
            data["sm_data"] = dict(dnn="internet", pdu_session_types="IPv4", ssc_modes="1",
                                   five_qi=9, arp_priority=8, session_ambr="1 Gbps / 500 Mbps")
        self.reply(m, "Nudm_SDM_Get_Response", status="200 OK", **data)

    def on_Nudm_SDM_Subscribe(self, m):
        self.subs.append((m.src, m.payload["supi"]))
        self.reply(m, "Nudm_SDM_Subscribe_Response", status="201 Created")
