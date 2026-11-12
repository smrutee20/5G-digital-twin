"""
CU-CP (one per gNB): RRC and the control plane of PDCP. Terminates F1-C, E1, N2 (NGAP) and Xn-C (XnAP).

Flows: initial access / registration / PDU session (TS 38.401 §8.1, §8.9), intra-gNB handover between two
cells of the same DU (RRC reconfiguration with sync), Xn handover between gNBs (TS 38.300 §9.2.3.2,
TS 23.502 §4.9.1.2: preparation, data forwarding, Path Switch, UE Context Release), and the Service
Request after a radio link failure (Initial Context Setup with the PDU session).
"""
from ..engine import Node

ACCESS, REG, PDU = "Initial Access", "Registration", "PDU Session Establishment"
XN, INTRA, SR = "Handover (Xn)", "Handover (intra-gNB)", "Service Request"


class CUCP(Node):
    kind = "CU-CP"

    def __init__(self, name, net, amf, cu_up, tac, gnb_id):
        super().__init__(name, net)
        self.amf, self.cu_up, self.tac, self.gnb_id = amf, cu_up, tac, gnb_id
        self.ctx = {}                  # ue -> dict(du, cell, ids, session, pending ...)
        self._id = 100 * gnb_id

    def start(self):
        self.request(self.amf, "N2", "NG Setup", "NGSetupRequest", lambda r: None,
                     global_ran_node_id=f"gNB-IITGN-{self.gnb_id}", supported_ta_list=f"TAC {self.tac}, PLMN 001-01, SST 1",
                     default_paging_drx="v128")

    # ----------------------------------------------------------- set-up procedures
    def on_F1SetupRequest(self, m):
        self.reply(m, "F1SetupResponse", cells_to_be_activated=m.payload["served_cells"])

    def on_GNBCUUPE1SetupRequest(self, m):
        self.reply(m, "GNBCUUPE1SetupResponse")

    def on_NGSetupResponse(self, m):
        pass

    def to_ue(self, ue, procedure, rrc, **payload):
        self.send(self.ctx[ue]["du"], "F1-C", procedure, "DLRRCMessageTransfer", ue=ue, rrc=rrc, **payload)

    def user_location(self, ue):
        return dict(nr_cgi=self.ctx[ue]["cell"], tai=f"001-01-{self.tac}")

    def new_ids(self):
        self._id += 1
        return self._id

    # ----------------------------------------------------------- bearer set-up (PDU session, Xn target, SR)
    def setup_bearer(self, ue, procedure, sess, then, forwarding=False):
        """E1 bearer (N3 + F1-U tunnels) -> F1 DRB at the DU -> E1 with the DU's F1-U endpoint -> then(e1_resp)."""
        c, flow = self.ctx[ue], sess["flow"]
        state = {}

        def bearer_ready(r):
            state["e1"] = r.payload["pdu_session_resource_setup_list"][0]
            c["ng_dl_up_tnl"] = state["e1"]["ng_dl_up_tnl_information"]
            drb = dict(drb_id=1, qos=dict(five_qi=flow["five_qi"], arp=flow["arp"]), flows_mapped_to_drb=[flow["qfi"]],
                       ul_up_tnl_information=state["e1"]["drb_setup_list"][0]["ul_up_tnl_information"])
            if c.get("ho_in"):                       # handover target: UE context + DRB before the UE arrives
                self.request(c["du"], "F1-C", procedure, "UEContextSetupRequest", drb_ready, ue=ue, handover=True,
                             target_cell=c["cell"], drbs_to_be_setup=[drb], ho_id=c["ho_in"]["ho_id"])
            else:
                self.request(c["du"], "F1-C", procedure, "UEContextModificationRequest", drb_ready, ue=ue,
                             drbs_to_be_setup=[drb])

        def drb_ready(r):
            dl = r.payload["drbs_setup"][0]["dl_up_tnl_information"]
            self.request(self.cu_up, "E1", procedure, "BearerContextModificationRequest",
                         lambda x: then(state["e1"]), ue=ue, pdu_session_id=1, drb_id=1, dl_up_parameters=dl)

        self.request(self.cu_up, "E1", procedure, "BearerContextSetupRequest", bearer_ready, ue=ue,
                     pdu_session_resource_to_setup_list=[dict(
                         pdu_session_id=1, s_nssai=sess["s_nssai"], ng_ul_up_tnl_information=sess["ul_tnl"],
                         qos_flow_information_to_be_setup=[flow], dl_forwarding="proposed" if forwarding else None,
                         drb_to_setup_list=[dict(drb_id=1, sdap_configuration=f"default DRB, QFI {flow['qfi']}",
                                                 pdcp_configuration="SN 18 bit, RLC-AM", flow_mapping=[flow["qfi"]])])],
                     du=c["du"])

    def setup_response(self, ue):
        c = self.ctx[ue]
        return [dict(pdu_session_id=1, transfer=dict(dl_qos_flow_per_tnl_information=dict(
            up_transport_layer_information=c["ng_dl_up_tnl"], associated_qos_flow_list=[c["session"]["flow"]["qfi"]])))]

    # ----------------------------------------------------------- RRC from the UE
    def on_InitialULRRCMessageTransfer(self, m):
        self.ctx[m.ue] = dict(du=m.src, ran_ue_ngap_id=self.new_ids(), cell=m.payload["nr_cgi"])
        proc = SR if m.payload.get("establishment_cause") == "mo-Data" else ACCESS
        self.to_ue(m.ue, proc, "RRCSetup", srb_id=0, radio_bearer_config="SRB1",
                   master_cell_group=m.payload["du_to_cu_rrc_container"])

    def on_ULRRCMessageTransfer(self, m):
        c, rrc = self.ctx[m.ue], m.payload["rrc"]
        nas = {k: v for k, v in m.payload.items() if k not in ("rrc", "srb_id", "ref_point", "selected_plmn")}
        if rrc == "RRCSetupComplete":
            self.send(self.amf, "N2", m.procedure, "InitialUEMessage", ue=m.ue, ran_ue_ngap_id=c["ran_ue_ngap_id"],
                      user_location_information=self.user_location(m.ue),
                      rrc_establishment_cause="mo-Data" if m.procedure == SR else "mo-Signalling", **nas)
        elif rrc == "ULInformationTransfer":
            self.send(self.amf, "N2", m.procedure, "UplinkNASTransport", ue=m.ue, amf_ue_ngap_id=c["amf_ue_ngap_id"],
                      ran_ue_ngap_id=c["ran_ue_ngap_id"], user_location_information=self.user_location(m.ue), **nas)
        elif rrc == "SecurityModeComplete":             # AS security on
            sess = c.get("pending_session")
            final = lambda e1=None: self.to_ue(m.ue, m.procedure, "RRCReconfiguration", radio_bearer_config=(
                "SRB2, DRB1" if sess else "SRB2"), **c.pop("pending_nas"))
            self.setup_bearer(m.ue, m.procedure, sess, final) if sess else final()
        elif rrc == "MeasurementReport":
            self.handover_decision(m)
        elif rrc == "RRCReconfigurationComplete":
            if c.get("ho_intra"):                       # intra-gNB handover done
                c["cell"] = c.pop("ho_intra")
            elif c.get("ho_in"):                        # Xn target: UE arrived -> Path Switch to the AMF
                self.path_switch(m.ue)
            elif c.get("pending_n2") is not None:
                req = c.pop("pending_n2")
                ids = dict(amf_ue_ngap_id=c["amf_ue_ngap_id"], ran_ue_ngap_id=c["ran_ue_ngap_id"])
                if req.message == "InitialContextSetupRequest":
                    extra = {"pdu_session_resource_setup_list_cxt_res": self.setup_response(m.ue)} \
                        if c.get("pending_session") else {}
                    c.pop("pending_session", None)
                    self.reply(req, "InitialContextSetupResponse", **ids, **extra)
                else:
                    self.reply(req, "PDUSessionResourceSetupResponse", **ids,
                               pdu_session_resource_setup_list_su_res=self.setup_response(m.ue))

    # ----------------------------------------------------------- NGAP from the AMF
    def on_DownlinkNASTransport(self, m):
        self.ctx[m.ue]["amf_ue_ngap_id"] = m.payload["amf_ue_ngap_id"]
        nas = {k: v for k, v in m.payload.items() if k not in ("amf_ue_ngap_id", "ran_ue_ngap_id", "ref_point")}
        self.to_ue(m.ue, m.procedure, "DLInformationTransfer", **nas)

    def on_InitialContextSetupRequest(self, m):
        c, p = self.ctx[m.ue], m.payload
        c["amf_ue_ngap_id"] = p["amf_ue_ngap_id"]
        c["pending_n2"] = m
        c["pending_nas"] = {k: p[k] for k in ("nas", "guti", "allowed_nssai", "tai_list", "registration_result")
                            if k in p}
        if p.get("pdu_session_resource_setup_list_cxt_req"):          # Service Request: re-establish the session
            item = p["pdu_session_resource_setup_list_cxt_req"][0]
            c["session"] = c["pending_session"] = self.session_from(item)
        self.request(c["du"], "F1-C", m.procedure, "UEContextSetupRequest", lambda r: None, ue=m.ue,
                     rrc="SecurityModeCommand", srbs_to_be_setup="SRB2",
                     security_algorithms="NEA2/NIA2 (from UE security capabilities)")

    @staticmethod
    def session_from(item):
        tr = item["transfer"]
        return dict(s_nssai=item["s_nssai"], ul_tnl=tr["ul_ngu_up_tnl_information"],
                    flow=tr["qos_flow_setup_request_list"][0], ambr=tr.get("pdu_session_aggregate_maximum_bit_rate"))

    def on_PDUSessionResourceSetupRequest(self, m):
        c = self.ctx[m.ue]
        c["pending_n2"] = m
        item = m.payload["pdu_session_resource_setup_list_su_req"][0]
        c["session"] = self.session_from(item)
        self.setup_bearer(m.ue, PDU, c["session"], lambda e1: self.to_ue(
            m.ue, PDU, "RRCReconfiguration", radio_bearer_config="DRB1 (SDAP: QFI 1, default DRB)",
            nas=item["nas"], nas_sm=item["nas_sm"], **item["n1_sm"]))

    # ----------------------------------------------------------- handover: decision (source)
    def handover_decision(self, m):
        c, target = self.ctx[m.ue], m.payload["target_cell"]
        if c.get("ho_out") or c.get("ho_intra") or c.get("ho_in"):
            return                                       # one handover at a time
        owner = self.net.cell_owner[target]              # (DU, CU-CP) serving the target cell
        hid = self.net.new_ho_id()
        if owner[1] == self.name:                        # same gNB: reconfiguration with sync, no core involved
            c["ho_intra"] = target
            self.request(c["du"], "F1-C", INTRA, "UEContextModificationRequest", lambda r: None, ue=m.ue,
                         rrc="RRCReconfiguration", reconfiguration_with_sync=True, target_cell=target,
                         rach_config_dedicated="contention-free preamble", transmission_action_indicator="stop",
                         intra_du=owner[0] == c["du"], ho_id=hid)
            return
        c["ho_out"] = dict(target=owner[1], ho_id=hid)
        s = c["session"]

        def acked(r):                                    # target ready: forwarding on, then the handover command
            fwd = r.payload["pdu_session_resources_admitted_list"][0]["dl_forwarding_up_tnl_information"]
            self.request(self.cu_up, "E1", XN, "BearerContextModificationRequest", lambda x: command(r), ue=m.ue,
                         pdu_session_id=1, data_forwarding_information=fwd, ho_id=hid)

        def command(r):
            self.request(c["du"], "F1-C", XN, "UEContextModificationRequest", lambda x: None, ue=m.ue,
                         rrc="RRCReconfiguration", reconfiguration_with_sync=True, target_cell=target,
                         rach_config_dedicated="contention-free preamble",
                         transmission_action_indicator="stop", intra_du=False, ho_id=hid)
            self.send(owner[1], "Xn-C", XN, "SNStatusTransfer", ue=m.ue, ho_id=hid,
                      drbs_subject_to_status_transfer="DRB1: UL/DL COUNT")

        self.request(owner[1], "Xn-C", XN, "HandoverRequest", acked, ue=m.ue, ho_id=hid, cause="handover-desirable",
                     target_cell=target, source_ng_ran_node=self.name,
                     ue_context_information=dict(amf_ue_ngap_id=c["amf_ue_ngap_id"], guami="001-01-AMF1",
                                                 security_information="KgNB*, NEA2/NIA2",
                                                 pdu_session_resources_to_be_setup=[dict(
                                                     pdu_session_id=1, s_nssai=s["s_nssai"], ul_ng_u_tnl=s["ul_tnl"],
                                                     qos_flows=[s["flow"]], ambr=s.get("ambr"))]),
                     rrc_context="HandoverPreparationInformation", measurement=m.payload.get("meas_results"))

    # ----------------------------------------------------------- handover: target side
    def on_HandoverRequest(self, m):
        p = m.payload
        du = self.net.cell_owner[p["target_cell"]][0]
        ui = p["ue_context_information"]
        sr = ui["pdu_session_resources_to_be_setup"][0]
        self.ctx[m.ue] = c = dict(du=du, cell=p["target_cell"], ran_ue_ngap_id=self.new_ids(),
                                  amf_ue_ngap_id=ui["amf_ue_ngap_id"],
                                  session=dict(s_nssai=sr["s_nssai"], ul_tnl=sr["ul_ng_u_tnl"], flow=sr["qos_flows"][0],
                                               ambr=sr.get("ambr")),
                                  ho_in=dict(source=m.src, ho_id=p["ho_id"]))
        self.setup_bearer(m.ue, XN, c["session"], lambda e1: self.reply(
            m, "HandoverRequestAcknowledge", ho_id=p["ho_id"],
            pdu_session_resources_admitted_list=[dict(
                pdu_session_id=1, dl_forwarding_up_tnl_information=e1["dl_forwarding_up_tnl_information"])],
            target_to_source_transparent_container="RRCReconfiguration (reconfigurationWithSync, RACH-ConfigDedicated)"),
            forwarding=True)

    def on_SNStatusTransfer(self, m):
        pass                                             # PDCP COUNTs taken over by the target CU-UP

    def path_switch(self, ue):
        c = self.ctx[ue]

        def acked(r):
            c["amf_ue_ngap_id"] = r.payload["amf_ue_ngap_id"]
            ho = c.pop("ho_in")
            self.send(ho["source"], "Xn-C", XN, "UEContextRelease", ue=ue, ho_id=ho["ho_id"],
                      cause="successful handover")

        self.request(self.amf, "N2", XN, "PathSwitchRequest", acked, ue=ue, ran_ue_ngap_id=c["ran_ue_ngap_id"],
                     source_amf_ue_ngap_id=c["amf_ue_ngap_id"], user_location_information=self.user_location(ue),
                     ue_security_capabilities="NEA0-2, NIA1-2", ho_id=c["ho_in"]["ho_id"],
                     pdu_session_resource_to_be_switched_dl_list=[dict(
                         pdu_session_id=1, transfer=dict(dl_ngu_up_tnl_information=c["ng_dl_up_tnl"],
                                                         qos_flow_accepted_list=[c["session"]["flow"]["qfi"]]))])

    # ----------------------------------------------------------- handover: source releases the UE
    def on_UEContextRelease(self, m):
        c = self.ctx.pop(m.ue)
        hid = m.payload.get("ho_id")
        self.request(c["du"], "F1-C", XN, "UEContextReleaseCommand", lambda r: None, ue=m.ue, ho_id=hid,
                     cause="handover completed")
        self.request(self.cu_up, "E1", XN, "BearerContextReleaseCommand", lambda r: None, ue=m.ue, ho_id=hid,
                     cause="handover completed")
