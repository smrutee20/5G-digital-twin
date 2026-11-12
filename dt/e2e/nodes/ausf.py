"""AUSF: 5G-AKA authentication server (TS 33.501 §6.1.3.2). Gets the 5G HE AV from the UDM."""
from ..engine import Node


class AUSF(Node):
    kind = "AUSF"

    def __init__(self, name, net):
        super().__init__(name, net)
        self.pending = {}               # ue -> dict(xres_star, supi)

    def start(self):
        self.request("NRF", "SBI", "NF Registration", "Nnrf_NFManagement_NFRegister", lambda r: None,
                     nf_type=self.kind, nf_instance=self.name, services="nausf-auth")

    def on_Nausf_UEAuthentication_Authenticate(self, m):
        if m.payload.get("operation") != "5g-aka-confirmation":
            def got_he_av(r):
                he = r.payload["authentication_vector"]
                self.pending[m.ue] = dict(xres_star=he["xres_star"], supi=r.payload["supi"])
                # 5G HE AV -> 5G SE AV: keep XRES* and KAUSF, send HXRES* = SHA-256(RAND || XRES*)
                self.reply(m, "Nausf_UEAuthentication_Authenticate_Response", status="201 Created",
                           auth_type="5G_AKA", **{"5g_auth_data": dict(rand=he["rand"], autn=he["autn"],
                                                                         hxres_star="HXRES*")},
                           links="/ue-authentications/{authCtxId}/5g-aka-confirmation")
            self.discover("UDM", m.procedure, lambda udm: self.request(
                udm, "SBI", m.procedure, "Nudm_UEAuthentication_Get", got_he_av, ue=m.ue,
                supi_or_suci=m.payload["supi_or_suci"], serving_network_name=m.payload["serving_network_name"],
                ausf_instance_id=self.name), ue=m.ue)
        else:
            a = self.pending.pop(m.ue)

            def confirmed(r):              # RES* == XRES*: tell the AMF, with the SUPI and KSEAF
                self.reply(m, "Nausf_UEAuthentication_Authenticate_Response", status="200 OK",
                           auth_result="AUTHENTICATION_SUCCESS", supi=a["supi"], kseaf="KSEAF")
            self.request(self.nf_cache["UDM"], "SBI", m.procedure, "Nudm_UEAuthentication_ResultConfirmation",
                         confirmed, ue=m.ue, supi=a["supi"], success=True, auth_type="5G_AKA",
                         serving_network_name="5G:mnc001.mcc001.3gppnetwork.org", res_star_check="RES* == XRES*: OK")
