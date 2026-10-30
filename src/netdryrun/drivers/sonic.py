"""SONiC (docker-sonic-vs) driver. SONiC routes with FRR inside the container, so state is read
exactly like FRR (vtysh JSON); this class exists so SONiC is detected and named on its own."""
from __future__ import annotations

from .frr import FrrDriver


class SonicDriver(FrrDriver):
    name = "sonic"
