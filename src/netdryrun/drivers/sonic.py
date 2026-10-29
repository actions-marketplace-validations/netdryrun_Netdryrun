"""SONiC (docker-sonic-vs) driver. SONiC routes with FRR inside the container, so state is read
exactly like FRR (vtysh JSON); this class exists so SONiC is detected and named on its own."""
from __future__ import annotations

from .frr import FrrDriver


class SonicDriver(FrrDriver):
    name = "sonic"

    def config_load_errors(self) -> list[str] | None:
        # docker-sonic-vs is configured after boot by setup commands, which fail the run on a non-zero exit code;
        # where its FRR logs a rejected line has not been captured yet, so it doesn't claim a clean load
        return None
