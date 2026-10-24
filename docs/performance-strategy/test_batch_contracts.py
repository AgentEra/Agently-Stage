"""Check the group semantics used by H1, independently of timing."""

from __future__ import annotations

import asyncio
import concurrent.futures as cf
import contextvars
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest

from agently_stage import Stage


def test_carrier_gather_keeps_context_and_cancellation_scope():
    marker = contextvars.ContextVar("batch_marker", default="missing")
    marker.set("batch")
    entered = threading.Event()
    finalized = []
    stage = Stage(loop="stage")

    async def child(i):
        assert marker.get() == "batch"
        if i == 7:
            entered.set()
        try:
            await asyncio.sleep(10)
        finally:
            finalized.append(i)

    async def batch():
        await asyncio.gather(*(child(i) for i in range(8)))

    handle = stage.go(batch)
    assert entered.wait(2)
    handle.cancel(timeout=2)
    handle.wait_settled(timeout=2)
    assert sorted(finalized) == list(range(8))
    stage.close(timeout=2)


def test_carrier_gather_body_failure_does_not_fake_sibling_settlement():
    entered = threading.Event()
    release = cf.Future()
    finished = threading.Event()
    stage = Stage(loop="stage")

    async def sibling():
        entered.set()
        await asyncio.wrap_future(release)
        finished.set()

    async def failed():
        await asyncio.sleep(0)
        raise ValueError("batch failure")

    async def batch():
        await asyncio.gather(sibling(), failed())

    handle = stage.go(batch)
    assert entered.wait(2)
    with pytest.raises(ValueError, match="batch failure"):
        handle.get(timeout=2)
    try:
        with pytest.raises(TimeoutError):
            handle.wait_settled(timeout=0.01)
        assert not finished.is_set()
    finally:
        release.set_result(None)
        handle.wait_settled(timeout=2)
        stage.close(timeout=2)
    assert finished.is_set()
