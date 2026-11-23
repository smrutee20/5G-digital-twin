# Messages and terms shown in the Twin & 5G core tab

This list was taken from the page data (`twin.html`), covering all 3 routes and all 6 flows. Every message is shown
once; "gNB" means any of gNB-A, gNB-B or gNB-C (the same message also runs between the other gNBs on the other
routes). Messages that carry a NAS message are shown on the page as `RRCSetupComplete [NAS: Registration Request]`,
and the NAS messages are listed separately in section 2.

**Class notes?** column:
- **NO** = not in the class topics (SSB/MIB/SIB1, random access, RRC setup, registration with SUCI/SUPI/5G-AKA,
  security mode, GUTI, PDU session over N11/N4/N3, uplink and downlink data, NAT at UPF, Xn handover, paging,
  Service Request).
- *likely* = not named in the topics, but a normal part of one of them.
- yes = named in the topics.

## 1. Messages (the label on the moving dot and the bottom line)

| # | Message name | From → To | Interface | Flow | What it means | Suggested label | Class notes? |
|---|---|---|---|---|---|---|---|
| 1 | SSB | gNB → UE | Uu | 1 | Each sector broadcasts a sync signal; the phone syncs and learns the cell ID | Sync signal (SSB) | yes |
| 2 | MIB | gNB → UE | Uu | 1 | Basic system info: tells the phone where to find SIB1 | Master info (MIB) | yes |
| 3 | SIB1 | gNB → UE | Uu | 1 | System info: network ID (001-01) and tracking area | Cell info (SIB1) | yes |
| 4 | RandomAccessPreamble | UE → gNB | Uu | 1, 5, 6 | Msg1: the phone says "I am here" | Random access Msg1 | yes |
| 5 | RandomAccessResponse | gNB → UE | Uu | 1, 5, 6 | Msg2: the gNB answers and gives the phone a C-RNTI | Random access Msg2 | yes |
| 6 | RRCSetupRequest | UE → gNB | Uu | 1, 6 | Msg3: the phone asks for an RRC connection | RRC Setup Request | yes |
| 7 | RRCSetup | gNB → UE | Uu | 1, 6 | Msg4: the gNB sets up the connection (SRB1) | RRC Setup | yes |
| 8 | RRCSetupComplete | UE → gNB | Uu | 2, 6 | Connection ready; carries the Registration Request or Service Request (NAS) | RRC Setup Complete | yes |
| 9 | InitialUEMessage | gNB → AMF | N2 | 2, 6 | gNB passes the phone's first NAS message to the AMF | Forward to AMF | **NO** |
| 10 | Nausf_UEAuthentication_Authenticate | AMF → AUSF | SBI | 2 | AMF asks the AUSF to authenticate this SUCI | Authenticate request | **NO** |
| 11 | Nudm_UEAuthentication_Get | AUSF → UDM | SBI | 2 | AUSF asks the UDM for the subscriber's keys | Get subscriber keys | **NO** |
| 12 | DeconcealSUCI | UDM → SIDF | internal | 2 | UDM asks the SIDF to decrypt the SUCI | Decrypt SUCI | **NO** (the step SUCI→SUPI is in the notes) |
| 13 | DeconcealSUCI_Response | SIDF → UDM | internal | 2 | SIDF returns the SUPI | SUPI found | **NO** |
| 14 | Nudm_UEAuthentication_Get_Response | UDM → AUSF | SBI | 2 | UDM returns an authentication vector (RAND, AUTN, XRES*) | Subscriber keys | **NO** |
| 15 | Nausf_UEAuthentication_Authenticate_Response | AUSF → AMF | SBI | 2 | AUSF returns the challenge, the expected answer and the SUPI | Authenticate reply | **NO** |
| 16 | DownlinkNASTransport | AMF → gNB | N2 | 2 | Carries a NAS message (Authentication Request, Security Mode Command, Registration Accept) towards the phone | AMF → phone (via gNB) | **NO** |
| 17 | DLInformationTransfer | gNB → UE | Uu | 2 | gNB passes the AMF's NAS message to the phone | gNB → phone (NAS) | **NO** |
| 18 | ULInformationTransfer | UE → gNB | Uu | 2, 3 | Carries the phone's NAS message (Authentication Response, Security Mode Complete, Registration Complete, PDU Session Request) | Phone → gNB (NAS) | **NO** |
| 19 | UplinkNASTransport | gNB → AMF | N2 | 2, 3 | gNB forwards the phone's NAS message to the AMF | Phone → AMF (via gNB) | **NO** |
| 20 | Nnssf_NSSelection_Get | AMF → NSSF | SBI | 2 | AMF asks which network slice the phone may use | Choose slice | **NO** |
| 21 | Nnssf_NSSelection_Get_Response | NSSF → AMF | SBI | 2 | NSSF allows slice SST 1 (eMBB) | Slice allowed | **NO** |
| 22 | Nsmf_PDUSession_CreateSMContext | AMF → SMF | N11 | 3 | AMF passes the session request to the SMF | Create session | *likely* (N11 step) |
| 23 | Nsmf_PDUSession_CreateSMContext_Response | SMF → AMF | N11 | 3 | SMF: session created | Session created | *likely* (N11 step) |
| 24 | PFCPSessionEstablishmentRequest | SMF → UPF | N4 | 3 | SMF picks the UPF, gives the phone an IP and sets the forwarding rules | Set up UPF rules | **NO** (N4 is in the notes, PFCP is not) |
| 25 | PFCPSessionEstablishmentResponse | UPF → SMF | N4 | 3 | UPF gives the uplink tunnel ID (TEID) | UPF rules set | **NO** |
| 26 | Namf_Communication_N1N2MessageTransfer | SMF → AMF | N11 | 3, 6 | SMF sends the PDU Session Accept (flow 3), or asks the AMF to reach an idle phone (flow 6) | SMF → AMF message | **NO** |
| 27 | Namf_Communication_N1N2MessageTransfer_Response | AMF → SMF | N11 | 3, 6 | AMF: OK (200), or "phone idle, I will page it" (202) | AMF reply | **NO** |
| 28 | PDUSessionResourceSetupRequest | AMF → gNB | N2 | 3 | AMF gives the gNB the uplink tunnel and the QoS; carries the PDU Session Accept | Set up session at gNB | **NO** |
| 29 | RRCReconfiguration | gNB → UE | Uu | 3, 5, 6 | Flows 3 and 6: data radio bearer set up. Flow 5: handover command "go to sector X" | Radio bearer setup / Handover command | **NO** (*likely* in flow 5, as the handover command) |
| 30 | RRCReconfigurationComplete | UE → gNB | Uu | 3, 5, 6 | Phone: bearer ready / "I have arrived" (handover) | Bearer ready / Arrived | **NO** (*likely* in flow 5) |
| 31 | PDUSessionResourceSetupResponse | gNB → AMF | N2 | 3 | gNB gives the core its downlink tunnel ID | gNB tunnel ready | **NO** |
| 32 | Nsmf_PDUSession_UpdateSMContext | AMF → SMF | N11 | 3, 5, 6 | AMF asks the SMF to change the session (new downlink TEID, or pause it) | Update session | *likely* (N11 step) |
| 33 | Nsmf_PDUSession_UpdateSMContext_Response | SMF → AMF | N11 | 3, 5, 6 | SMF: UPF updated | Session updated | *likely* (N11 step) |
| 34 | PFCPSessionModificationRequest | SMF → UPF | N4 | 3, 5, 6 | SMF changes the UPF rules (send downlink to this TEID, or buffer) | Update UPF rules | **NO** |
| 35 | PFCPSessionModificationResponse | UPF → SMF | N4 | 3, 5, 6 | UPF: rules updated | UPF rules updated | **NO** |
| 36 | PUSCH | UE → gNB | Uu | 4 | Uplink data over the air | Uplink data | **NO** |
| 37 | GTP-U | gNB ↔ UPF | N3 | 4, 6 | The packet inside the N3 tunnel | Tunnelled packet (N3) | *likely* (N3 user plane) |
| 38 | IPPacket | UPF ↔ Internet | N6 | 4, 6 | Ordinary IP packet; the UPF applies NAT | IP packet | yes (NAT at UPF) |
| 39 | PDSCH | gNB → UE | Uu | 4, 6 | Downlink data over the air | Downlink data | **NO** |
| 40 | MeasurementReport | UE → gNB | Uu | 5 | Event A3: another sector is stronger by the offset | Measurement report | *likely* (Xn handover) |
| 41 | HandoverRequest | old gNB → new gNB | Xn | 5 | Old gNB asks the new gNB to take the phone | Handover Request | yes |
| 42 | HandoverRequestAcknowledge | new gNB → old gNB | Xn | 5 | New gNB accepts and reserves a C-RNTI | Handover accepted | yes |
| 43 | PathSwitchRequest | new gNB → AMF | N2 | 5 | New gNB: "send the phone's data to me now" | Path switch | *likely* (Xn handover) |
| 44 | EndMarker | UPF → old gNB | N3 | 5 | Last packet on the old tunnel: nothing more will come this way | Old path closed | **NO** |
| 45 | PathSwitchRequestAcknowledge | AMF → new gNB | N2 | 5 | AMF confirms the path switch | Path switched | *likely* (Xn handover) |
| 46 | UEContextRelease | new gNB → old gNB | Xn | 5 | Old gNB can forget the phone | Release old gNB | *likely* (Xn handover) |
| 47 | UEContextReleaseRequest | gNB → AMF | N2 | 6 | No data for 10 s: gNB asks to release the phone | Release request | **NO** |
| 48 | UEContextReleaseCommand | AMF → gNB | N2 | 6 | AMF tells the gNB to release the phone | Release | **NO** |
| 49 | RRCRelease | gNB → UE | Uu | 6 | Phone goes idle and gives up its C-RNTI | Go idle | **NO** |
| 50 | UEContextReleaseComplete | gNB → AMF | N2 | 6 | gNB has forgotten the phone | Released | **NO** |
| 51 | PFCPSessionReportRequest | UPF → SMF | N4 | 6 | UPF: downlink data is waiting for an idle phone | Data waiting | **NO** |
| 52 | PFCPSessionReportResponse | SMF → UPF | N4 | 6 | SMF acknowledges | Data waiting (ack) | **NO** |
| 53 | Paging | AMF → gNB (N2), gNB → UE (Uu) | N2, Uu | 6 | Look for the idle phone by its 5G-S-TMSI in every gNB of its tracking areas | Paging | yes |
| 54 | InitialContextSetupRequest | AMF → gNB | N2 | 6 | AMF sends the session back to the gNB; carries Service Accept | Restore session | **NO** |
| 55 | InitialContextSetupResponse | gNB → AMF | N2 | 6 | gNB gives the core its new downlink TEID | Session restored | **NO** |

