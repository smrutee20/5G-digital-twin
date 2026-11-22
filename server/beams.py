"""
The gNB beam model: an SSB-style codebook of N fixed beams per sector.

Each sector sweeps N beams (default 8). Beam b points at azimuth phi_b inside the 120 degree sector, measured from
the sector's boresight; the beams are spread evenly in sin(phi) between -60 and +60 degrees (a DFT-style grid).
Every element in a column gets the same phase, so in elevation the beam follows the mechanical downtilt.
The UE measures every beam and reports the strongest: RSRP = best beam.

    w_b[n] = exp(-j 2 pi y_n sin(phi_b)) / sqrt(N_ant)      y_n = horizontal element position in wavelengths

The sign matches Sionna RT 2.2.0, whose per-element channel goes as exp(+j 2 pi y_n sin(phi)) and which applies the
precoder as a transpose product sum_n w[n] h[n] (checked: a 1x4 array steered at 30 deg gains 10 log10(4) = 6.02 dB).
With a cross-polarised array both slants get the same weights (one co-phased SSB port).

WHY THE TOTAL POWER STAYS FIXED
The sector's transmit power (e.g. 46 dBm) is the total over all elements: each of the N_ant elements radiates
P / N_ant, because every beam vector has unit norm (sum |w[n]|^2 = 1). A larger array therefore changes only how
the same power is focused (array gain up to 10 log10(N_ant) in the beam direction, less elsewhere), never how much
power leaves the antenna. Scaling the power with the number of elements would add a second, unrelated effect
(+24 dB just from 256 power amplifiers on a 16x16 array) and break the per-sector power limit that a real site has to
respect, so comparisons between array sizes would no longer isolate the effect of the antenna.
"""
import numpy as np

SECTOR_HALF_WIDTH_DEG = 60.0                    # 3 sectors per site -> 120 degrees each


def beam_angles_deg(num_beams):
    """Azimuth of each beam relative to boresight, spread evenly in sin(phi) over the sector."""
    u = np.sin(np.deg2rad(SECTOR_HALF_WIDTH_DEG)) * ((2 * np.arange(num_beams) + 1) / num_beams - 1)
    return np.rad2deg(np.arcsin(u))


def codebook(array, num_beams):
    """Unit-norm beam vectors [num_beams, array.num_ant] (complex) for a Sionna PlanarArray."""
    y = np.array(array.normalized_positions)[1]                     # horizontal positions in wavelengths
    u = np.sin(np.deg2rad(beam_angles_deg(num_beams)))
    w = np.exp(-1j * 2 * np.pi * y[None, :] * u[:, None])           # [beam, element]
    # Sionna lists the antennas of a dual-polarised array as [all elements, 1st slant] + [all elements, 2nd slant]
    w = np.tile(w, (1, array.num_ant // array.array_size))
    return w / np.sqrt(array.num_ant)                               # unit norm: total power fixed (see above)


def unique_beams(array, num_beams):
    """The distinct beams: with one column every beam is the same vector, so it only has to be traced once."""
    cols = len(np.unique(np.round(np.array(array.normalized_positions)[1], 6)))
    return codebook(array, num_beams if cols > 1 else 1)
