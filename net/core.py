"""
The 5G core: AMF, AUSF, UDM (with its SIDF), NSSF, SMF, UPF, and a server on the internet.

Interfaces: N2 gNB-AMF, N11 AMF-SMF, N4 SMF-UPF, N3 gNB-UPF, N6 UPF-internet, and the service-based
interface (SBI, HTTP) between AMF, AUSF, UDM and NSSF. Authentication values (RAND, AUTN, RES*) are
placeholders: the order of the messages is modelled, not the cryptography.
"""
from net.sim import Element
from net.ids import deconceal, guti, s_tmsi
import config as C

TAI = f"{C.MCC}-{C.MNC}-{C.TAC}"


class AMF(Element):
    """Access and mobility: registration, the phone's identities, paging. Relays session requests to the SMF."""

    def __init__(self, net, gnbs):
        super().__init__("AMF", net)
        self.gnbs = gnbs                    # gNB name -> its tracking area code
        self.ue = {}                        # what the AMF knows about the phone
        self._ngap = 0

    def to_gnb(self, message, note, **fields):
        self.send(self.ue["gnb"], "N2", message, note, amf_ue_ngap_id=self.ue["amf_ue_ngap_id"],
                  ran_ue_ngap_id=self.ue["ran_ue_ngap_id"], **fields)

    def new_ngap_id(self, msg):
        self._ngap += 1
        self.ue.update(gnb=msg["src"], ran_ue_ngap_id=msg["ran_ue_ngap_id"], amf_ue_ngap_id=self._ngap)

    def to_smf(self, message, note, **fields):
        self.send("SMF", "N11", message, note, pdu_session_id=1, **fields)

    # ------------------------------------------------ Flow 2: registration
    def on_InitialUEMessage(self, msg):
        self.new_ngap_id(msg)
        if msg["nas"] == "ServiceRequest":                  # Flow 6: a paged phone is back
            assert msg["s_tmsi"] == self.ue["s_tmsi"], "unknown 5G-S-TMSI"
            self.ue["connected"] = True
            self.to_smf("Nsmf_PDUSession_UpdateSMContext", "AMF found the phone by its 5G-S-TMSI; asks the SMF to wake its session",
                        up_cnx_state="ACTIVATING", reason="service request")
            return
        self.ue.update(suci=msg["suci"], requested=msg["s_nssai"], connected=True)
        self.send("AUSF", "SBI", "Nausf_UEAuthentication_Authenticate", "AMF asks the AUSF: 'who is this SUCI?'",
                  suci=msg["suci"], serving_network=f"5G:mnc0{C.MNC}.mcc{C.MCC}.3gppnetwork.org")

    def on_Nausf_UEAuthentication_Authenticate_Response(self, msg):
        self.ue.update(supi=msg["supi"], hxres_star=msg["hxres_star"])
        self.to_gnb("DownlinkNASTransport", "Authentication Request (RAND, AUTN) to the phone, with the AMF UE NGAP ID",
                    nas="AuthenticationRequest", ngksi=1, rand=msg["rand"], autn=msg["autn"])

    def on_UplinkNASTransport(self, msg):
        nas = msg["nas"]
        if nas == "AuthenticationResponse":
            assert msg["res_star"] == self.ue["hxres_star"], "authentication failed"
            self.to_gnb("DownlinkNASTransport", "RES* matches: Security Mode Command (ciphering, integrity, send IMEISV)",
                        nas="SecurityModeCommand", ngksi=1, ciphering="5G-EA0", integrity="5G-IA2",
                        imeisv_request=True)
        elif nas == "SecurityModeComplete":
            self.ue["imeisv"] = msg["imeisv"]
            self.send("NSSF", "SBI", "Nnssf_NSSelection_Get", "AMF asks the NSSF which slice the phone may use",
                      requested_nssai=self.ue["requested"], tai=TAI)
        elif nas == "RegistrationComplete":
            self.ue["registered"] = True
        elif nas == "PDUSessionEstablishmentRequest":       # Flow 3
            self.to_smf("Nsmf_PDUSession_CreateSMContext", "AMF passes the session request to the SMF over N11",
                        supi=self.ue["supi"], dnn=msg["dnn"], s_nssai=msg["s_nssai"], tai=TAI)

    def on_Nnssf_NSSelection_Get_Response(self, msg):
        g = C.GUAMI
        new = guti(C.MCC, C.MNC, g["amf_region_id"], g["amf_set_id"], g["amf_pointer"], C.FIRST_5G_TMSI)
        self.ue.update(guti=new["value"], s_tmsi=s_tmsi(new["value"]), allowed=msg["allowed_nssai"], tai_list=[TAI])
        self.to_gnb("DownlinkNASTransport", "Registration Accept: a 5G-GUTI to use instead of the SUPI, the TAI list and the allowed slice",
                    nas="RegistrationAccept", guti=self.ue["guti"], s_tmsi=self.ue["s_tmsi"],
                    tai_list=self.ue["tai_list"], s_nssai=msg["allowed_nssai"])

    # ------------------------------------------------ Flow 3: PDU session (the SMF answers over N11)
    def on_Nsmf_PDUSession_CreateSMContext_Response(self, msg):
        pass                                                # "201 Created": the SMF has started

    def on_Namf_Communication_N1N2MessageTransfer(self, msg):
        if not self.ue["connected"]:                        # Flow 6: the phone is idle -> page it
            self.send("SMF", "N11", "Namf_Communication_N1N2MessageTransfer_Response",
                      "AMF: 'the phone is idle, I will page it' (202 Accepted)", status="202 Accepted")
            for gnb, tac in self.gnbs.items():
                if f"{C.MCC}-{C.MNC}-{tac}" in self.ue["tai_list"]:
                    self.send(gnb, "N2", "Paging", f"AMF pages the phone's 5G-S-TMSI through {gnb} (in its TAI list)",
                              s_tmsi=self.ue["s_tmsi"], tai_list=self.ue["tai_list"])
            return
        self.send("SMF", "N11", "Namf_Communication_N1N2MessageTransfer_Response", "AMF: 'OK' (200)", status="200 OK")
        self.to_gnb("PDUSessionResourceSetupRequest", "AMF tells the gNB the UPF's tunnel (uplink TEID) and the QoS; NAS inside for the phone",
                    nas="PDUSessionEstablishmentAccept", **{k: msg[k] for k in
                                                            ("pdu_session_id", "ul_teid", "upf_ip", "qfi", "five_qi", "ue_ip", "s_nssai")})

    def on_PDUSessionResourceSetupResponse(self, msg):
        self.to_smf("Nsmf_PDUSession_UpdateSMContext", "AMF passes the gNB's downlink TEID to the SMF",
                    dl_teid=msg["dl_teid"], gnb_ip=msg["gnb_ip"], reason="session setup")

    def on_Nsmf_PDUSession_UpdateSMContext_Response(self, msg):
        reason = msg["reason"]
        if reason == "service request":                     # Flow 6: set the phone's context up again
            self.to_gnb("InitialContextSetupRequest", "AMF sends the session (uplink TEID, QoS) to the gNB; inside: Service Accept",
                        nas="ServiceAccept", pdu_session_id=1, ul_teid=msg["ul_teid"], qfi=msg["qfi"],
                        five_qi=msg["five_qi"])
        elif reason == "path switch":                       # Flow 5
            self.to_gnb("PathSwitchRequestAcknowledge", "AMF confirms the path switch to the new gNB")
        elif reason == "release":                           # going idle
            self.to_gnb("UEContextReleaseCommand", "AMF tells the gNB to release the phone", cause="user inactivity")

    def on_InitialContextSetupResponse(self, msg):
        self.to_smf("Nsmf_PDUSession_UpdateSMContext", "AMF passes the gNB's new downlink TEID to the SMF",
                    dl_teid=msg["dl_teid"], gnb_ip=msg["gnb_ip"], reason="service accepted")

    # ------------------------------------------------ Flow 5: handover
    def on_PathSwitchRequest(self, msg):
        self.ue.update(gnb=msg["src"], ran_ue_ngap_id=msg["ran_ue_ngap_id"])
        self.to_smf("Nsmf_PDUSession_UpdateSMContext", "AMF asks the SMF to switch the downlink to the new gNB's TEID",
                    dl_teid=msg["dl_teid"], gnb_ip=msg["gnb_ip"], reason="path switch")

    # ------------------------------------------------ Flow 6: going idle
    def on_UEContextReleaseRequest(self, msg):
        self.to_smf("Nsmf_PDUSession_UpdateSMContext", "AMF asks the SMF to pause the session (the UPF will buffer)",
                    up_cnx_state="DEACTIVATED", reason="release")

    def on_UEContextReleaseComplete(self, msg):
        self.ue["connected"] = False
        self.net.forget("ran_ue_ngap_id", "amf_ue_ngap_id", "dl_teid")
        self.net.say("The phone is idle: no C-RNTI, no NGAP IDs, no downlink tunnel. It keeps its 5G-GUTI, IP and session")


