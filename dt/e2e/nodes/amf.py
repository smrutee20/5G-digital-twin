"""
AMF: registration (TS 23.502 §4.2.2.2.2), 5G-AKA with AUSF/UDM (TS 33.501 §6.1.3.2), NAS security,
UDM registration/subscription, AM policy (PCF), N2 (NGAP) and relaying 5GSM messages to/from the SMF.
"""
from ..engine import Node

REG, PDU = "Registration", "PDU Session Establishment"
XN, SR = "Handover (Xn)", "Service Request"
SN_NAME = "5G:mnc001.mcc001.3gppnetwork.org"


class AMF(Node):
    kind = "AMF"

    def __init__(self, name, net, tac):
        super().__init__(name, net)
        self.tac = tac
        self.ctx = {}                       # ue -> dict(ran, suci, supi, state, ids)
        self._id = 0

    def start(self):
        self.request("NRF", "SBI", "NF Registration", "Nnrf_NFManagement_NFRegister", lambda r: None,
                     nf_type=self.kind, nf_instance=self.name, services="namf-comm, namf-evts", guami="001-01-AMF1")

    def nas_dl(self, ue, procedure, nas, **payload):
        c = self.ctx[ue]
        self.send(c["ran"], "N2", procedure, "DownlinkNASTransport", ue=ue, amf_ue_ngap_id=c["amf_ue_ngap_id"],
                  ran_ue_ngap_id=c["ran_ue_ngap_id"], nas=nas, **payload)

    # ----------------------------------------------------------- N2 set-up
    def on_NGSetupRequest(self, m):
        self.reply(m, "NGSetupResponse", amf_name=self.name, served_guami_list="001-01-AMF1",
                   relative_amf_capacity=255, plmn_support_list="001-01, SST 1")

    # ----------------------------------------------------------- registration: authentication (steps 8-9)
    def on_InitialUEMessage(self, m):
        if m.payload.get("nas") == "ServiceRequest":
            return self.service_request(m)
        self._id += 1
        ue = m.ue
        c = self.ctx[ue] = dict(ran=m.src, suci=m.payload["mobile_identity"], supi=None, state="REGISTERING",
                                amf_ue_ngap_id=self._id, ran_ue_ngap_id=m.payload["ran_ue_ngap_id"],
                                location=m.payload["user_location_information"])

        def got_se_av(r):                    # 5G SE AV (RAND, AUTN, HXRES*) -> challenge the UE
            c["hxres"] = r.payload["5g_auth_data"]["hxres_star"]
            self.nas_dl(ue, REG, "AuthenticationRequest", ngksi=1, abba="0x0000",
                        rand=r.payload["5g_auth_data"]["rand"], autn=r.payload["5g_auth_data"]["autn"])

        self.discover("AUSF", REG, lambda ausf: self.request(
            ausf, "SBI", REG, "Nausf_UEAuthentication_Authenticate", got_se_av, ue=ue,
            supi_or_suci=c["suci"], serving_network_name=SN_NAME), ue=ue)

    def on_UplinkNASTransport(self, m):
        ue, nas, c = m.ue, m.payload["nas"], self.ctx[m.ue]
        if nas == "AuthenticationResponse":
            # AMF compares HRES* with HXRES* (serving-network check), then the AUSF confirms with RES*
            def confirmed(r):
                c["supi"] = r.payload["supi"]
                self.nas_dl(ue, REG, "SecurityModeCommand", ngksi=1, selected_nas_security_algorithms="5G-EA2 / 5G-IA2",
                            replayed_ue_security_capabilities="NEA0-2, NIA1-2", imeisv_request=True)
            self.request(self.nf_cache["AUSF"], "SBI", REG, "Nausf_UEAuthentication_Authenticate", confirmed,
                         ue=ue, operation="5g-aka-confirmation", res_star=m.payload["authentication_response_parameter"],
                         hres_star_check="HRES* == HXRES*: OK")
        elif nas == "SecurityModeComplete":
            self.after_security(ue)
        elif nas == "RegistrationComplete":
            c["state"] = "REGISTERED"
        elif nas == "ULNASTransport" and m.payload.get("nas_sm") == "PDUSessionEstablishmentRequest":
            p = m.payload
            self.discover("SMF", PDU, lambda smf: self.request(
                smf, "SBI", PDU, "Nsmf_PDUSession_CreateSMContext", lambda r: None, ue=ue,
                supi=c["supi"], pdu_session_id=p["pdu_session_id"], dnn=p["dnn"], s_nssai=p["s_nssai"],
                serving_nf_id=self.name, an_type="3GPP_ACCESS", rat_type="NR",
                ue_location=m.payload["user_location_information"], request_type=p["request_type"],
                n1_sm_msg="PDUSessionEstablishmentRequest", pdu_session_type=p["pdu_session_type"],
                ssc_mode=p["ssc_mode"]), ue=ue)
        else:
            raise RuntimeError(f"AMF: unexpected NAS {nas}")

    # ----------------------------------------------------------- registration: steps 13-21
    def after_security(self, ue):
        c = self.ctx[ue]

        def ics(_):                          # step 21: Registration Accept inside Initial Context Setup
            self.request(c["ran"], "N2", REG, "InitialContextSetupRequest", lambda r: None, ue=ue,
                         amf_ue_ngap_id=c["amf_ue_ngap_id"], ran_ue_ngap_id=c["ran_ue_ngap_id"],
                         guami="001-01-AMF1", allowed_nssai="SST 1", ue_security_capabilities="NEA0-2, NIA1-2",
                         security_key="KgNB", nas="RegistrationAccept", registration_result="3GPP access",
                         guti=f"5g-guti-00101-AMF1-{c['amf_ue_ngap_id']:08x}", tai_list=[f"001-01-{self.tac}"],
                         t3512="54 min")

        def policy(_):                       # steps 15-16: PCF selection + AM policy association
            self.discover("PCF", REG, lambda pcf: self.request(
                pcf, "SBI", REG, "Npcf_AMPolicyControl_Create", ics, ue=ue, supi=c["supi"],
                access_type="3GPP_ACCESS", rat_type="NR", user_location=c["location"]), ue=ue)

        def subscribe(_):
            self.request(self.nf_cache["UDM"], "SBI", REG, "Nudm_SDM_Subscribe", policy, ue=ue, supi=c["supi"],
                         monitored_resources="am-data, smf-select-data, ue-context-in-smf-data")

        def sdm(_):
            self.request(self.nf_cache["UDM"], "SBI", REG, "Nudm_SDM_Get", subscribe, ue=ue, supi=c["supi"],
                         dataset_names="am-data, smf-select-data, ue-context-in-smf-data")

        # steps 13-14: UDM selection, UECM registration, subscription data
        self.discover("UDM", REG, lambda udm: self.request(
            udm, "SBI", REG, "Nudm_UECM_Registration", sdm, ue=ue, supi=c["supi"], amf_instance_id=self.name,
            guami="001-01-AMF1", rat_type="NR", initial_registration_ind=True), ue=ue)

    # ----------------------------------------------------------- Service Request (TS 23.502 §4.2.3.2)
    def service_request(self, m):
        """A registered UE comes back through another gNB (e.g. its own was switched off)."""
        ue, c = m.ue, self.ctx[m.ue]
        old = c["ran"]
        if old != m.src:                     # implicit release of the N2 association with the old gNB
            self.send(old, "N2", SR, "UEContextReleaseCommand", ue=ue, amf_ue_ngap_id=c["amf_ue_ngap_id"],
                      cause="radio connection with UE lost")
        c.update(ran=m.src, ran_ue_ngap_id=m.payload["ran_ue_ngap_id"], location=m.payload["user_location_information"])
        smf = self.nf_cache["SMF"]

        def got_n2(r):                       # SMF returns the session's N2 info (UL tunnel, QoS flow)
            p = r.payload
            self.request(c["ran"], "N2", SR, "InitialContextSetupRequest", setup_done, ue=ue,
                         amf_ue_ngap_id=c["amf_ue_ngap_id"], ran_ue_ngap_id=c["ran_ue_ngap_id"], guami="001-01-AMF1",
                         allowed_nssai="SST 1", ue_security_capabilities="NEA0-2, NIA1-2", security_key="KgNB",
                         nas="ServiceAccept", pdu_session_resource_setup_list_cxt_req=[dict(
                             pdu_session_id=1, s_nssai=p["s_nssai"], transfer=p["n2_sm_info"])])

        def setup_done(r):                   # new DL tunnel -> SMF -> UPF (the core re-routes the session)
            self.request(smf, "SBI", SR, "Nsmf_PDUSession_UpdateSMContext", lambda x: None, ue=ue,
                         n2_sm_info_type="PDU_RES_SETUP_RSP",
                         n2_sm_info=r.payload["pdu_session_resource_setup_list_cxt_res"][0]["transfer"])

        self.request(smf, "SBI", SR, "Nsmf_PDUSession_UpdateSMContext", got_n2, ue=ue, up_cnx_state="ACTIVATING",
                     an_type="3GPP_ACCESS", ue_location=c["location"])

    # ----------------------------------------------------------- Xn handover: Path Switch (TS 23.502 §4.9.1.2.2)
    def on_PathSwitchRequest(self, m):
        ue, c = m.ue, self.ctx[m.ue]
        c.update(ran=m.src, ran_ue_ngap_id=m.payload["ran_ue_ngap_id"], location=m.payload["user_location_information"])
        item = m.payload["pdu_session_resource_to_be_switched_dl_list"][0]
        dl = item["transfer"]["dl_ngu_up_tnl_information"]
        self.request(self.nf_cache["SMF"], "SBI", XN, "Nsmf_PDUSession_UpdateSMContext",
                     lambda r: self.reply(m, "PathSwitchRequestAcknowledge", amf_ue_ngap_id=c["amf_ue_ngap_id"],
                                          ran_ue_ngap_id=c["ran_ue_ngap_id"], security_context="NH, NCC",
                                          pdu_session_resource_switched_list=[dict(pdu_session_id=1)],
                                          ho_id=m.payload.get("ho_id")),
                     ue=ue, n2_sm_info_type="PATH_SWITCH_REQ", ho_id=m.payload.get("ho_id"),
                     n2_sm_info=dict(dl_qos_flow_per_tnl_information=dict(up_transport_layer_information=dl)),
                     ue_location=c["location"])

    # ----------------------------------------------------------- PDU session (SMF -> AMF -> RAN)
    def on_Namf_Communication_N1N2MessageTransfer(self, m):
        ue, c, p = m.ue, self.ctx[m.ue], m.payload
        self.reply(m, "Namf_Communication_N1N2MessageTransfer_Response", status="200 OK",
                   cause="N1_N2_TRANSFER_INITIATED")

        def setup_done(r):                   # steps 14-15: AN tunnel info -> SMF
            self.request(m.src, "SBI", PDU, "Nsmf_PDUSession_UpdateSMContext", lambda x: None, ue=ue,
                         n2_sm_info_type="PDU_RES_SETUP_RSP",
                         n2_sm_info=r.payload["pdu_session_resource_setup_list_su_res"][0]["transfer"])

        # step 12: N2 PDU Session Resource Setup Request with the NAS DL NAS TRANSPORT (5GSM Accept) inside
        self.request(c["ran"], "N2", PDU, "PDUSessionResourceSetupRequest", setup_done, ue=ue,
                     amf_ue_ngap_id=c["amf_ue_ngap_id"], ran_ue_ngap_id=c["ran_ue_ngap_id"],
                     pdu_session_resource_setup_list_su_req=[dict(
                         pdu_session_id=p["pdu_session_id"], s_nssai=p["s_nssai"],
                         nas="DLNASTransport", nas_sm=p["n1_sm_msg"], n1_sm=p["n1_sm_container"],
                         transfer=p["n2_sm_info"])])