## 2. NAS messages (shown in brackets: `[NAS: …]`)

| Message name | From → To | Carried in | Flow | What it means | Suggested label | Class notes? |
|---|---|---|---|---|---|---|
| Registration Request | UE → AMF | RRCSetupComplete, InitialUEMessage | 2 | Phone asks to join the network, with its SUCI | Registration Request | yes |
| Authentication Request | AMF → UE | DownlinkNASTransport, DLInformationTransfer | 2 | 5G-AKA challenge (RAND, AUTN) | Authentication Request | yes |
| Authentication Response | UE → AMF | ULInformationTransfer, UplinkNASTransport | 2 | The SIM's answer RES* | Authentication Response | yes |
| Security Mode Command | AMF → UE | DownlinkNASTransport, DLInformationTransfer | 2 | Turn on ciphering and integrity | Security Mode Command | yes |
| Security Mode Complete | UE → AMF | ULInformationTransfer, UplinkNASTransport | 2 | Security on; phone sends its IMEISV | Security Mode Complete | yes |
| Registration Accept | AMF → UE | DownlinkNASTransport, DLInformationTransfer | 2 | Phone gets its 5G-GUTI, TAI list and allowed slice | Registration Accept | yes |
| Registration Complete | UE → AMF | ULInformationTransfer, UplinkNASTransport | 2 | Phone confirms the new 5G-GUTI | Registration Complete | yes |
| PDU Session Establishment Request | UE → SMF (via AMF) | ULInformationTransfer, UplinkNASTransport | 3 | Phone asks for an internet connection | PDU Session Request | yes |
| PDU Session Establishment Accept | SMF → UE (via AMF) | PDUSessionResourceSetupRequest, RRCReconfiguration | 3 | Phone gets its IP and QoS | PDU Session Accept | yes |
| Service Request | UE → AMF | RRCSetupComplete, InitialUEMessage | 6 | Paged phone comes back: "you paged me" | Service Request | yes |
| Service Accept | AMF → UE | InitialContextSetupRequest, RRCReconfiguration | 6 | Network accepts; data can flow again | Service Accept | yes (with Service Request) |

