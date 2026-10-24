"""Run unchanged channel/stream tests with an isolated mechanism substitution.

Patching lives only in this test process; the production files stay untouched.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest
from candidates import ChunkStore, WakeTunnel

from agently_stage import Tunnel

variant = sys.argv[1]
assert variant in ("chunk", "grouped", "local")
original_init = Tunnel.__init__


@functools.wraps(original_init)
def initialize(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    if variant == "chunk":
        self._items = ChunkStore()
    else:
        self.wake = variant
        self.notifications = 0
        self.resolutions = 0


Tunnel.__init__ = initialize
if variant != "chunk":
    Tunnel._wake_waiters_locked = WakeTunnel._wake_waiters_locked
    Tunnel.resolve_many = staticmethod(WakeTunnel.resolve_many)

raise SystemExit(
    pytest.main(
        [
            "-q",
            "tests/test_api/test_Tunnel.py",
            "tests/test_runtime/test_tunnel_races.py",
            "tests/test_runtime/test_stage_stream.py",
        ]
    )
)
