"""
UE: random access, RRC (TS 38.331), NAS 5GMM/5GSM (TS 24.501) and a downlink application.

NAS naming: `nas` is the 5GMM message; a 5GSM message (e.g. PDU Session Establishment Request) is
carried inside UL/DL NAS TRANSPORT and logged as `nas_sm`.
"""
import zlib

from ..engine import Node

ACCESS, REG, PDU, UL = "Initial Access", "Registration", "PDU Session Establishment", "User Plane UL"
SR = "Service Request"


class UE(Node):
    kind = "UE"

    def __init__(self, name, net, idx, ru, supi):
        super().__init__(name, net)
        self.idx, self.ru, self.supi = idx, ru, supi
        # SUCI: SUPI concealed with the home network public key (ECIES profile A); only the MSIN part is hidden
        self.suci = f"suci-0-001-01-0000-1-1-{zlib.crc32(supi.encode()) % 10**10:010d}"
        self.rrc_state, self.mm_state, self.session = "RRC_IDLE", "DEREGISTERED", None
        self.t = {}
        self.rx_bytes = 0
        self.rx = []
        self.guti = self.ue_ip = self.qos_rules = None
        self.ho = None                   # handover in progress: dict(target, procedure, ho_id, t_cmd)
        self.events = []                 # (t_ms, event, detail) for KPIs: handovers, RLF, re-attach
        self.app = True                  # runs the downlink application after the PDU session
        self.ho_processing_ms, self.prach_period_ms = 0.0, 0.0   # set by the network (mobility settings)

    def uu(self, procedure, message, **payload):
        self.send(self.ru, "Uu", procedure, message, ue=self.name, **payload)

    def ul_nas(self, procedure, nas, **payload):
        self.uu(procedure, "ULInformationTransfer", channel="PUSCH", nas=nas, **payload)

    # ----------------------------------------------------------- initial access (4-step RACH)
    def power_on(self):
        self.t["power_on"] = self.sim.now
        self.uu(ACCESS, "RandomAccessPreamble", channel="PRACH", msg="Msg1")

    def on_RandomAccessResponse(self, m):
        self.c_rnti = m.payload["c_rnti"]
        if self.ho:                      # handover: RACH on the target cell done -> RRC Reconfiguration Complete
            ho, self.ho = self.ho, None
            self.uu(ho["procedure"], "RRCReconfigurationComplete", channel="PUSCH", ho_id=ho["ho_id"])
            self.events.append((self.sim.now, "handover complete", dict(target=self.ru, ho_id=ho["ho_id"],
                                                                         interruption_ms=self.sim.now - ho["t_cmd"])))
            return
        if self.mm_state == "REGISTERED":    # coming back after a radio link failure
            self.uu(SR, "RRCSetupRequest", channel="PUSCH", msg="Msg3", ue_identity="5G-S-TMSI",
                    establishment_cause="mo-Data")
            return
        self.uu(ACCESS, "RRCSetupRequest", channel="PUSCH", msg="Msg3", ue_identity="random value",
                establishment_cause="mo-Signalling")

    def on_RRCSetup(self, m):
        self.rrc_state = "RRC_CONNECTED"
        if self.mm_state == "REGISTERED":    # Service Request: resume the PDU session through this gNB
            self.uu(SR, "RRCSetupComplete", channel="PUSCH", selected_plmn="001-01", nas="ServiceRequest",
                    ngksi=1, s_tmsi=self.guti, service_type="data", uplink_data_status="PSI 1",
                    pdu_session_status="PSI 1")
            return
        self.t["rrc_connected"] = self.sim.now
        self.uu(REG, "RRCSetupComplete", channel="PUSCH", selected_plmn="001-01", nas="RegistrationRequest",
                registration_type="initial registration", ngksi="no key available", mobile_identity=self.suci,
                ue_security_capability="NEA0-2, NIA1-2", requested_nssai="SST 1")

    # ----------------------------------------------------------- 5GMM in DL RRC messages
    def on_DLInformationTransfer(self, m):
        nas = m.payload["nas"]
        if nas == "AuthenticationRequest":
            # USIM: verify AUTN (network authentication), compute RES*
            self.ul_nas(REG, "AuthenticationResponse", authentication_response_parameter="RES*")
        elif nas == "SecurityModeCommand":
            # NAS security on (integrity + ciphering with the selected algorithms)
            self.ul_nas(REG, "SecurityModeComplete", imeisv="IMEISV",
                        nas_message_container="RegistrationRequest (complete, ciphered)")
        else:
            raise RuntimeError(f"{self.name}: unexpected NAS {nas}")

    def on_SecurityModeCommand(self, m):            # RRC: AS security (KgNB -> RRC/UP keys)
        self.uu(m.procedure, "SecurityModeComplete", channel="PUSCH")

    def on_RRCReconfiguration(self, m):
        p = m.payload
        if p.get("reconfiguration_with_sync"):    # handover command: leave the cell, RACH on the target
            self.ho = dict(target=p["target_cell"], procedure=m.procedure, ho_id=p.get("ho_id"), t_cmd=self.sim.now)
            self.events.append((self.sim.now, "handover command", dict(source=self.ru, target=p["target_cell"],
                                                                        ho_id=p.get("ho_id"), type=m.procedure)))
            self.ru = p["target_cell"]
            # RRC processing, then the next random-access occasion of the target cell
            t = self.sim.now + self.ho_processing_ms
            if self.prach_period_ms:
                t = -(-t // self.prach_period_ms) * self.prach_period_ms
            proc, hid = m.procedure, p.get("ho_id")
            self.sim.at(t, lambda: self.uu(proc, "RandomAccessPreamble", channel="PRACH",
                                           msg="Msg1 (dedicated preamble)", ho_id=hid))
            return
        self.uu(m.procedure, "RRCReconfigurationComplete", channel="PUSCH")
        if p.get("nas") == "RegistrationAccept":
            self.mm_state = "REGISTERED"
            self.guti = p.get("guti")
            self.t["registered"] = self.sim.now
            self.ul_nas(REG, "RegistrationComplete")
            self.ul_nas(PDU, "ULNASTransport", payload_container_type="N1 SM information",
                        nas_sm="PDUSessionEstablishmentRequest", pdu_session_id=1, request_type="initial request",
                        dnn="internet", s_nssai="SST 1", pdu_session_type="IPv4", ssc_mode=1)
        elif p.get("nas") == "ServiceAccept":
            self.session = "ACTIVE"
            self.events.append((self.sim.now, "service resumed", dict(ru=self.ru)))
        elif p.get("nas_sm") == "PDUSessionEstablishmentAccept":
            self.session = "ACTIVE"
            self.ue_ip, self.qos_rules = p.get("pdu_address"), p.get("authorized_qos_rules")
            self.t["session_active"] = self.sim.now
            # application: ask the data-network server for a downlink stream (maps to QFI 1 by the default rule)
            if self.app:
                self.uu(UL, "PUSCH", bytes=400, app="HTTP GET /stream", pdu_session_id=1, qfi=1, src_ip=self.ue_ip)

    # ----------------------------------------------------------- mobility (driven by the radio twin)
    def report(self, target_ru, rsrp_serving, rsrp_target, procedure):
        """A3 fired in the twin: send an RRC Measurement Report (TS 38.331 §5.5.4.4)."""
        if self.rrc_state != "RRC_CONNECTED" or self.ho or self.session != "ACTIVE":
            return
        self.uu(procedure, "MeasurementReport", channel="PUSCH", meas_id=1, event="A3",
                target_cell=target_ru, meas_results=dict(serving=dict(cell=self.ru, rsrp_dbm=round(rsrp_serving, 1)),
                                                         neighbour=dict(cell=target_ru, rsrp_dbm=round(rsrp_target, 1))))

    def radio_link_failure(self, new_ru):
        """Serving cell gone: T310 expired; cell selection picked `new_ru`; come back with a Service Request."""
        self.events.append((self.sim.now, "radio link failure", dict(old=self.ru, new=new_ru)))
        self.rrc_state, self.session, self.ho, self.ru = "RRC_IDLE", "SUSPENDED", None, new_ru
        self.uu(SR, "RandomAccessPreamble", channel="PRACH", msg="Msg1")

    # ----------------------------------------------------------- user plane
    def on_PDSCH(self, m):
        b = m.payload["_batch"]
        self.t.setdefault("first_dl_byte", float(b.t.min()))
        self.rx_bytes += b.bytes
        self.rx.append(b)                 # delivered packets with their per-hop delay breakdown
