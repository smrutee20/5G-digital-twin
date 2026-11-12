"""
SMF: PDU session establishment (TS 23.502 §4.3.2.2.1). UDM registration/subscription data, SM policy
(PCF), UPF selection (TS 23.501 §6.3.3), N4 PFCP session (TS 29.244) and the QoS flow (TS 23.501 §5.7).
"""
import ipaddress

from ..engine import Node
from ..qos import FIVE_QI, qos_rule, qos_profile

PDU = "PDU Session Establishment"


class SMF(Node):
    kind = "SMF"

    def __init__(self, name, net, upfs):
        super().__init__(name, net)
        self.upf_names = upfs
        self.upfs = {}                  # name -> capabilities learned at PFCP association + session count
        self.sessions = {}
        self._seid = 0

    def start(self):
        self.request("NRF", "SBI", "NF Registration", "Nnrf_NFManagement_NFRegister", lambda r: None,
                     nf_type=self.kind, nf_instance=self.name, services="nsmf-pdusession", dnn_list="internet, ims")
        for u in self.upf_names:
            self.request(u, "N4", "N4 Association Setup", "PFCPAssociationSetupRequest", self.associated,
                         node_id=self.name, cp_function_features="LOAD, OVRL")

    def associated(self, r):
        p = r.payload
        pool = p["ue_ip_address_pool_information"]
        self.upfs[r.src] = dict(dnn=pool["network_instance"], sst=pool["s_nssai_sst"], tai=p["served_tai"],
                                max_sessions=p["max_sessions"], sessions=0,
                                pool=ipaddress.ip_network(pool["ue_ip_address_pool_identity"]), next_ip=1)

    # ----------------------------------------------------------- UPF selection
    def select_upf(self, dnn, sst, tai):
        """Filter by DNN, S-NSSAI and free capacity; prefer a UPF serving the UE's TAI; then the least loaded."""
        evals, ok = [], []
        for name, u in sorted(self.upfs.items()):
            reasons = []
            if dnn not in u["dnn"]:
                reasons.append(f"DNN {dnn} not served")
            if sst not in u["sst"]:
                reasons.append(f"SST {sst} not served")
            if u["sessions"] >= u["max_sessions"]:
                reasons.append(f"full ({u['sessions']}/{u['max_sessions']} sessions)")
            local = tai in u["tai"]
            load = u["sessions"] / u["max_sessions"]
            evals.append(dict(upf=name, eligible=not reasons, local_to_tai=local, load=round(load, 3),
                              reasons=", ".join(reasons) or "ok"))
            if not reasons:
                ok.append((not local, load, name))
        if not ok:
            raise RuntimeError(f"SMF: no UPF for DNN {dnn}, SST {sst}")
        chosen = min(ok)[2]
        return chosen, dict(selected=chosen, rule="DNN + S-NSSAI + capacity, then TAI locality, then lowest load",
                            candidates=evals)

    # ----------------------------------------------------------- PDU session establishment
    def on_Nsmf_PDUSession_CreateSMContext(self, m):
        ue, amf, p = m.ue, m.src, m.payload
        supi, psi, dnn, tai = p["supi"], p["pdu_session_id"], p["dnn"], p["ue_location"]["tai"]
        sst = int(p["s_nssai"].split()[-1])
        s = self.sessions[ue] = dict(amf=amf, supi=supi, psi=psi, dnn=dnn, s_nssai=p["s_nssai"])

        def n1n2(r):                     # step 11: N1 (to the UE) + N2 (to NG-RAN) SM information
            pdr = r.payload["created_pdr"][0]["local_f_teid"]
            s["ul_tnl"] = dict(gtp_teid=pdr["teid"], transport_layer_address=pdr["ipv4"])
            f = s["flow"]
            self.request(amf, "SBI", PDU, "Namf_Communication_N1N2MessageTransfer", lambda x: None, ue=ue,
                         pdu_session_id=psi, s_nssai=s["s_nssai"],
                         n1_sm_msg="PDUSessionEstablishmentAccept",
                         n1_sm_container=dict(pdu_session_id=psi, selected_pdu_session_type="IPv4",
                                              selected_ssc_mode=1, authorized_qos_rules=[qos_rule(f)],
                                              session_ambr=s["ambr"], pdu_address=s["ue_ip"], s_nssai=s["s_nssai"],
                                              dnn=dnn, authorized_qos_flow_descriptions=[dict(qfi=f["qfi"],
                                                                                             five_qi=f["five_qi"])]),
                         n2_sm_info=dict(pdu_session_aggregate_maximum_bit_rate=s["ambr"],
                                         ul_ngu_up_tnl_information=s["ul_tnl"], pdu_session_type="IPv4",
                                         qos_flow_setup_request_list=[dict(**qos_profile(f),
                                                                           resource_type=f["resource_type"],
                                                                           priority_level=f["priority_level"])]))

        def n4(policy):                  # steps 8 + 10a: UPF selection, PFCP session with PDR/FAR/QER
            d = policy.payload["sess_rules"]["auth_def_qos"]
            s["flow"] = dict(qfi=1, five_qi=d["five_qi"], arp=d["arp"], **FIVE_QI[d["five_qi"]])
            s["ambr"] = policy.payload["sess_rules"]["auth_sess_ambr"]
            upf, decision = self.select_upf(dnn, sst, tai)
            u = self.upfs[upf]
            u["sessions"] += 1
            s["upf"], s["ue_ip"] = upf, str(u["pool"][u["next_ip"]])
            u["next_ip"] += 1
            self._seid += 1
            s["seid"] = self._seid
            f = s["flow"]
            self.request(upf, "N4", PDU, "PFCPSessionEstablishmentRequest", n1n2, ue=ue,
                         node_id=self.name, cp_f_seid=hex(s["seid"]), upf_selection=decision,
                         create_pdr=[
                             dict(pdr_id=1, precedence=255, pdi=dict(source_interface="ACCESS", f_teid="CHOOSE",
                                                                    network_instance=dnn, qfi=f["qfi"]),
                                  outer_header_removal="GTP-U/UDP/IPv4", far_id=1, qer_id=1),
                             dict(pdr_id=2, precedence=255, pdi=dict(source_interface="CORE", network_instance=dnn,
                                                                    ue_ip_address=s["ue_ip"]),
                                  far_id=2, qer_id=1)],
                         create_far=[dict(far_id=1, apply_action="FORW", destination_interface="CORE",
                                          network_instance=dnn),
                                     dict(far_id=2, apply_action="BUFF", note="until the AN tunnel is known")],
                         create_qer=[dict(qer_id=1, qfi=f["qfi"], gate_status="OPEN/OPEN",
                                          mbr=s["ambr"], five_qi=f["five_qi"])])

        def policy(_):                   # step 7: PCF selection + SM policy association
            self.discover("PCF", PDU, lambda pcf: self.request(
                pcf, "SBI", PDU, "Npcf_SMPolicyControl_Create", n4, ue=ue, supi=supi, pdu_session_id=psi,
                dnn=dnn, s_nssai=s["s_nssai"], rat_type="NR"), ue=ue)

        def created(_):                  # step 5: Create SM Context Response
            self.reply(m, "Nsmf_PDUSession_CreateSMContext_Response", status="201 Created",
                       sm_context_ref=f"smctx-{supi}-{psi}")
            policy(None)

        def subscribe(_):
            self.request(self.nf_cache["UDM"], "SBI", PDU, "Nudm_SDM_Subscribe", created, ue=ue, supi=supi,
                         monitored_resources="sm-data")

        def sm_data(_):
            self.request(self.nf_cache["UDM"], "SBI", PDU, "Nudm_SDM_Get", subscribe, ue=ue, supi=supi,
                         dataset_names="sm-data", dnn=dnn, s_nssai=s["s_nssai"])

        # step 4: UDM selection, UECM registration (SMF serves this session), session subscription data
        self.discover("UDM", PDU, lambda udm: self.request(
            udm, "SBI", PDU, "Nudm_UECM_Registration", sm_data, ue=ue, supi=supi, smf_instance_id=self.name,
            pdu_session_id=psi, dnn=dnn, s_nssai=s["s_nssai"]), ue=ue)

    def on_Nsmf_PDUSession_UpdateSMContext(self, m):
        s = self.sessions[m.ue]
        if m.payload.get("up_cnx_state") == "ACTIVATING":      # Service Request: give the AMF the N2 SM info
            f = s["flow"]
            self.reply(m, "Nsmf_PDUSession_UpdateSMContext_Response", status="200 OK", s_nssai=s["s_nssai"],
                       n2_sm_info=dict(pdu_session_aggregate_maximum_bit_rate=s["ambr"],
                                       ul_ngu_up_tnl_information=s["ul_tnl"], pdu_session_type="IPv4",
                                       qos_flow_setup_request_list=[dict(**qos_profile(f), resource_type=f["resource_type"],
                                                                         priority_level=f["priority_level"])]))
            return
        path_switch = m.payload.get("n2_sm_info_type") == "PATH_SWITCH_REQ"
        an = m.payload["n2_sm_info"]["dl_qos_flow_per_tnl_information"]["up_transport_layer_information"]
        s["dl_tnl"] = an
        # step 16a: N4 Session Modification -- FAR 2 from BUFF to FORW with GTP-U outer header to NG-RAN
        self.request(s["upf"], "N4", m.procedure, "PFCPSessionModificationRequest",
                     lambda r: self.reply(m, "Nsmf_PDUSession_UpdateSMContext_Response", status="200 OK",
                                          up_cnx_state="ACTIVATED"),
                     ue=m.ue, cp_f_seid=hex(s["seid"]), ho_id=m.payload.get("ho_id"),
                     update_far=[dict(far_id=2, apply_action="FORW", forwarding_parameters=dict(
                         destination_interface="ACCESS", network_instance=s["dnn"],
                         outer_header_creation=dict(description="GTP-U/UDP/IPv4", teid=an["gtp_teid"],
                                                    ipv4=an["transport_layer_address"]),
                         **({"pfcpsm_req_flags": "SNDEM (send end marker)"} if path_switch else {})))])
