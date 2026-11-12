# IIT Gandhinagar 5G digital twin

One page, `twin.html`, shows a phone walking on the IIT Gandhinagar campus two ways at once, on one shared
timeline:

- **Left, the 3D twin.** The campus buildings and the 3 sites with their 9 sectors. Underneath is the
  ray-traced RSRP map. The phone walks a route, and a line joins it to its serving sector. A small panel shows
  the 3 strongest sectors at the phone's position and the serving sector.
- **Right, the 5G network.** UE, gNB-A/B/C (one per site), AMF, AUSF, UDM with SIDF, NSSF, SMF, UPF and the
  internet, joined by Uu, N1, N2, N3, N4, N6, N11 and Xn. Each message moves along its interface, with its
  real name.
- **Bottom.** What is happening now, in one plain line, and the identities in use: SUCI, SUPI, 5G-GUTI,
  5G-S-TMSI, C-RNTI, the NGAP IDs, the TEIDs, PDU session ID, UE IP, S-NSSAI, QFI and 5QI.

What happens on the timeline:
1. **Walk start.** SSB/MIB/SIB1, random access (C-RNTI) and RRC setup. Then registration: SUCI → AUSF →
   UDM/SIDF → SUPI, authentication, security mode with IMEISV, and Registration Accept with the 5G-GUTI. Then
   the PDU session: N11 and N4, TEIDs and the UE IP.
2. **While walking.** Every 5 steps, a request goes up and a reply comes down: UE → gNB → N3 → UPF → N6 →
   internet, and back.
3. **Handover.** When the twin's A3 rule (another sector 3 dB stronger for 2 steps) picks a sector on
   another site, the walk pauses while the core runs the Xn handover and the path switch at the UPF. The 3D
   line and the network diagram change on the same frame.
4. **After the walk.** With no data for 10 s the phone goes idle. A chat message arrives, the UPF buffers it,
   N4 tells the SMF, the AMF pages, the phone answers with a Service Request (5G-S-TMSI), and the message is
   delivered.

| Route | Xn handovers (where) |
|---|---|
| 2 (shown first) | 4: B225→A180 at 12 m, A180→C173 at 40 m, C173→B225 at 56 m, B225→C173 at 92 m |
| 3 | 2: B105→C53 at 64 m, C53→B105 at 80 m |
| 1 | none |

## Run it

Needs Python 3.10 or newer; nothing else to install.

```
python3 -m venv .venv          # once
source .venv/bin/activate      # in every new terminal (after this, `python` works)
python run.py                  # about 1 second: twin data -> network simulation -> twin.html
open twin.html                 # or double-click it; everything is inside, so it works offline
python test_flows.py           # checks the taught flows appear in order, and the handovers match the study
```

Controls: route, Play/Pause (space bar), Next step, speed, and camera (overview, or follow the phone). In the
3D view, drag to turn, right-drag to move, and scroll to zoom.

## Using the tool

**Open a given moment.** Add `#route=…&frame=…&view=…` to the address, for slides or for showing one message:

```
open "twin.html#route=2&frame=62"               # route 2, the first handover (phone switches to gNB-A)
open "twin.html#route=2&frame=269&view=follow"  # route 2, the paging step, camera following the phone
open "twin.html#route=3"                        # route 3 from the start
```

`open` with `#…` works for files in Safari and Chrome. If your browser drops it, open `twin.html` and add the
`#…` part in the address bar.

**Ask "what if" questions.** Change a setting in `config.py`, then run `python run.py` again (1 second):

| Change in `config.py` | What happens (Xn handovers on routes 1 / 2 / 3) |
|---|---|
| nothing (`A3_OFFSET_DB = 3.0`, `A3_STEPS = 2`) | 0 / 4 / 2, as in the study |
| `A3_OFFSET_DB = 6.0` (stricter) | 0 / 3 / 2: the weakest switch, A180→C173 at only +3.5 dB, no longer happens |
| `A3_STEPS = 1` (hastier) | 0 / 4 / 4: route 3 hands over back and forth more ("ping-pong") |
| `INACTIVITY_S = 30.0` | the phone stays connected longer after the walk before paging is needed |
| `DELAY_MS["N2"] = 10.0` | every procedure through the AMF takes longer; the order stays the same |

For example, from the terminal:

