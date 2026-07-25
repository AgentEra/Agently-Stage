from __future__ import annotations

import asyncio
import inspect
import threading

import pytest

from agently_stage import Tunnel
from agently_stage.StageException import TunnelClosedError, TunnelLagError


async def _collect_async(tunnel: Tunnel[int]) -> list[int]:
    return [item async for item in tunnel]


def test_default_timeout_preserves_original_ten_second_safety_posture() -> None:
    timeout = inspect.signature(Tunnel).parameters["timeout"].default
    assert timeout == 10


def test_each_subscriber_replays_the_full_sequence() -> None:
    tunnel: Tunnel[int] = Tunnel()
    tunnel.put(1)
    first = iter(tunnel)
    tunnel.put(2)
    tunnel.close()

    assert list(first) == [1, 2]
    assert list(tunnel) == [1, 2]
    assert tunnel.get() == [1, 2]


def test_bounded_history_replays_only_the_retained_suffix_to_late_readers() -> None:
    tunnel: Tunnel[int] = Tunnel(max_history=3)
    for item in range(5):
        tunnel.put(item)
    tunnel.close()

    assert list(tunnel) == [2, 3, 4]
    assert tunnel.get() == [2, 3, 4]


def test_bounded_history_reports_an_explicit_gap_to_a_slow_reader() -> None:
    tunnel: Tunnel[int] = Tunnel(max_history=2)
    reader = iter(tunnel)

    tunnel.put(0)
    assert next(reader) == 0
    for item in range(1, 5):
        tunnel.put(item)

    with pytest.raises(TunnelLagError) as exc_info:
        next(reader)

    assert exc_info.value.missed_count == 2
    assert exc_info.value.expected_sequence == 1
    assert exc_info.value.available_from == 3


def test_bounded_history_reports_the_same_gap_to_an_async_reader() -> None:
    async def scenario() -> None:
        tunnel: Tunnel[int] = Tunnel(max_history=2)
        reader = tunnel.__aiter__()

        tunnel.put(0)
        assert await anext(reader) == 0
        for item in range(1, 5):
            tunnel.put(item)

        with pytest.raises(TunnelLagError) as exc_info:
            await anext(reader)

        assert exc_info.value.missed_count == 2
        assert exc_info.value.expected_sequence == 1
        assert exc_info.value.available_from == 3

    asyncio.run(scenario())


def test_bounded_history_storage_tracks_capacity_not_total_writes() -> None:
    tunnel: Tunnel[int] = Tunnel(max_history=128)

    for item in range(50_000):
        tunnel.put(item)

    assert len(tunnel._items) == 128
    assert tunnel._base_sequence == 50_000 - 128
    assert tunnel._next_sequence == 50_000


def test_bounded_history_requires_a_positive_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        Tunnel(max_history=0)


def test_async_subscribers_are_woken_without_polling() -> None:
    async def scenario() -> None:
        tunnel: Tunnel[int] = Tunnel()
        first = asyncio.create_task(_collect_async(tunnel))
        second = asyncio.create_task(_collect_async(tunnel))
        await asyncio.sleep(0)

        await tunnel.async_put(1)
        await tunnel.async_put(2)
        await tunnel.async_close()

        assert await first == [1, 2]
        assert await second == [1, 2]

    asyncio.run(scenario())


def test_terminal_failure_follows_accepted_values_for_every_subscriber() -> None:
    tunnel: Tunnel[int] = Tunnel()
    tunnel.put(1)
    tunnel.fail(ValueError("source failed"))

    first = iter(tunnel)
    second = iter(tunnel)
    assert next(first) == 1
    assert next(second) == 1
    with pytest.raises(ValueError, match="source failed"):
        next(first)
    with pytest.raises(ValueError, match="source failed"):
        next(second)


def test_writes_after_terminal_state_fail_deterministically() -> None:
    tunnel: Tunnel[int] = Tunnel()
    tunnel.close()
    tunnel.close()

    with pytest.raises(TunnelClosedError):
        tunnel.put(1)


def test_timeout_ends_only_that_reader() -> None:
    tunnel: Tunnel[int] = Tunnel(timeout=0.01)
    tunnel.put(1)

    assert tunnel.get() == [1]

    tunnel.put(2)
    tunnel.close()
    assert tunnel.get() == [1, 2]


def test_timed_out_reader_does_not_close_tunnel() -> None:
    tunnel: Tunnel[int] = Tunnel(timeout=0.01)

    assert list(tunnel) == []

    tunnel.put(1)
    tunnel.close()
    assert list(tunnel) == [1]


def test_concurrent_producers_publish_one_total_order() -> None:
    tunnel: Tunnel[tuple[int, int]] = Tunnel()

    def produce(producer_id: int) -> None:
        for sequence in range(100):
            tunnel.put((producer_id, sequence))

    threads = [threading.Thread(target=produce, args=(producer_id,)) for producer_id in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    tunnel.close()

    first = list(tunnel)
    second = list(tunnel)
    assert first == second
    assert len(first) == 400
    assert set(first) == {(producer_id, sequence) for producer_id in range(4) for sequence in range(100)}


def test_cancelled_async_reader_does_not_break_later_readers() -> None:
    async def scenario() -> None:
        tunnel: Tunnel[int] = Tunnel()
        cancelled_reader = asyncio.create_task(_collect_async(tunnel))
        await asyncio.sleep(0)
        cancelled_reader.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled_reader

        later_reader = asyncio.create_task(_collect_async(tunnel))
        tunnel.put(1)
        tunnel.close()
        assert await later_reader == [1]

    asyncio.run(scenario())
