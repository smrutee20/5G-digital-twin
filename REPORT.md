# A 5G digital twin of the IIT Gandhinagar campus, with the 5G core flows

*Course project, 5G and Beyond, IIT Gandhinagar, Semester I 2026. Draft.*

## 1. Aim

Show, on one page and on one timeline, two things that are usually taught separately:

- **The radio side.** Where a phone gets its signal on the real campus, and why it changes serving cell.
- **The 5G system's side.** Which messages the phone, the base stations and the core exchange because of it,
  and which identities each message carries.

## 2. What was built

One offline web page, `twin.html`, made by one command, `python run.py`.

- **Left: a 3D digital twin of the campus.**
  - The OpenStreetMap buildings.
  - 3 sites (A, B, C), each with 3 sectors, so 9 cells.
  - The ray-traced RSRP map on the ground.
  - A phone walking one of 3 routes, joined by a line to its serving sector.
  - A panel with the 3 strongest sectors at the phone's position.
- **Right: the 5G network,** limited to what was taught.
  - The elements: UE, one gNB per site, AMF, AUSF, UDM (with its SIDF), NSSF, SMF, UPF and the internet.
  - The interfaces: Uu, N1, N2, N3, N4, N6, N11 and Xn.
  - Each message moves along its interface, with its 3GPP name.
- **Bottom:** the current step in one plain sentence, and the identities in use. These are SUCI, SUPI,
  5G-GUTI, 5G-S-TMSI, C-RNTI, RAN/AMF UE NGAP IDs, TEIDs, PDU session ID, UE IP, S-NSSAI, QFI and 5QI.

Both sides are driven by one event log, so the serving line in 3D and the network diagram change on the same
frame.

## 3. Method

### 3.1 The radio twin (from ray tracing)

The signal values come from the ray tracing of the project's earlier study:
- **Tool and settings:** Sionna RT at 3.5 GHz (100 MHz, 273 PRBs), 46 dBm per sector, 30 m masts with 8°
  downtilt, up to 3 reflections plus diffraction.
- **Scene:** the OpenStreetMap buildings of a 1.4 km × 1.4 km area around the campus.
- **Routes:** for each of 3 routes (66 points, 2 m apart, 130 m), the ray-traced RSRP of all 9 sectors at every
  point, plus line of sight.
- **RSRP map:** the strongest sector's RSRP on a 5 m grid.
- **RSRP formula:** transmit power per resource element (46 dBm − 10·log₁₀(273 × 12)) plus the path gain
  averaged over the 273 PRBs.

These results are stored in `data/twin.json`; nothing is re-traced when the page is built.

### 3.2 The handover rule (event A3)

At every step, the twin compares the serving sector with the strongest other sector. If a neighbour is more
than 3 dB stronger for 2 consecutive steps, the serving sector changes.
- **Another site:** the network runs an Xn handover.
- **Same site:** the change would stay inside one gNB, with no core messages. None occurs on these routes.

### 3.3 The network model

`net/` holds a small discrete-event simulation:
- **One Python class per network element.** A message called `X` is handled by the element's method `on_X`,
  which may send further messages.
- **Message timing.** Each message is delivered after a fixed delay for its interface (1 ms on most, 5 ms on
  N6) plus 0.5 ms of processing.
- **Logging.** Every message is logged with its interface, a plain-English note, and the identities it
  carries. Those identities feed the panel at the bottom.

The flows follow the order given in the class notes:

| Flow | Trigger on the timeline | Main messages |
|---|---|---|
| 1. Broadcast and access | walk start | SSB, MIB, SIB1 → random access (C-RNTI in Msg2) → RRC Setup Request / Setup |
| 2. Registration | after RRC setup | Registration Request (SUCI, null scheme) → AMF → AUSF → UDM → SIDF (SUCI → SUPI) → Authentication Request/Response → Security Mode Command/Complete (IMEISV) → NSSF → Registration Accept (5G-GUTI, TAI list, allowed S-NSSAI) → Registration Complete |
| 3. PDU session | after registration | PDU Session Establishment Request → N11 CreateSMContext → N4 PFCP Session Establishment (uplink TEID, UE IP) → N1N2 transfer → PDU Session Resource Setup → downlink TEID → N4 modification |
| 4. Data | every 5 steps while walking | uplink UE → gNB → N3 (GTP-U) → UPF (NAT) → N6, and the reply back down |
| 5. Xn handover | when A3 picks another site | Measurement Report → Xn Handover Request / Ack → handover command → random access on the new cell → Path Switch Request → N11 → N4 (path switch, End Marker to the old gNB) → Path Switch Ack → Xn UE Context Release |
| 6. Idle and paging | after the walk ends | 10 s without data → release (N2, N11, N4 "buffer", RRC Release) → a chat message arrives → UPF buffers → N4 report → AMF pages the TAI list → Service Request (5G-S-TMSI) → context set up again → buffered data delivered |

## 4. Results

### 4.1 Where the phone hands over

| Route | Xn handovers | Ray-traced values |
|---|---|---|
| 1 | none: sector A180 serves the whole walk | 589 of 594 (5 from the 3GPP formula) |
| 2 | 4 (details below) | all 594 |
| 3 | 2: B105 → C53 at 64 m (+7.3 dB), C53 → B105 at 80 m (+5.9 dB) | 396 of 594 (198 from the 3GPP formula) |

Route 2, in detail:

