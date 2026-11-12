"""
End-to-end 5G flow layer on top of the radio twin (dt/twin.py, dt/channel.py, dt/alloc.py unchanged).

A discrete-event simulation of UE, RU, DU, CU-CP, CU-UP, AMF, SMF, UPF, AUSF, UDM, NRF, PCF and a
data-network server, connected by Uu, fronthaul, F1-C/F1-U, E1, N2, N3, N4, N6 and the SBI.
Run it with experiments/e09_e2e_flow.py.
"""
from .network import E2ENetwork

__all__ = ["E2ENetwork"]
