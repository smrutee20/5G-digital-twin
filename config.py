"""
All settings in one place (plain Python, so nothing has to be installed).
Positions are local metres on the IIT Gandhinagar campus: x = east, y = north of (23.2107 N, 72.6872 E).
"""

# ---------------------------------------------------------------- the digital twin (left side)
# Three sites (one gNB each), each with 3 sectors. A sector is named site + direction, e.g. "B225".
SITES = {
    "A": dict(xy=(173.7, 158.4), height_m=30.0, sectors_deg=(60, 180, 300)),     # Indoor Sports Complex
    "B": dict(xy=(59.1, 333.9), height_m=30.0, sectors_deg=(105, 225, 345)),     # Academic Block 12
    "C": dict(xy=(-148.4, -215.8), height_m=30.0, sectors_deg=(53, 173, 293)),   # Kyzeel Hostel
}

# The three routes of the earlier study: 66 points, 2 m apart, walked at 1.4 m/s (one step every 1.43 s)
STEP_M = 2.0
SPEED_MPS = 1.4
DEFAULT_ROUTE = 2                               # the route with the most handovers (2)

# Handover rule (event A3): another sector 3 dB stronger than the serving one for 2 steps in a row
A3_OFFSET_DB = 3.0
A3_STEPS = 2

# ---------------------------------------------------------------- the 5G network (right side)
MCC, MNC = "001", "01"                          # test network PLMN 001-01
MSIN = "9876500001"                             # SUPI imsi-001019876500001
IMEISV = dict(tac="35710670", snr=1597, svn="01")   # 3571067000159701
TAC = 1                                         # one tracking area for all three sites
GUAMI = dict(amf_region_id=1, amf_set_id=1, amf_pointer=1)
FIRST_5G_TMSI = 0xC0000001
SST = 1                                         # S-NSSAI slice/service type 1 = eMBB
QFI, FIVE_QI = 1, 9                             # one QoS flow, 5QI 9 = default internet
DNN = "internet"
UE_IP = "10.45.0.2"                             # private address the SMF gives the phone
UPF_N3_IP = "10.100.1.1"
UPF_PUBLIC_IP = "198.51.100.7"                  # the UPF's NAT address towards the internet
SERVER_IP = "203.0.113.10"                      # a web/chat server on the internet
GNB_N3_IP = {"A": "10.100.0.1", "B": "10.100.0.2", "C": "10.100.0.3"}

# One-way delay per interface [ms] (assumptions; they only set the order and spacing of messages)
DELAY_MS = dict(Uu=1.0, N2=1.0, N3=1.0, N4=1.0, N6=5.0, N11=1.0, SBI=1.0, Xn=1.0, internal=0.1)
PROCESSING_MS = 0.5                             # every element takes this long to handle a message

# ---------------------------------------------------------------- what happens on the walk
DATA_EVERY_STEPS = 5                            # while walking, a request up and a reply down every 5 steps (7 s)
INACTIVITY_S = 10.0                             # no data for this long -> the gNB releases the phone to idle
CHAT_AFTER_IDLE_S = 3.0                         # after the walk, a chat message arrives for the idle phone


def sectors():
    """Every sector: name ("A60"), site ("A"), antenna position (x, y, z) and direction (degrees)."""
    return [dict(name=f"{s}{az}", site=s, pos=(*v["xy"], v["height_m"]), az=float(az))
            for s, v in SITES.items() for az in v["sectors_deg"]]


def pci(sector):
    """Physical cell ID broadcast in the sector's SSB: 3 x (site number) + (sector number), from 300."""
    names = [x["name"] for x in sectors()]
    i = names.index(sector)
    return 300 + 3 * (i // 3) + i % 3
