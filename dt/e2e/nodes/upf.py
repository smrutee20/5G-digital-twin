"""
UPF: user-plane anchor. PFCP sessions from the SMF (N4, TS 29.244) with PDR/FAR/QER rules,
GTP-U tunnels to the CU-UP (N3, TS 29.281) and IP to the data network (N6).
"""
from ..engine import Node


class UPF(Node):
    kind = "UPF"

    def __init__(self, name, net, spec, dn):
        super().__init__(name, net)
        self.spec, self.dn, self.n3_ip = spec, dn, spec["n3_ip"]
        net.ip_table[self.n3_ip] = name
        self.sess = {}                 # ue -> PFCP session state
        self.held = {}                 # DL packets buffered by FAR 2 (BUFF)
        self._teid = 0x9000 + 0x1000 * len([n for n in net.nodes.values() if n.kind == "UPF"])

    def on_PFCPAssociationSetupRequest(self, m):
        s = self.spec
        self.reply(m, "PFCPAssociationSetupResponse", node_id=self.name, cause="Request accepted",
                   up_function_features="FTUP (F-TEID allocation), UEIP",
                   ue_ip_address_pool_information=dict(ue_ip_address_pool_identity=s["ue_pool"],
                                                       network_instance=list(s["dnn"]), s_nssai_sst=list(s["sst"])),
                   served_tai=[f"001-01-{tac}" for tac in s["tai"]], max_sessions=s["max_sessions"])

    def on_PFCPSessionEstablishmentRequest(self, m):
        p = m.payload
        self._teid += 1
        teid = hex(self._teid)
        ue_ip = next(r["pdi"]["ue_ip_address"] for r in p["create_pdr"] if r["pdi"]["source_interface"] == "CORE")
        self.sess[m.ue] = dict(seid=p["cp_f_seid"], ul_teid=teid, ue_ip=ue_ip, qfi=p["create_qer"][0]["qfi"],
                               far2="BUFF", dl_teid=None, gnb=None)
        self.reply(m, "PFCPSessionEstablishmentResponse", cause="Request accepted", up_f_seid=hex(0x5000 + self._teid),
                   created_pdr=[dict(pdr_id=1, local_f_teid=dict(teid=teid, ipv4=self.n3_ip))])

    def on_PFCPSessionModificationRequest(self, m):
        s = self.sess[m.ue]
        far = m.payload["update_far"][0]
        ohc = far["forwarding_parameters"]["outer_header_creation"]
        if "pfcpsm_req_flags" in far["forwarding_parameters"] and s["gnb"]:    # path switch: close the old path
            self.send(s["gnb"], "N3", m.procedure, "EndMarker", ue=m.ue, teid=s["dl_teid"], ho_id=m.payload.get("ho_id"))
        s.update(far2=far["apply_action"], dl_teid=ohc["teid"], gnb=self.net.route(ohc["ipv4"]),
                 t_forw=self.sim.now)
        self.reply(m, "PFCPSessionModificationResponse", cause="Request accepted")
        for msg in self.held.pop(m.ue, []):
            msg.payload["_batch"].hold_until(self.sim.now, "core")      # buffered by FAR 2 until now
            self.forward_dl(msg)

    def on_G_PDU(self, m):             # uplink: PDR 1 (ACCESS, our F-TEID) -> FAR 1 -> N6
        s = self.sess[m.ue]
        assert m.payload["teid"] == s["ul_teid"], "GTP-U TEID does not match the PFCP session"
        self.send(self.dn, "N6", m.procedure, "IPPacket", ue=m.ue, bytes=m.payload["bytes"], direction="UL",
                  src_ip=s["ue_ip"], app=m.payload.get("app"))

    def on_IPPacket(self, m):          # downlink: PDR 2 (CORE, UE IP) -> FAR 2 (BUFF or FORW) + QER (QFI)
        m.payload["_batch"].hop(self.net.link_ms("N6"), "n6", self.net.proc["UPF"], "core")
        s = self.sess.get(m.ue)
        if s and s["far2"] == "FORW":
            self.forward_dl(m)
        else:
            self.held.setdefault(m.ue, []).append(m)

    def forward_dl(self, m):
        s = self.sess[m.ue]
        b = m.payload["_batch"]
        self.send(s["gnb"], "N3", m.procedure, "G-PDU", ue=m.ue, bytes=b.bytes, packets=len(b), direction="DL",
                  teid=s["dl_teid"], qfi=s["qfi"], dst_ip=s["ue_ip"], epoch=m.payload.get("epoch"), _batch=b)
