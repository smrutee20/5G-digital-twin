"""
Real packets for the "5G Network Visualiser" packet view:  .venv/bin/python tools/extract_pcap.py

Reads the class captures in plan/ (gitignored: never commit them, never copy them into the repo or the site), decodes
them with tshark -T json and saves ONE example frame per message type as a compact, masked field tree in
data/pcap_examples.json (the page embeds that file; run.py / tools/build_site.py pick it up).

  message types  NGAP (N2) and the NAS-5GS inside it; F1AP and the NR RRC inside it (the F1 link between the gNB's
                 DU and CU: the RRC messages the twin shows on Uu); GTP-U on N3 (one uplink, one downlink G-PDU)
  field tree     per layer: [label, children]; labels use tshark's own field names and value strings
                 (tshark -G fields / -G values), e.g. "procedureCode: id-InitialUEMessage (15)"
  left out       link layer (MAC addresses), PER encoding details, byte blobs (they would carry identifiers in
                 encoded form), the application payload inside GTP-U (only its IP/UDP/TCP headers are kept)
  masked         IMSI/SUPI, SUCI MSIN, IMEI(SV), GUTI/5G-TMSI, IP addresses, e.g. "001-01-98765xxxxx", "172.16.x.x"
                 (the original values are then checked to be absent from the output)

tshark: from PATH or Wireshark.app; if missing, `brew install wireshark` is tried.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURES = [ROOT / "plan" / "iitgn_30Oct25.pcap", ROOT / "plan" / "iitgn_30Oct2025.pcap"]
OUT = ROOT / "data" / "pcap_examples.json"
MAX_NODES = 700                     # per frame (RRC Reconfiguration / UE capabilities are huge)
FRAMES_PER_TYPE = 3                 # a few frames per message type, with different NAS contents if possible


# ---------------------------------------------------------------------- tshark
def find_tshark():
    for p in (shutil.which("tshark"), "/Applications/Wireshark.app/Contents/MacOS/tshark", "/opt/homebrew/bin/tshark"):
        if p and Path(p).exists():
            return p
    if shutil.which("brew"):
        print("tshark not found: brew install wireshark")
        subprocess.run(["brew", "install", "wireshark"], check=True)
        if shutil.which("tshark"):
            return shutil.which("tshark")
    sys.exit("tshark not found: install Wireshark (brew install wireshark)")


def dictionaries(ts):
    """tshark's field names ({abbrev: (name, base)}) and value strings ({abbrev: {int: text}})."""
    names, values = {}, {}
    for line in subprocess.run([ts, "-G", "fields"], capture_output=True, text=True).stdout.splitlines():
        p = line.split("\t")
        if p[0] == "F" and len(p) > 5:
            names[p[2]] = (p[1], p[5])
    for line in subprocess.run([ts, "-G", "values"], capture_output=True, text=True).stdout.splitlines():
        p = line.split("\t")
        if p[0] == "V" and len(p) == 4:
            try:
                values.setdefault(p[1], {})[int(p[2])] = p[3]
            except ValueError:
                pass
    return names, values


def decode(ts, pcap, display_filter, count=None):
    cmd = [ts, "-r", str(pcap), "-Y", display_filter, "-T", "json"] + (["-c", str(count)] if count else [])
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return json.loads(out, object_pairs_hook=list)          # keep duplicate keys (ip.addr twice, inner ip ...)


# ---------------------------------------------------------------------- masking
ID_KEYS = re.compile(r"imsi|supi|msin|imei|tmsi|guti|suci|e212\.|msisdn|mac_address|\.eth\b|ue_ip|pdu_addr|ipv4|ipv6", re.I)
IPV4 = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")
MAC = re.compile(r"\b[0-9a-f]{2}(:[0-9a-f]{2}){5}\b", re.I)
PRIVATE = re.compile(r"^(10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.)")


