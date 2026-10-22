from __future__ import annotations

import asyncio
import concurrent.futures as cf
import contextvars
import ctypes
import random
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest
from bench import kernel, native_library
from candidates import ChunkStore, ReplayTunnel, WakeTunnel

from agently_stage import Stage, TunnelLagError


def test_chunk_store_random_model():
    rng = random.Random(20261022)
    store = ChunkStore(7)
    model = []
    for i in range(20000):
        if model and rng.random() < 0.48:
            assert store.popleft() == model.pop(0)
        else:
            store.append(i)
            model.append(i)
        assert len(store) == len(model)
        if model:
            index = rng.randrange(len(model))
            assert store[index] == model[index]
            assert store[-1] == model[-1]
    assert list(store) == model


@pytest.mark.parametrize("storage", ["deque", "list", "chunk"])
def test_replay_independent_readers_and_failure(storage):
    channel = ReplayTunnel(storage, timeout=None)
    first = channel.subscribe()
    for i in range(2000):
        channel.put(i)
    second = channel.subscribe(start=1500)
    channel.fail(ValueError("terminal"))
    assert [next(first) for _ in range(2000)] == list(range(2000))
    assert [next(second) for _ in range(500)] == list(range(1500, 2000))
    with pytest.raises(ValueError, match="terminal"):
        next(first)
    with pytest.raises(ValueError, match="terminal"):
        next(second)


@pytest.mark.parametrize("storage", ["deque", "chunk"])
def test_bounded_eviction(storage):
    channel = ReplayTunnel(storage, max_history=300, timeout=None)
    old = channel.subscribe()
    for i in range(2000):
        channel.put(i)
    assert channel.retained_range == (1700, 2000)
    with pytest.raises(TunnelLagError):
        next(old)
    channel.close()
    assert list(channel) == list(range(1700, 2000))


@pytest.mark.parametrize("wake", ["baseline", "grouped", "local"])
def test_cross_loop_broadcast_and_cancel(wake):
    channel = WakeTunnel(wake, timeout=None)
    ready = threading.Barrier(3)

    def reader():
        async def read():
            sub = channel.subscribe()
            ready.wait(timeout=3)
            return [x async for x in sub]

        return asyncio.run(read())

    with cf.ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(reader) for _ in range(2)]
        ready.wait(timeout=3)
        for i in range(10000):
            channel.put(i)
        channel.close()
        assert all(f.result(timeout=10) == list(range(10000)) for f in futures)

    async def cancelled():
        c = WakeTunnel(wake, timeout=None)
        sub = c.subscribe()
        task = asyncio.create_task(sub.__anext__())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        c.put(1)
        c.close()
        assert [x async for x in c] == [1]
        assert not c._async_waiters

    asyncio.run(cancelled())


def test_stage_context_settlement_and_blocking_cancel():
    async def run():
        marker = contextvars.ContextVar("test_marker", default="empty")
        marker.set("context")
        stage = Stage(max_workers=2)
        assert await stage.go(marker.get).async_get() == "context"
        entered, release = threading.Event(), threading.Event()
        effects = []

        def blocking():
            entered.set()
            release.wait(timeout=5)
            effects.append("finished")

        handle = stage.go(blocking)
        await asyncio.to_thread(entered.wait, 2)
        assert entered.is_set()
        handle.cancel(timeout=0)
        await asyncio.sleep(0.01)
        assert not effects
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await handle.async_get()
        await handle.async_wait_settled()
        assert effects == ["finished"]
        await stage.async_close()

    asyncio.run(run())


@pytest.mark.parametrize("language", ["rust", "go"])
def test_native_kernel_matches_python(language):
    lib = native_library(language)
    for iterations in (0, 1, 7, 1000):
        for seed in range(20):
            assert lib.kernel(seed, iterations) == kernel(seed, iterations)
        assert lib.batch(20, iterations) == sum(kernel(i, iterations) for i in range(20)) % (1 << 64)