```
sed -i '' 's/^A3_OFFSET_DB = 3.0/A3_OFFSET_DB = 6.0/' config.py && python run.py   # try a stricter rule
sed -i '' 's/^A3_OFFSET_DB = 6.0/A3_OFFSET_DB = 3.0/' config.py && python run.py   # and back
```

`python test_flows.py` checks the handover places against the study, so it reports a difference after such a
change. That is expected: it shows the change had an effect.

## Why this is useful

- **It shows cause and effect.** A handover is not just a list of messages. You see *why* it happens (the
  ray-traced signal of each sector where the phone is), and then *what* it costs the network (15 messages over
  Uu, Xn, N2, N11, N4 and N3). Both appear on one screen, at the same moment.
- **It makes identities concrete.** Each identity appears when a message first carries it and disappears when
  it is released. For example, the SUPI never travels over the radio, and the C-RNTI and RAN UE NGAP ID change
  at a handover while the AMF UE NGAP ID, 5G-GUTI and IP stay.
- **It is one file, and needs no setup to view.** `twin.html` opens offline by double-click on any computer, so
  it can be shared for revision or shown in a presentation.
- **It can be checked and changed.** Every flow is plain Python, one small class per network element, and the
  test checks it against the class order and the study's results. A setting in `config.py` answers a "what
  if" question in a second.

## Files

| File | What it does |
|---|---|
| `run.py` | The one command: loads the twin data, simulates the network on each route, writes `twin.html` |
| `config.py` | Every setting: sites and sectors, A3 rule, identities, IP addresses, delays, timeline |
| `twin/twin_data.py` | Loads `data/twin.json` |
| `net/ids.py` | Builds the identities: SUPI, SUCI (null scheme) and SIDF, IMEISV, 5G-GUTI, 5G-S-TMSI |
| `net/sim.py` | The clock and `send()`: delivers each message after its interface's delay and logs it |
| `net/ran.py` | The phone (UE) and the gNBs: broadcast, random access, RRC, NAS relay, Xn handover, paging |
| `net/core.py` | AMF, AUSF, UDM, SIDF, NSSF, SMF, UPF (tunnels, NAT, buffering) and an internet server |
| `viewer.html` | The page template (3D twin, network diagram, playback) that `run.py` fills in |
| `test_flows.py` | Checks each taught flow's messages are in order on every route, and the handover places |
| `vendor/` | three.js r128 and its OrbitControls (MIT licence), copied into `twin.html` so it works offline |
| `data/twin.json` | Buildings, sectors, RSRP map picture, and the RSRP of all 9 sectors at every route step |
| `REPORT.md` | The project report: aim, method, results, checks and limitations |

## Computed by ray tracing vs assumed

**Ray-traced.** All of this comes from the earlier study, run with Sionna RT at 3.5 GHz with up to 3 reflections
plus diffraction, on the OpenStreetMap buildings. It is not re-traced here.
- **The RSRP map.** The strongest sector's RSRP on a 5 m grid.
- **The signal along each route.** The RSRP of all 9 sectors at each of the 66 points (2 m apart), plus line of
  sight.
- **Therefore:** the starting sector, every A3 decision, and every handover.

Some signal values on the routes are not ray-traced. Where tracing found no path, or a path implausibly weak,
the study used the 3GPP TR 38.901 formula instead. Route 2 has no such values. Route 1 has 5 of its 594 values
(66 points × 9 sectors) filled, and route 3 has 198 of 594. The panel marks these "3GPP fill".

`data/twin.json` holds all of this (and the OpenStreetMap buildings), so `python run.py` never traces.

**Assumed:**
- **Sites:** positions, heights, sector directions, 8° tilt and 46 dBm power.
- **Buildings:** heights where OpenStreetMap has none. The model leaves out trees, terrain, fast fading,
  noise and interference.
- **The A3 rule:** 3 dB for 2 steps. The walking speed is 1.4 m/s.
- **The whole 5G network:**
  - the message delays per interface;
  - the identity and IP values;
  - when data is sent;
  - the 10 s inactivity timer, and when the chat message arrives.

  Authentication values (RAND, AUTN, RES*) are placeholders, with no cryptography. The order of messages
  follows the class notes.
- **One phone.** A change between two sectors of the same site would stay inside one gNB, with no core
  messages; none happens on these routes.