def mask_value(v):
    s = str(v)
    if IPV4.fullmatch(s):
        return ".".join(s.split(".")[:2]) + ".x.x" if PRIVATE.match(s) else "x.x.x.x"
    digits = re.sub(r"\D", "", s)
    if re.fullmatch(r"\d{15}", s):                                          # IMSI / SUPI
        return f"{s[:3]}-{s[3:5]}-{s[5:10]}" + "x" * 5
    if re.fullmatch(r"\d{14,16}", s):                                       # IMEI(SV): keep the TAC (model)
        return s[:8] + "x" * (len(s) - 8)
    if re.fullmatch(r"\d{5,13}", s):                                        # MSIN
        return s[:min(5, len(s) // 2)] + "x" * (len(s) - min(5, len(s) // 2))
    if re.fullmatch(r"0x[0-9a-fA-F]+", s):                                  # TMSI / GUTI parts
        return s[:4] + "x" * (len(s) - 4)
    keep = len(s) // 3 if len(digits) >= 5 else 0                            # other identifiers: keep a third
    return s[:keep] + re.sub(r"[0-9a-zA-Z]", "x", s[keep:])


class Masker:
    def __init__(self):
        self.secrets = {}                                                   # original -> masked

    def value(self, key, v):
        if isinstance(v, str) and (ID_KEYS.search(key) or IPV4.fullmatch(v)):
            if v not in ("0", "1") and len(v) > 2:
                self.secrets[v] = mask_value(v)
                return self.secrets[v]
        return v

    def text(self, s):
        s = IPV4.sub(lambda m: mask_value(m.group(0)), s)
        s = MAC.sub("xx:xx:xx:xx:xx:xx", s)
        for raw, masked in sorted(self.secrets.items(), key=lambda kv: -len(kv[0])):
            if len(raw) >= 5:
                s = s.replace(raw, masked)
        return s


# ---------------------------------------------------------------------- field tree
BLOB = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){8,}$")          # 9+ bytes of hex: encoded content, dropped
SKIP_PREFIX = ("per.", "frame.", "sll.", "eth.", "_ws.", "sctp.chunk_bit", "ip.checksum", "udp.checksum", "tcp.checksum",
               "ip.stream", "udp.stream", "tcp.stream", "ip.host", "ip.addr", "ip.src_host", "ip.dst_host",
               "udp.port", "tcp.port", "sctp.port", "sctp.assoc_index", "sctp.data_tsn_raw", "udp.time", "tcp.time",
               "tcp.analysis", "tcp.options", "tcp.option", "tcp.payload", "udp.payload", "tcp.segment", "tcp.reassembled")


class TreeBuilder:
    def __init__(self, names, values, masker):
        self.names, self.values, self.m = names, values, masker
        self.count = 0

    def label(self, key, val):
        name, base = self.names.get(key, (None, None))
        if name is None:                                                    # a text item ("Item 1: id-NAS-PDU")
            return self.m.text(key) if val in (None, "") else f"{self.m.text(key)}: {self.m.text(str(val))}"
        if key.endswith("_element") or val is None:
            return name
        v = self.m.value(key, val)
        if v != val:
            return f"{name}: {v}"
        if BLOB.match(str(v)):
            return f"{name}: ‹{(len(v) + 1) // 3} bytes›"
        try:
            text = self.values.get(key, {}).get(int(str(v), 0))
        except ValueError:
            text = None
        return f"{name}: {text} ({v})" if text else f"{name}: {self.m.text(str(v))}"

    def build(self, pairs):
        """tshark json (list of pairs) -> [[label, children], ...]; X_tree children are attached to field X."""
        out, by_key = [], {}
        for key, val in pairs:
            if key.startswith(SKIP_PREFIX):
                continue
            if self.count >= MAX_NODES:
                out.append(["… (more fields not shown)", []])
                break
            if key.endswith("_tree") and key[:-5] in by_key:
                by_key[key[:-5]][1].extend(self.build(val) if isinstance(val, list) else [])
                continue
            self.count += 1
            if isinstance(val, list):                                       # a subtree
                node = [self.label(key, None), self.build(val)]
                if not node[1] and key.endswith("_element"):
                    continue
            else:
                node = [self.label(key, val), []]
            by_key[key] = node
            out.append(node)
        return out


def walk(pairs, fn, path=()):
    for k, v in pairs:
        fn(k, v, path)
        if isinstance(v, list):
            walk(v, fn, path + (k,))


# ---------------------------------------------------------------------- message types in a frame
def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def message_types(layers, values):
    """[(protocol, type)] in this frame, e.g. [("F1AP", "ULRRCMessageTransfer"), ("RRC", "RRCSetupComplete"),
    ("NAS", "Registration request")]."""
    found = []

    def fn(k, v, path):
        top = path[0] if path else k
        msg_level = bool(path) and re.search(r"\.(initiatingMessage|successfulOutcome_|unsuccessfulOutcome_)value_element$", path[-1])
        if top == "ngap" and re.fullmatch(r"ngap\.(\w+)_element", k) and msg_level:
            found.append(("NGAP", k[5:-8]))
        elif top == "f1ap" and re.fullmatch(r"f1ap\.(\w+)_element", k) and msg_level:
            found.append(("F1AP", k[5:-8]))
        elif k in ("nas-5gs.mm.message_type", "nas-5gs.sm.message_type") and isinstance(v, str):
            found.append(("NAS", values.get(k, {}).get(int(v, 0), v)))
        elif re.fullmatch(r"nr-rrc\.(MIB|SIB1)_element", k):
            found.append(("RRC", k[7:-8]))
        elif re.fullmatch(r"nr-rrc\.(\w+)_element", k) and len(path) > 1 and path[-1] == "nr-rrc.c1_tree" \
                and path[-2] == "nr-rrc.message_tree":
            found.append(("RRC", k[7:-8]))
    walk(layers, fn)
    seen, out = set(), []
    for t in found:
        if t not in seen and not t[1].endswith(("_IEs", "IEs")):
            seen.add(t)
            out.append(t)
    return out


def keep_layers(layers):
    """The layers worth showing: IP, SCTP/UDP, NGAP/F1AP (NAS / RRC nested inside), GTP-U and the inner IP/UDP/TCP
    headers (the application payload inside the tunnel is not kept)."""
    out, inner = [], False
    for k, v in layers:
        if k in ("frame", "sll", "eth", "ethertype"):
            continue
        if k == "gtp":
            inner = True
            out.append((k, v))
            continue
        if inner and k not in ("ip", "udp", "tcp", "icmp"):
            out.append((k, [("(payload not shown)", "")]))
            continue
        out.append((k, v))
    return out


LAYER_NAME = {"ip": "IP", "sctp": "SCTP", "udp": "UDP", "tcp": "TCP", "ngap": "NGAP", "f1ap": "F1AP", "gtp": "GTP-U",
              "nas-5gs": "NAS-5GS", "nr-rrc": "NR RRC", "dns": "DNS", "icmp": "ICMP", "quic": "QUIC", "tls": "TLS"}


def frame_record(pkt, cap, names, values, masker, types):
    src = dict(pkt)["_source"]
    layers = dict(src)["layers"]
    fr = dict(dict(layers)["frame"])
    tb = TreeBuilder(names, values, masker)
    tree, seen_ip = [], 0
    for k, v in keep_layers(layers):
        if k == "ip":
            seen_ip += 1
        title = LAYER_NAME.get(k, k.upper()) + (" (inner, inside the tunnel)" if k == "ip" and seen_ip > 1 else "")
        tree.append([title, tb.build(v) if isinstance(v, list) else []])
    return dict(capture=cap.name, frame=int(fr["frame.number"]), time_s=round(float(fr["frame.time_relative"]), 3),
                length=int(fr["frame.len"]), protocols=fr["frame.protocols"].replace("sll:ethertype:", ""),
                types=[list(t) for t in types], tree=tree)


# ---------------------------------------------------------------------- main
def main():
    caps = [c for c in CAPTURES if c.exists()]
    if not caps:
        sys.exit("no captures in plan/ (they are not in the repo)")
    ts = find_tshark()
    names, values = dictionaries(ts)
    masker = Masker()
    frames, index = [], {}                                     # index: "PROTO:type" -> [frame ids]

    def add(pkt, cap, types):
        rec = frame_record(pkt, cap, names, values, masker, types)
        fid = len(frames)
        frames.append(rec)
        for p, t in types:
            index.setdefault(f"{p}:{t}", []).append(fid)

    for cap in caps:
        print(f"decoding {cap.name} (NGAP, F1AP) ...")
        for pkt in decode(ts, cap, "ngap || f1ap"):
            layers = dict(dict(pkt)["_source"])["layers"]
            types = message_types(layers, values)
            if not types:
                continue
            # keep a frame if it brings a new type, or a new NAS content for a type we have fewer than N of
            nas = tuple(sorted(t for p, t in types if p == "NAS"))
            new = any(f"{p}:{t}" not in index for p, t in types)
            more = any(len(index.get(f"{p}:{t}", [])) < FRAMES_PER_TYPE and p in ("NGAP", "F1AP") and nas and
                       nas not in {tuple(sorted(x for q, x in frames[i]["types"] if q == "NAS")) for i in index[f"{p}:{t}"]}
                       for p, t in types if f"{p}:{t}" in index)
            if new or more:
                add(pkt, cap, types)
        print(f"decoding {cap.name} (GTP-U) ...")
        got = {"uplink": False, "downlink": False}
        for pkt in decode(ts, cap, "gtp && (dns || icmp)", count=20000):
            layers = dict(dict(pkt)["_source"])["layers"]
            ips = [dict(v) for k, v in layers if k == "ip"]
            if len(ips) < 2:
                continue
            d = "uplink" if ips[1].get("ip.src", "").startswith("10.") else "downlink"
            if not got[d] and f"GTP:G-PDU {d}" not in index:
                add(pkt, cap, [("GTP", f"G-PDU {d}")])
                got[d] = True
            if all(got.values()):
                break

    out = dict(
        about="One decoded example frame per message type from the class captures (tshark -T json), identifiers "
              "masked; made by tools/extract_pcap.py. NGAP/NAS on N2, F1AP/RRC on F1 (between the gNB's DU and CU), "
              "GTP-U on N3.",
        captures=[c.name for c in caps], tshark=subprocess.run([ts, "-v"], capture_output=True, text=True).stdout.split("\n")[0],
        index=index, frames=frames)
    text = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    # last pass on the whole text, then check that no original identifier is left
    text = masker.text(text)
    leaks = [raw for raw in masker.secrets if len(raw) >= 5 and raw in text]
    if leaks:
        sys.exit(f"masking failed for {len(leaks)} values; nothing written")
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(frames)} frames, {len(index)} message types, "
          f"{OUT.stat().st_size / 1e3:.0f} kB, {len(masker.secrets)} identifiers masked")
    for k in sorted(index):
        print(f"  {k:55s} frames {[frames[i]['frame'] for i in index[k]]}")


if __name__ == "__main__":
    main()
