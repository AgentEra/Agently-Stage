"""Run existing public Tunnel contracts unchanged under each public wake mode."""

from __future__ import annotations

import functools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agently_stage import Tunnel

mode = sys.argv[1]
original = Tunnel.__init__


@functools.wraps(original)
def initialize(self, *args, **kwargs):
    kwargs.setdefault("wake_mode", mode)
    original(self, *args, **kwargs)


Tunnel.__init__ = initialize
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