## 3. Other terms the tab shows

| Term | Where it appears | What it means | Suggested label | Class notes? |
|---|---|---|---|---|
| Flow 1 "Broadcast, random access, RRC setup" | flow label | Flow name | (keep) | yes |
| Flow 2 "Registration" | flow label | Flow name | (keep) | yes |
| Flow 3 "PDU session" | flow label | Flow name | (keep) | yes |
| Flow 4 "Uplink and downlink data" | flow label | Flow name | (keep) | yes |
| Flow 5 "Handover over Xn" | flow label | Flow name | (keep) | yes |
| Flow 6 "Idle and paging" | flow label | Flow name | (keep) | yes |
| SUCI | identity box, notes | Encrypted subscriber ID sent over the air | (keep) | yes |
| SUPI | identity box, notes | Permanent subscriber ID (IMSI-like) | (keep) | yes |
| 5G-GUTI | identity box, notes | Temporary ID that replaces the SUPI | (keep) | yes |
| 5G-S-TMSI | identity box, paging notes | Short form of the GUTI, used for paging | Short GUTI (5G-S-TMSI) | *likely* (GUTI, paging) |
| C-RNTI | identity box, notes | The phone's radio ID within one cell | Radio ID (C-RNTI) | *likely* (random access) |
| RAN UE NGAP ID | identity box, notes | The gNB's ID for this phone on N2 | gNB's phone ID | **NO** |
| AMF UE NGAP ID | identity box, notes | The AMF's ID for this phone on N2 | AMF's phone ID | **NO** |
| TEID uplink (UPF) | identity box, notes | Tunnel ID of the UPF end of the N3 tunnel | Uplink tunnel ID | *likely* (N3) |
| TEID downlink (gNB) | identity box, notes | Tunnel ID of the gNB end of the N3 tunnel | Downlink tunnel ID | *likely* (N3) |
| PDU session ID | identity box | Number of the phone's data session | Session ID | *likely* (PDU session) |
| UE IP | identity box, NAT notes | Phone's IP address (10.45.0.2) | Phone IP | yes |
| S-NSSAI | identity box | Network slice ID (SST 1 = eMBB) | Slice ID | **NO** |
| QFI | identity box, notes | QoS flow ID inside the session | QoS flow ID | **NO** |
| 5QI | identity box, notes | QoS class (9 = best effort) | QoS class | **NO** |
| AMF, SMF, UPF | network diagram | Core functions: access & mobility, sessions, user plane | (keep) | yes |
| AUSF, UDM | network diagram | Authentication server, subscriber database | (keep) | *likely* (5G-AKA) |
| SIDF | network diagram | Decrypts SUCI → SUPI inside the UDM | (keep) | *likely* (SUCI/SUPI) |
| NSSF | network diagram | Chooses the network slice | Slice selection | **NO** |
| Internet / server | network diagram | The data network beyond N6 | (keep) | yes |
| Uu | diagram link | Radio link phone ↔ gNB | Radio (Uu) | *likely* |
| Xn | diagram link | gNB ↔ gNB | (keep) | yes |
| N1 (NAS, carried over Uu + N2) | diagram link | Phone ↔ AMF signalling | (keep) | **NO** |
| N2 | diagram link | gNB ↔ AMF signalling (NGAP) | (keep) | **NO** |
| N3 | diagram link | gNB ↔ UPF user-plane tunnel | (keep) | yes |
| N4 | diagram link | SMF ↔ UPF (PFCP) | (keep) | yes |
| N6 | diagram link | UPF ↔ internet | (keep) | **NO** |
| N11 | diagram link | AMF ↔ SMF | (keep) | yes |
| SBI | diagram link | Service-based interface between core functions | (keep) | **NO** |
| RRC connected / RRC idle / off | signal panel | Phone's radio state | Connected / Idle / Off | *likely* (paging) |
| PSS + SSS, PCI | SSB note | Sync signals and the physical cell ID | Sync signals, cell ID | **NO** |
| Msg1 – Msg4 | random-access notes | The four random-access steps | (keep) | yes |
| SRB1 | RRC Setup note | Signalling radio bearer | Signalling channel | **NO** |
| Data radio bearer | RRCReconfiguration note | Radio channel for user data | Data channel | **NO** |
| RAND, AUTN, XRES*, RES* | authentication notes | 5G-AKA challenge and answers | (keep) | yes (5G-AKA) |
| IMEISV | Security Mode note | Device (handset) ID | Device ID | **NO** |
| SST 1 (eMBB) | NSSF note | Slice type: mobile broadband | Broadband slice | **NO** |
| PDRs | PFCP note | UPF packet-detection rules | Forwarding rules | **NO** |
| TAI list / tracking area | Registration Accept, paging notes | Areas where the phone is paged | Tracking areas | *likely* (paging) |
| Event A3, offset, time-to-trigger | Measurement Report note, header | Handover trigger: a neighbour stronger by the offset for N steps | Handover trigger | *likely* (Xn handover) |
| "Sector … is on the same gNB: the gNB switches sector itself" | info note | Handover inside one gNB, no core messages | Same-gNB sector change | **NO** |
| "No data for 10 s … inactivity timer" | info note | Why the phone goes idle | Inactivity timer | **NO** |
| "the UPF buffers the packet" | info note | UPF holds downlink data for an idle phone | (keep) | *likely* (paging) |
| Strongest sectors here, RSRP (dBm), line of sight / blocked | signal panel | Received power from each sector at the phone's position | (keep) | **NO** (not a protocol term) |
| Serving sector | signal panel | Sector the phone is connected to | (keep) | *likely* |
