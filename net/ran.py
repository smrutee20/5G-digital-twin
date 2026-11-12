"""
The radio side: the phone (UE) and the base stations (one gNB per site A, B and C, each with 3 sectors).

The UE talks only to the gNB whose sector (cell) it is on (interface Uu). NAS messages for the AMF (N1) travel
inside RRC over Uu and inside NGAP over N2; the gNB forwards them without reading them.
"""
from net.sim import Element
import config as C


def nas_fields(msg):
    """The fields of a message, without the radio/transport headers (what gets forwarded)."""
    return {k: v for k, v in msg.items()
            if k not in ("src", "message", "nas", "flow", "c_rnti", "ran_ue_ngap_id", "amf_ue_ngap_id")}


class UE(Element):
    def __init__(self, net, supi, suci, imeisv):
        super().__init__("UE", net)
        self.supi, self.suci, self.imeisv = supi, suci, imeisv     # the SUPI never leaves the phone
        self.cell = self.gnb = None     # the sector (cell) the phone listens to, and that sector's gNB
        self.connected = False          # RRC connected, or idle
        self.c_rnti = self.s_tmsi = self.ip = None
        self.handover = False           # moving to a new gNB
        self.paged = False              # woken up by paging
        self.received = []              # downlink data that reached the phone

    def uu(self, message, note, **fields):
        if self.c_rnti:
            fields.setdefault("c_rnti", self.c_rnti)
        self.send(self.gnb, "Uu", message, note, **fields)

    # ------------------------------------------------ Flow 1: broadcast, random access, RRC setup
    def power_on(self, cell):
        self.move_to(cell)
        self.net.elements[self.gnb].broadcast(cell)

    def move_to(self, cell):
        """Listen to another sector: its gNB is the one of its site ("B225" -> "gNB-B")."""
        self.cell = self.net.serving = cell
        self.gnb = f"gNB-{cell[0]}"

    def on_SSB(self, msg):
        pass                            # time and frequency sync, and the cell's PCI

    def on_MIB(self, msg):
        pass                            # tells the phone where to find SIB1

    def on_SIB1(self, msg):
        self.uu("RandomAccessPreamble", "Msg1: the phone sends a random-access preamble to say 'I am here'")

    def on_RandomAccessResponse(self, msg):
        self.c_rnti = msg["c_rnti"]
        if self.handover:
            self.handover = False
            self.uu("RRCReconfigurationComplete", f"The phone tells {self.gnb} that it has arrived")
        elif self.paged:
            self.uu("RRCSetupRequest", "Msg3: the phone asks for a connection, giving part of its 5G-S-TMSI",
                    s_tmsi_part1=self.s_tmsi, cause="mt-Access (answering a page)")
        else:
            self.uu("RRCSetupRequest", "Msg3: the phone asks for an RRC connection",
                    ue_identity="random value", cause="mo-Signalling")

    def on_RRCSetup(self, msg):
        self.connected, self.net.ue_state = True, "RRC connected"
        if self.paged:
            self.uu("RRCSetupComplete", "Service Request with the 5G-S-TMSI: 'you paged me, I am back'",
                    nas="ServiceRequest", s_tmsi=self.s_tmsi, service_type="mobile terminated services")
            return
        self.net.flow = 2
        self.uu("RRCSetupComplete", "Registration Request with the SUCI (the SUPI stays hidden on the radio)",
                nas="RegistrationRequest", registration_type="initial", suci=self.suci, s_nssai=f"SST {C.SST}")

    # ------------------------------------------------ Flow 2 and 3: NAS from the AMF
    def on_DLInformationTransfer(self, msg):
        nas = msg["nas"]
        if nas == "AuthenticationRequest":
            self.uu("ULInformationTransfer", "The SIM computes RES* from RAND and its secret key: Authentication Response",
                    nas="AuthenticationResponse", res_star="RES*")
        elif nas == "SecurityModeCommand":
            self.uu("ULInformationTransfer", "Security on; only now does the phone send its IMEISV",
                    nas="SecurityModeComplete", imeisv=self.imeisv)
        elif nas == "RegistrationAccept":
            self.s_tmsi = msg["s_tmsi"]
            self.uu("ULInformationTransfer", "The phone confirms its new 5G-GUTI: Registration Complete",
                    nas="RegistrationComplete")
            self.net.flow = 3
            self.uu("ULInformationTransfer", "The phone asks for an internet connection: PDU Session Establishment Request",
                    nas="PDUSessionEstablishmentRequest", pdu_session_id=1, dnn=C.DNN, s_nssai=f"SST {C.SST}")

    def on_RRCReconfiguration(self, msg):
        if msg.get("target_cell"):                       # Flow 5: handover command
            self.move_to(msg["target_cell"])
            self.c_rnti, self.handover = None, True
            self.uu("RandomAccessPreamble", f"The phone switches to {self.gnb} (sector {self.cell}): random access")
            return
        if msg.get("nas") == "PDUSessionEstablishmentAccept":
            self.ip = msg["ue_ip"]
        if msg.get("nas") == "ServiceAccept":
            self.paged = False
        self.uu("RRCReconfigurationComplete", "The phone's data radio bearer is ready")

    # ------------------------------------------------ Flow 4: data
    def send_request(self):
        self.uu("PUSCH", "Uplink: the phone sends a request to a server on the internet (QFI 1)",
                from_ip=f"{self.ip}:40001", to_ip=f"{C.SERVER_IP}:443", bytes=400, qfi=C.QFI)

    def on_PDSCH(self, msg):
        self.received.append(msg)

    # ------------------------------------------------ Flow 5: handover is triggered by the twin's A3 rule
    def measurement_report(self, target_cell, serving_dbm, target_dbm):
        self.uu("MeasurementReport", f"Event A3: sector {target_cell} is {target_dbm - serving_dbm:.1f} dB stronger "
                f"than {self.cell}", event="A3", serving_cell=self.cell, serving_rsrp_dbm=serving_dbm,
                neighbour_cell=target_cell, neighbour_pci=C.pci(target_cell), neighbour_rsrp_dbm=target_dbm)

    # ------------------------------------------------ Flow 6: idle and paging
    def on_RRCRelease(self, msg):
        self.connected, self.c_rnti, self.net.ue_state = False, None, "RRC idle"
        self.net.forget("c_rnti")

    def on_Paging(self, msg):
        if msg["src"] != self.gnb or self.connected or msg["s_tmsi"] != self.s_tmsi:
            return                                     # the phone only listens to the gNB it camps on
        self.paged = True
        self.uu("RandomAccessPreamble", "The phone hears its 5G-S-TMSI in the page: random access")