class AUSF(Element):
    """Authentication server: asks the UDM for the subscriber and an authentication vector."""

    def on_Nausf_UEAuthentication_Authenticate(self, msg):
        self.send("UDM", "SBI", "Nudm_UEAuthentication_Get", "AUSF asks the UDM for this subscriber", suci=msg["suci"])

    def on_Nudm_UEAuthentication_Get_Response(self, msg):
        self.send("AMF", "SBI", "Nausf_UEAuthentication_Authenticate_Response",
                  "AUSF returns the challenge (RAND, AUTN), the expected answer and the SUPI",
                  supi=msg["supi"], rand=msg["rand"], autn=msg["autn"], hxres_star="RES*")


class UDM(Element):
    """Subscriber records. Its SIDF turns the SUCI back into the SUPI."""

    def __init__(self, net, subscribers):
        super().__init__("UDM", net)
        self.subscribers = subscribers

    def on_Nudm_UEAuthentication_Get(self, msg):
        self.send("SIDF", "internal", "DeconcealSUCI", "UDM hands the SUCI to its SIDF", suci=msg["suci"])

    def on_DeconcealSUCI_Response(self, msg):
        assert msg["supi"] in self.subscribers, "not a subscriber"
        self.send("AUSF", "SBI", "Nudm_UEAuthentication_Get_Response",
                  "UDM finds the subscriber and makes an authentication vector (RAND, AUTN, XRES*)",
                  supi=msg["supi"], rand="RAND", autn="AUTN", xres_star="RES*")


