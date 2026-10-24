from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

import pytest

from agently_stage import Tunnel
from agently_stage.Tunnel import _AsyncWaiter


@pytest.mark.parametrize("mode", ["individual", "grouped"])
@pytest.mark.parametrize("terminal", ["close", "fail"])
def test_multiple_owner_loops_receive_ordered_history(mode: Literal["individual", "grouped"], terminal: str) -> None:
    tunnel: Tunnel[int] = Tunnel(timeout=None, wake_mode=mode)
    ready = [threading.Event(), threading.Event()]

    async def read(index: int) -> list[list[int]]:
        async def consumer() -> list[int]:
            values: list[int] = []
            try:
                async for value in tunnel:
                    values.append(value)
            except ValueError as error:
                assert str(error) == "end"
                assert terminal == "fail"
            else:
                assert terminal == "close"
            return values

        tasks = [asyncio.create_task(consumer()) for _ in range(8)]
        await asyncio.sleep(0)
        ready[index].set()
        return await asyncio.wait_for(asyncio.gather(*tasks), 5)

    def run(index: int) -> list[list[int]]:
        return asyncio.run(read(index), debug=True)

    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(run, i) for i in range(2)]
        assert all(event.wait(3) for event in ready)
        for value in range(100):
            tunnel.put(value)
        if terminal == "fail":
            tunnel.fail(ValueError("end"))
        else:
            tunnel.close()
        for future in futures:
            assert future.result(timeout=6) == [list(range(100))] * 8
    assert not tunnel._async_waiters


@pytest.mark.parametrize("mode", ["individual", "grouped"])
def test_notification_races_cancel_timeout_and_reader_close(mode: Literal["individual", "grouped"]) -> None:
    async def scenario() -> None:
        tunnel: Tunnel[int] = Tunnel(timeout=None, wake_mode=mode)
        readers = [tunnel.subscribe() for _ in range(4)]
        tasks = [asyncio.create_task(anext(reader)) for reader in readers]
        await asyncio.sleep(0)
        tunnel.put(42)  # notification queued but not yet delivered
        tasks[0].cancel()
        readers[1].close()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        with pytest.raises(StopAsyncIteration):
            await tasks[1]
        assert await tasks[2] == await tasks[3] == 42
        with pytest.raises(StopAsyncIteration):
            await anext(tunnel.subscribe(start="latest", timeout=0.001))
        tunnel.put(43)
        tunnel.close()
        tunnel.close()
        assert tunnel.get() == [42, 43]
        assert not tunnel._async_waiters

    asyncio.run(scenario(), debug=True)


@pytest.mark.parametrize("mode", ["individual", "grouped"])
def test_closed_owner_does_not_prevent_other_owner_notification(mode: Literal["individual", "grouped"]) -> None:
    dead_loop = asyncio.new_event_loop()
    dead_future = dead_loop.create_future()
    dead_loop.close()

    async def scenario() -> None:
        tunnel: Tunnel[int] = Tunnel(timeout=None, wake_mode=mode)
        reader = asyncio.create_task(anext(tunnel.subscribe()))
        await asyncio.sleep(0)
        with tunnel._condition:
            tunnel._async_waiters.add(_AsyncWaiter(dead_loop, dead_future))
        await asyncio.to_thread(tunnel.put, 1)
        assert await asyncio.wait_for(reader, 1) == 1
        assert not dead_future.done()  # no foreign-thread mutation
        tunnel.close()

    asyncio.run(scenario(), debug=True)


def test_invalid_mode_is_rejected_and_positional_compatibility_remains() -> None:
    with pytest.raises(ValueError, match="wake_mode"):
        Tunnel(wake_mode="automatic")  # type: ignore[arg-type]
    tunnel: Tunnel[int] = Tunnel(0.1, None, True, 2)
    for value in range(4):
        tunnel.put(value)
    tunnel.close()
    assert tunnel.get() == [2, 3]
