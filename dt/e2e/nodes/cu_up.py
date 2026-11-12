"""
CU-UP (one per gNB): PDCP (user plane) and SDAP (QFI -> DRB). Terminates E1, F1-U, N3 and Xn-U.
Each PDU session has an N3 tunnel (UL TEID at the UPF, DL TEID here) and each DRB an F1-U tunnel.
During an Xn handover the source CU-UP forwards downlink data (including what the DU gives back) to
the target CU-UP over Xn-U until the UPF's End Marker arrives (TS 38.300 §9.2.3.2.3).
"""
from ..engine import Node


class CUUP(Node):
    kind = "CU-UP"

    def __init__(self, name, net, cu_cp, n3_ip, f1u_ip):
        super().__init__(name, net)
        self.cu_cp, self.n3_ip, self.f1u_ip = cu_cp, n3_ip, f1u_ip
        net.ip_table[n3_ip] = net.ip_table[f1u_ip] = name
        self.bearer = {}               # ue -> tunnel endpoints, QFI, forwarding state, held data
        self._teid = 0x1000 + 0x100 * len([n for n in net.nodes.values() if n.kind == "CU-UP"])
        self.dl_delivered = {}

    def start(self):
        self.request(self.cu_cp, "E1", "E1 Setup", "GNBCUUPE1SetupRequest", lambda r: None,
                     gnb_cu_up_id=self.name, supported_plmns="001-01, SST 1")

    def new_teid(self):
        self._teid += 1
        return hex(self._teid)

    # ----------------------------------------------------------- E1 (bearer contexts)
    def on_BearerContextSetupRequest(self, m):
        s = m.payload["pdu_session_resource_to_setup_list"][0]
        dl_n3, ul_f1u = self.new_teid(), self.new_teid()
        ul = s["ng_ul_up_tnl_information"]
        b = self.bearer[m.ue] = dict(du=m.payload["du"], upf=self.net.route(ul["transport_layer_address"]),
                                     qfi=s["qos_flow_information_to_be_setup"][0]["qfi"], n3_ul=ul["gtp_teid"],
                                     n3_dl=dl_n3, f1u_ul=ul_f1u, f1u_dl=None, forward=None, held=[])
        resp = dict(pdu_session_id=s["pdu_session_id"],
                    ng_dl_up_tnl_information=dict(gtp_teid=dl_n3, transport_layer_address=self.n3_ip),
                    drb_setup_list=[dict(drb_id=1, ul_up_tnl_information=dict(gtp_teid=ul_f1u,
                                                                              transport_layer_address=self.f1u_ip),
                                         flow_setup_list=[b["qfi"]])])
        if s.get("dl_forwarding") == "proposed":          # handover target: tunnel for forwarded data
            b["xn_dl"] = self.new_teid()
            resp["dl_forwarding_up_tnl_information"] = dict(gtp_teid=b["xn_dl"], transport_layer_address=self.n3_ip)
        self.reply(m, "BearerContextSetupResponse", pdu_session_resource_setup_list=[resp])

    def on_BearerContextModificationRequest(self, m):
        b, p = self.bearer[m.ue], m.payload
        if "dl_up_parameters" in p:                          # the DU's F1-U endpoint is known: release held data
            dl = p["dl_up_parameters"]
            b.update(f1u_dl=dl["gtp_teid"], du=self.net.route(dl["transport_layer_address"]))
        if "data_forwarding_information" in p:               # handover source: forward DL to the target gNB
            f = p["data_forwarding_information"]
            b["forward"] = dict(peer=self.net.route(f["transport_layer_address"]), teid=f["gtp_teid"])
        self.reply(m, "BearerContextModificationResponse")
        held, b["held"] = b["held"], []
        for msg in held:
            self.downlink(msg)

    def on_BearerContextReleaseCommand(self, m):
        self.bearer.pop(m.ue, None)
        self.reply(m, "BearerContextReleaseComplete", cause="successful handover")

    # ----------------------------------------------------------- user plane
    def on_G_PDU(self, m):
        b = self.bearer.get(m.ue)
        if b is None:
            return
        if m.interface == "F1-U":                            # uplink: PDCP -> SDAP (QFI) -> GTP-U to the UPF
            self.send(b["upf"], "N3", m.procedure, "G-PDU", ue=m.ue, bytes=m.payload["bytes"], direction="UL",
                      teid=b["n3_ul"], qfi=b["qfi"], app=m.payload.get("app"))
            return
        comp = ("backhaul", self.net.link_ms("N3")) if m.interface == "N3" else ("xn", self.net.link_ms("Xn-U"))
        m.payload["_batch"].hop(comp[1], comp[0], self.net.proc["CU-UP"], "ran_proc")
        self.downlink(m)

    def downlink(self, m):
        b, pk = self.bearer[m.ue], m.payload["_batch"]
        if b["forward"]:                                     # source gNB during a handover
            self.send(b["forward"]["peer"], "Xn-U", "Handover (Xn)", "G-PDU", ue=m.ue, bytes=pk.bytes,
                      packets=len(pk), direction="DL", teid=b["forward"]["teid"], forwarded=True, _batch=pk)
        elif b["f1u_dl"]:
            self.send(b["du"], "F1-U", m.procedure, "G-PDU", ue=m.ue, bytes=pk.bytes, packets=len(pk),
                      direction="DL", teid=b["f1u_dl"], drb=1, epoch=m.payload.get("epoch"), _batch=pk)
        else:
            b["held"].append(m)

    def on_EndMarker(self, m):                               # last packet on the old path
        b = self.bearer.get(m.ue)
        if b and b["forward"]:
            self.send(b["forward"]["peer"], "Xn-U", "Handover (Xn)", "EndMarker", ue=m.ue, teid=b["forward"]["teid"],
                      ho_id=m.payload.get("ho_id"))

    def on_DLDataDeliveryStatus(self, m):
        self.dl_delivered[m.ue] = self.dl_delivered.get(m.ue, 0) + m.payload["delivered_bytes"]
        if "_batch" in m.payload and m.ue in self.bearer:    # data the DU gave back at a handover command
            m.payload["_batch"].hop(self.net.link_ms("F1-U"), "midhaul", self.net.proc["CU-UP"], "ran_proc")
            self.downlink(m)