class GNB(Element):
    def __init__(self, net, site, index):
        super().__init__(f"gNB-{site}", net)
        self.site, self.n3_ip = site, C.GNB_N3_IP[site]
        self._rnti, self._ngap, self._teid = 0x4600 + 0x100 * index, 100 * (index + 1), 0xB000 + 0x100 * index
        self.ctx = None                 # the phone's context while it is connected to this gNB
        self.last_data = None

    def to_ue(self, message, note, **fields):
        if self.ctx and self.ctx.get("c_rnti"):
            fields.setdefault("c_rnti", self.ctx["c_rnti"])
        self.send("UE", "Uu", message, note, **fields)

    def to_amf(self, message, note, **fields):
        self.send("AMF", "N2", message, note, ran_ue_ngap_id=self.ctx["ran_ue_ngap_id"],
                  amf_ue_ngap_id=self.ctx.get("amf_ue_ngap_id"), **fields)

    def new_c_rnti(self):
        self._rnti += 1
        return f"0x{self._rnti:04x}"

    def new_dl_teid(self):
        self._teid += 1
        self.ctx["dl_teid"] = f"0x{self._teid:08x}"
        return self.ctx["dl_teid"]

    # ------------------------------------------------ Flow 1
    def broadcast(self, cell):
        self.to_ue("SSB", f"Sector {cell} broadcasts its SSB (PSS + SSS): the phone syncs and learns the cell ID "
                   f"(PCI {C.pci(cell)})", cell=cell, pci=C.pci(cell))
        self.to_ue("MIB", f"Sector {cell} broadcasts the MIB: where to find SIB1", scs_khz=30)
        self.to_ue("SIB1", f"Sector {cell} broadcasts SIB1: network {C.MCC}-{C.MNC}, tracking area {C.TAC}",
                   plmn=f"{C.MCC}-{C.MNC}", tac=C.TAC, cell=cell)

    def on_RandomAccessPreamble(self, msg):
        if self.ctx is None:
            self.ctx = dict(c_rnti=self.new_c_rnti())
        self.to_ue("RandomAccessResponse", f"Msg2: {self.name} answers and gives the phone its C-RNTI",
                   c_rnti=self.ctx["c_rnti"], timing_advance=0)

    def on_RRCSetupRequest(self, msg):
        self.to_ue("RRCSetup", "Msg4: RRC Setup (signalling radio bearer SRB1)", srb="SRB1")

    def on_RRCSetupComplete(self, msg):
        self._ngap += 1
        self.ctx["ran_ue_ngap_id"] = self._ngap
        self.send("AMF", "N2", "InitialUEMessage",
                  f"{self.name} cannot read NAS: it passes it to the AMF with a new RAN UE NGAP ID",
                  nas=msg["nas"], ran_ue_ngap_id=self._ngap, tai=f"{C.MCC}-{C.MNC}-{C.TAC}", **nas_fields(msg))

    def on_ULInformationTransfer(self, msg):
        self.to_amf("UplinkNASTransport", f"{self.name} forwards the NAS message to the AMF",
                    nas=msg["nas"], **nas_fields(msg))

    # ------------------------------------------------ NGAP from the AMF
    def on_DownlinkNASTransport(self, msg):
        self.ctx["amf_ue_ngap_id"] = msg["amf_ue_ngap_id"]
        self.to_ue("DLInformationTransfer", f"{self.name} passes the AMF's NAS message to the phone",
                   nas=msg["nas"], **nas_fields(msg))

    def on_PDUSessionResourceSetupRequest(self, msg):
        self.ctx.update(ul_teid=msg["ul_teid"], qfi=msg["qfi"], waiting="pdu")
        self.new_dl_teid()
        self.to_ue("RRCReconfiguration", "Data radio bearer set up; inside: PDU Session Accept with the phone's IP",
                   nas="PDUSessionEstablishmentAccept", drb="DRB1", ue_ip=msg["ue_ip"], qfi=msg["qfi"],
                   five_qi=msg["five_qi"], pdu_session_id=msg["pdu_session_id"])

    def on_InitialContextSetupRequest(self, msg):         # after a Service Request
        self.ctx.update(amf_ue_ngap_id=msg["amf_ue_ngap_id"], ul_teid=msg["ul_teid"], qfi=msg["qfi"],
                        waiting="service")
        self.new_dl_teid()
        self.to_ue("RRCReconfiguration", "Data radio bearer set up again; inside: Service Accept",
                   nas="ServiceAccept", drb="DRB1", qfi=msg["qfi"])

    def on_RRCReconfigurationComplete(self, msg):
        waiting, self.ctx["waiting"] = self.ctx.get("waiting"), None
        tunnel = dict(dl_teid=self.ctx["dl_teid"], gnb_ip=self.n3_ip, pdu_session_id=1)
        if waiting == "pdu":
            self.to_amf("PDUSessionResourceSetupResponse", f"{self.name} gives the core its downlink TEID", **tunnel)
        elif waiting == "service":
            self.to_amf("InitialContextSetupResponse", f"{self.name} gives the core its new downlink TEID", **tunnel)
        elif waiting == "handover":
            self.to_amf("PathSwitchRequest", f"{self.name}: 'the phone is with me now, send its data to my TEID'",
                        tai=f"{C.MCC}-{C.MNC}-{C.TAC}", **tunnel)
        self.touch()

    # ------------------------------------------------ Flow 4: user data (GTP-U on N3)
    def on_PUSCH(self, msg):
        self.touch()
        self.send("UPF", "N3", "GTP_U", f"{self.name} puts the packet in the GTP-U tunnel to the UPF (uplink TEID)",
                  ul_teid=self.ctx["ul_teid"], qfi=self.ctx["qfi"], from_ip=msg["from_ip"], to_ip=msg["to_ip"],
                  bytes=msg["bytes"], direction="uplink")

    def on_GTP_U(self, msg):
        self.touch()
        self.to_ue("PDSCH", f"{self.name} finds the phone from the TEID and sends the packet over the air",
                   from_ip=msg["from_ip"], to_ip=msg["to_ip"], bytes=msg["bytes"], app=msg.get("app"))

    def on_EndMarker(self, msg):
        self.net.say(f"{self.name} got the End Marker: no more data will come on the old path")

    # ------------------------------------------------ Flow 5: handover over Xn
    def on_MeasurementReport(self, msg):
        c = self.ctx
        target = f"gNB-{msg['neighbour_cell'][0]}"
        self.send(target, "Xn", "HandoverRequest",
                  f"{self.name} asks {target} to take the phone (sector {msg['neighbour_cell']}), with its context",
                  target_cell=msg["neighbour_cell"], amf_ue_ngap_id=c["amf_ue_ngap_id"], ul_teid=c["ul_teid"], qfi=c["qfi"], five_qi=C.FIVE_QI,
                  pdu_session_id=1, ue_ambr="as subscribed")

    def on_HandoverRequest(self, msg):
        self._ngap += 1
        self.ctx = dict(c_rnti=self.new_c_rnti(), ran_ue_ngap_id=self._ngap, amf_ue_ngap_id=msg["amf_ue_ngap_id"],
                        ul_teid=msg["ul_teid"], qfi=msg["qfi"], waiting="handover", source=msg["src"])
        self.new_dl_teid()
        self.send(msg["src"], "Xn", "HandoverRequestAcknowledge",
                  f"{self.name} accepts and reserves a C-RNTI for the phone", target_cell=msg["target_cell"],
                  new_c_rnti=self.ctx["c_rnti"])

    def on_HandoverRequestAcknowledge(self, msg):
        self.to_ue("RRCReconfiguration", f"Handover command: 'go to sector {msg['target_cell']} of {msg['src']}'",
                   target_cell=msg["target_cell"], pci=C.pci(msg["target_cell"]), new_c_rnti=msg["new_c_rnti"])

    def on_PathSwitchRequestAcknowledge(self, msg):
        self.send(self.ctx["source"], "Xn", "UEContextRelease",
                  f"{self.name} tells the old gNB it can forget the phone")

    def on_UEContextRelease(self, msg):
        self.ctx = None

    # ------------------------------------------------ Flow 6: going idle, and paging
    def touch(self):
        """Any data restarts the inactivity timer."""
        self.last_data = t = self.net.now
        self.net.at(t + C.INACTIVITY_S * 1000, self.check_inactive, t)

    def check_inactive(self, t):
        if self.ctx is None or self.last_data != t or self.ctx.get("waiting"):
            return
        self.net.flow = 6
        self.to_amf("UEContextReleaseRequest", f"No data for {C.INACTIVITY_S:.0f} s: {self.name} asks to release the phone",
                    cause="user inactivity")

    def on_UEContextReleaseCommand(self, msg):
        self.to_ue("RRCRelease", "RRC Release: the phone goes idle and gives up its C-RNTI")
        self.to_amf("UEContextReleaseComplete", f"{self.name} has forgotten the phone")
        self.ctx = None

    def on_Paging(self, msg):
        self.send("UE", "Uu", "Paging", f"{self.name} pages the 5G-S-TMSI on its 3 sectors", s_tmsi=msg["s_tmsi"])