class SIDF(Element):
    """Inside the UDM: SUCI -> SUPI. Null scheme: the MSIN in the SUCI is not encrypted."""

    def on_DeconcealSUCI(self, msg):
        self.send("UDM", "internal", "DeconcealSUCI_Response", "SIDF: SUCI -> SUPI (null scheme: read the MSIN as it is)",
                  supi=deconceal(msg["suci"]), scheme="null (0)")


class NSSF(Element):
    """Slice selection: which S-NSSAI the phone may use."""

    def on_Nnssf_NSSelection_Get(self, msg):
        assert msg["requested_nssai"] == f"SST {C.SST}"
        self.send("AMF", "SBI", "Nnssf_NSSelection_Get_Response", f"NSSF allows slice SST {C.SST} (eMBB)",
                  allowed_nssai=msg["requested_nssai"])


class SMF(Element):
    """Session management: gives the phone an IP, sets the QoS and programs the UPF over N4 (PFCP)."""

    def __init__(self, net):
        super().__init__("SMF", net)
        self.s = {}

    def on_Nsmf_PDUSession_CreateSMContext(self, msg):
        self.send("AMF", "N11", "Nsmf_PDUSession_CreateSMContext_Response", "SMF: session context created (201)",
                  status="201 Created")
        self.s.update(ue_ip=C.UE_IP, s_nssai=msg["s_nssai"], seid="0x1")
        self.send("UPF", "N4", "PFCPSessionEstablishmentRequest",
                  "SMF picks the UPF and gives the phone an IP; PFCP sets the rules (PDRs) for this session",
                  seid="0x1", ue_ip=C.UE_IP, qfi=C.QFI, five_qi=C.FIVE_QI,
                  rules="uplink: tunnel -> N6 with NAT; downlink: buffer until the gNB's TEID is known")

    def on_PFCPSessionEstablishmentResponse(self, msg):
        self.s["ul_teid"] = msg["ul_teid"]
        self.send("AMF", "N11", "Namf_Communication_N1N2MessageTransfer",
                  "SMF sends the PDU Session Accept (IP, QFI 1, 5QI 9) for the phone and the uplink TEID for the gNB",
                  pdu_session_id=1, ue_ip=C.UE_IP, qfi=C.QFI, five_qi=C.FIVE_QI, s_nssai=self.s["s_nssai"],
                  ul_teid=msg["ul_teid"], upf_ip=C.UPF_N3_IP)

    def on_Namf_Communication_N1N2MessageTransfer_Response(self, msg):
        pass

    def on_Nsmf_PDUSession_UpdateSMContext(self, msg):
        self.s["reason"] = reason = msg["reason"]
        if reason == "service request":                     # nothing to change at the UPF yet
            self.send("AMF", "N11", "Nsmf_PDUSession_UpdateSMContext_Response",
                      "SMF returns the session: uplink TEID and QoS", reason=reason, pdu_session_id=1,
                      ul_teid=self.s["ul_teid"], qfi=C.QFI, five_qi=C.FIVE_QI)
        elif reason == "release":
            self.send("UPF", "N4", "PFCPSessionModificationRequest", "SMF tells the UPF: buffer downlink data for this phone",
                      seid="0x1", downlink="BUFFER and report")
        else:
            self.send("UPF", "N4", "PFCPSessionModificationRequest",
                      f"SMF tells the UPF: send downlink data to the gNB's TEID {msg['dl_teid']}",
                      seid="0x1", downlink="FORWARD", dl_teid=msg["dl_teid"], gnb_ip=msg["gnb_ip"])

    def on_PFCPSessionModificationResponse(self, msg):
        self.send("AMF", "N11", "Nsmf_PDUSession_UpdateSMContext_Response", "SMF: the UPF is updated",
                  reason=self.s["reason"])

    def on_PFCPSessionReportRequest(self, msg):             # Flow 6: data waiting at the UPF
        self.send("UPF", "N4", "PFCPSessionReportResponse", "SMF acknowledges the report", seid="0x1")
        self.send("AMF", "N11", "Namf_Communication_N1N2MessageTransfer",
                  "SMF asks the AMF to reach the phone: data is waiting", pdu_session_id=1)


