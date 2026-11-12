"""
5G identities as taught in class ("Every ID" table, Identities study notes).

  SUPI       imsi-<MCC><MNC><MSIN>, e.g. imsi-001019876500001 (class example)
  SUCI       null scheme (protection scheme 0): the MSIN is sent as it is, as in the class pcap.
             suci-<type 0 = IMSI>-<MCC>-<MNC>-<routing indicator>-<scheme 0>-<HN key id 0>-<MSIN>
  IMEISV     TAC (8) + SNR (6) + SVN (2) = 16 digits, e.g. 3571067000159701
  5G-GUTI    80 bits = GUAMI (MCC+MNC 24 | AMF Region 8 | AMF Set 10 | AMF Pointer 6) + 5G-TMSI 32
  5G-S-TMSI  48 bits = AMF Set 10 | AMF Pointer 6 | 5G-TMSI 32  (the low 48 bits of the GUTI)
"""


def supi(mcc, mnc, msin):
    return f"imsi-{mcc}{mnc}{msin}"


def suci_null_scheme(supi_, mcc, mnc, routing_indicator="0000"):
    msin = supi_[len("imsi-") + len(mcc) + len(mnc):]
    return f"suci-0-{mcc}-{mnc}-{routing_indicator}-0-0-{msin}"


def deconceal(suci):
    """SIDF: SUCI -> SUPI. Null scheme: the scheme output is the MSIN itself."""
    _, supi_type, mcc, mnc, _ri, scheme, _key_id, output = suci.split("-")
    if supi_type != "0" or scheme != "0":
        raise ValueError(f"only an IMSI SUCI with the null scheme is modelled: {suci}")
    return supi(mcc, mnc, output)


def imeisv(tac, snr, svn):
    v = f"{tac}{int(snr):06d}{svn}"
    assert len(v) == 16 and v.isdigit(), v
    return v


def _plmn_bcd(mcc, mnc):
    """PLMN ID as 24 bits of BCD (TS 24.008): MCC2 MCC1 | MNC3 MCC3 | MNC2 MNC1, F for a 2-digit MNC."""
    d = [int(c) for c in mcc]
    n = [int(c) for c in mnc] + ([0xF] if len(mnc) == 2 else [])
    m3 = n[2] if len(mnc) == 3 else 0xF
    return ((d[1] << 4 | d[0]) << 16) | ((m3 << 4 | d[2]) << 8) | (n[1] << 4 | n[0])


def guti(mcc, mnc, amf_region_id, amf_set_id, amf_pointer, tmsi):
    assert amf_region_id < 2 ** 8 and amf_set_id < 2 ** 10 and amf_pointer < 2 ** 6 and tmsi < 2 ** 32
    value = (_plmn_bcd(mcc, mnc) << 56) | (amf_region_id << 48) | (amf_set_id << 38) | (amf_pointer << 32) | tmsi
    return dict(value=f"0x{value:020x}", mcc=mcc, mnc=mnc, amf_region_id=amf_region_id, amf_set_id=amf_set_id,
                amf_pointer=amf_pointer, tmsi=f"0x{tmsi:08x}")


def s_tmsi(guti_value):
    """5G-S-TMSI = AMF Set ID + AMF Pointer + 5G-TMSI = the low 48 bits of the 80-bit GUTI."""
    return f"0x{int(guti_value, 16) & (2 ** 48 - 1):012x}"