| Distance | From → to | Serving RSRP | New RSRP | Margin |
|---|---|---|---|---|
| 12 m | B225 → A180 | −123.1 dBm | −118.2 dBm | +4.9 dB |
| 40 m | A180 → C173 | −119.0 dBm | −115.5 dBm | +3.5 dB |
| 56 m | C173 → B225 | −111.8 dBm | −99.6 dBm | +12.2 dB |
| 92 m | B225 → C173 | −99.5 dBm | −92.5 dBm | +7.0 dB |

These are the same places as in the earlier study (which used the same A3 rule); `test_flows.py` checks this.
The handovers happen where buildings block one site and open another.
- **First 40 m of route 2:** the best sector is weak (−119 to −103 dBm), so a few dB decide the serving cell;
  the first two handovers have margins of only 4.9 and 3.5 dB.
- **56 m:** the margin is 12 dB, a clear change of best server.

### 4.2 Signalling cost

| | Route 1 | Route 2 | Route 3 |
|---|---|---|---|
| Messages in total | 160 | 220 | 190 |
| Power on: broadcast and access, registration, PDU session | 7 + 22 + 16 | 7 + 22 + 16 | 7 + 22 + 16 |
| Data (13 request/reply pairs) | 78 | 78 | 78 |
| Xn handovers | 0 | 60 | 30 |
| Idle and paging | 37 | 37 | 37 |

- **Cost of one handover:** 15 messages over Uu, Xn, N2, N11, N4 and N3.
- **Time:** with the assumed delays, one handover takes about 19.5 ms from Measurement Report to the release of
  the old gNB.
- **Comparison with route 1:** route 2 needs 60 more messages than route 1 to stay connected over the same
  130 m. All of them are caused by where the walk passes buildings.

### 4.3 Identities through the walk (route 2)

| Event | What changes |
|---|---|
| Power on | C-RNTI 0x4701 and RAN UE NGAP ID 201 (gNB-B), AMF UE NGAP ID 1, 5G-GUTI 0x00f110010041c0000001, UE IP 10.45.0.2, uplink TEID 0x00000a01, downlink TEID 0x0000b101 |
| Each Xn handover | **new:** C-RNTI, RAN UE NGAP ID and downlink TEID, from the new gNB. **kept:** AMF UE NGAP ID, 5G-GUTI, UE IP, uplink TEID |
| Going idle | dropped: C-RNTI, both NGAP IDs and the downlink TEID. Kept: 5G-GUTI / 5G-S-TMSI, UE IP, PDU session |
| Service Request after paging | new C-RNTI, RAN UE NGAP ID, AMF UE NGAP ID (2) and downlink TEID; found by 5G-S-TMSI 0x0041c0000001 |

The SUPI (imsi-001019876500001) is never sent over Uu or N2. Only the SUCI is, and the SIDF turns it back into
the SUPI inside the UDM.

### 4.4 What if: the A3 settings

| A3 setting | Xn handovers (routes 1 / 2 / 3) |
|---|---|
| 3 dB, 2 steps (used) | 0 / 4 / 2 |
| 6 dB, 2 steps | 0 / 3 / 2 |
| 3 dB, 1 step | 0 / 4 / 4 |
| 1 dB, 2 steps | 0 / 4 / 2 |
| 3 dB, 3 steps | 0 / 4 / 2 |

- **A larger offset (6 dB)** removes the weakest switch on route 2 (A180 → C173 at only +3.5 dB).
- **A single step** doubles route 3's handovers, because the phone switches back and forth ("ping-pong").

This is the usual trade-off: fewer handovers against staying longer on a weaker cell.

## 5. Checks

`python test_flows.py` checks, on every route, that:
- each taught flow's key messages appear in the taught order (flow 5 is checked once per handover);
- the handovers happen at the study's places (route 2: 12, 40, 56, 92 m; route 3: 64, 80 m; route 1: none);
- the SUPI never travels over Uu or N2;
- after paging, the buffered message reaches the phone.

All checks pass. The page was also checked visually in a browser: at each handover the 3D serving line and the
network diagram switch on the same frame.

## 6. Limitations

- **Values not from ray tracing.** Some route values are 3GPP TR 38.901 values used where tracing found no
  usable path (route 3: a third of its values). The page marks them "3GPP fill". Route 2 has none.
- **The model leaves out:** trees, terrain and building interiors (OpenStreetMap has none of these), fast
  fading, noise, and interference.
- **The ray-tracing data cannot be re-run.** The raw data is no longer available, so `data/twin.json` is fixed.
- **Assumed network values.** Message delays, identity values, IP addresses and the data timetable are
  assumptions; the timings show order and relative cost, not measured latency. Authentication values are
  placeholders, with no cryptography.
- **Simplified scope.** There is one phone and one PDU session. Same-site sector changes are not signalled.
  Steps not taught in class (e.g. AS security, Xn data forwarding, NRF/PCF) are left out.
- **Authentication order.** It follows the class order: the AUSF returns the SUPI with the challenge. In the
  standard, the AUSF releases the SUPI only after it has checked RES*.

## 7. How to run

```
python3 -m venv .venv && source .venv/bin/activate
python run.py          # builds twin.html in about 1 second
open twin.html         # works offline
python test_flows.py   # the checks of section 5
```

`README.md` lists every file and shows how to try other settings.

## 8. Conclusion

The page links a radio decision to its signalling cost, using real campus geometry. On route 2, buildings make
the best server change four times in 130 m. Each change costs 15 messages across six interfaces and replaces
the phone's radio-side identities while its core identities stay. Changing the A3 settings shows the
handover/ping-pong trade-off directly. Because it is a single offline file built from a few short Python files
that are checked automatically, it can be used to revise the class flows and extended one element at a time.