class UPF(Element):
    """User plane: GTP-U tunnels to the gNB (N3), NAT to the internet (N6), buffering while the phone is idle."""

    def __init__(self, net):
        super().__init__("UPF", net)
        self.dl_teid = self.gnb = None
        self.buffer = []
        self.reported = False
        self.nat = {}                       # public port -> private ip:port

    def on_PFCPSessionEstablishmentRequest(self, msg):
        self.send("SMF", "N4", "PFCPSessionEstablishmentResponse", "UPF allocates the uplink TEID of the tunnel",
                  seid="0x1", ul_teid="0x00000a01")

    def on_PFCPSessionModificationRequest(self, msg):
        old = self.gnb
        if msg["downlink"] == "FORWARD":
            gnb_of_ip = {ip: f"gNB-{tower}" for tower, ip in C.GNB_N3_IP.items()}
            self.dl_teid, self.gnb = msg["dl_teid"], gnb_of_ip[msg["gnb_ip"]]
            if old and old != self.gnb:     # Flow 5: path switch
                self.send(old, "N3", "EndMarker", f"Path switch at the UPF: End Marker on the old tunnel to {old}")
        else:
            self.dl_teid = self.gnb = None
        self.send("SMF", "N4", "PFCPSessionModificationResponse", "UPF: rules updated", seid="0x1")
        if self.gnb:                        # deliver anything buffered
            self.reported = False
            for packet in self.buffer:
                self.to_gnb(packet, "UPF delivers the buffered packet to the gNB")
            self.buffer = []

    def on_PFCPSessionReportResponse(self, msg):
        pass

    def to_gnb(self, packet, note):
        self.send(self.gnb, "N3", "GTP_U", note, dl_teid=self.dl_teid, qfi=C.QFI, direction="downlink", **packet)

    def on_GTP_U(self, msg):                # uplink
        private = msg["from_ip"]
        self.nat["50001"] = private
        public = f"{C.UPF_PUBLIC_IP}:50001"
        self.send("Internet", "N6", "IPPacket", f"UPF removes the tunnel and translates (NAT) {private} -> {public}",
                  from_ip=public, to_ip=msg["to_ip"], bytes=msg["bytes"], nat=f"{private} <-> {public}")

    def on_IPPacket(self, msg):             # downlink
        private = self.nat[msg["to_ip"].split(":")[1]]
        packet = dict(from_ip=msg["from_ip"], to_ip=private, bytes=msg["bytes"], app=msg.get("app"))
        if self.gnb:
            self.to_gnb(packet, f"UPF translates back (NAT) to {private} and tunnels it to {self.gnb}")
            return
        self.buffer.append(packet)
        self.net.say("The phone is idle: the UPF buffers the packet")
        if not self.reported:
            self.reported = True
            self.send("SMF", "N4", "PFCPSessionReportRequest", "UPF tells the SMF: downlink data is waiting",
                      seid="0x1", report="downlink data")


class Internet(Element):
    """A server on the internet (N6). Answers requests; can also send a message on its own (a chat message)."""

    def on_IPPacket(self, msg):
        self.send("UPF", "N6", "IPPacket", "The server answers (downlink)", from_ip=msg["to_ip"], to_ip=msg["from_ip"], bytes=1400,
                  app="response")

    def push(self, public_addr):
        self.send("UPF", "N6", "IPPacket", "A chat message for the phone arrives from the internet",
                  from_ip=f"{C.SERVER_IP}:443", to_ip=public_addr, bytes=1000, app="chat message")
