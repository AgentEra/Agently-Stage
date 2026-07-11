from __future__ import annotations

import asyncio
import time

import pytest

from agently_stage import Stage

from .test_base import Counter


def test_with_outclose():
    counter = Counter()

    with Stage() as stage:

        async def async_task(value: str):
            counter.increment(f"async_task start {value}")
            await asyncio.sleep(1)
            counter.increment(f"async_task end {value}")

        def sync_task(value: str):
            counter.increment(f"sync_task start {value}")
            time.sleep(2)
            counter.increment(f"sync_task end {value}")

        async_response = stage.go(async_task, "1")
        sync_response = stage.go(sync_task, "2")
        assert stage.is_closing is False

    assert stage.is_closing is True
    async_response.get()
    sync_response.get()
    expected_values = [
        "async_task start 1",
        "sync_task start 2",
        "async_task end 1",
        "sync_task end 2",
    ]
    assert all(value in counter.value for value in expected_values)


def test_on_success():
    counter = Counter()

    with Stage() as stage:

        def sync_task(value: str):
            counter.increment(f"sync_task start {value}")
            time.sleep(2)
            counter.increment(f"sync_task end {value}")
            return counter

        async def async_on_success(res):
            await asyncio.sleep(0)
            counter.increment("on_success 2")

        async_response = stage.go(sync_task, "1", on_success=lambda res: res.increment("on_success 1"))
        stage.go(sync_task, "2", on_success=async_on_success)
        assert "on_success 1" not in counter.value
        assert "on_success 2" not in counter.value
        assert "sync_task end 1" not in counter.value
        assert "sync_task end 2" not in counter.value
        assert stage.is_closing is False

    assert stage.is_closing is True
    async_response.get()
    expected_values = [
        "sync_task start 1",
        "sync_task end 1",
        "on_success 1",
        "sync_task start 2",
        "sync_task end 2",
        "on_success 2",
    ]
    time.sleep(0.1)
    assert all(value in counter.value for value in expected_values)


def test_async_on_success():
    counter = Counter()

    with Stage() as stage:

        async def async_task(value: str):
            counter.increment(f"sync_task start {value}")
            await asyncio.sleep(2)
            counter.increment(f"sync_task end {value}")
            return counter

        async def async_on_success(res):
            await asyncio.sleep(0)
            res.increment(f"on_success {1}")

        async_response = stage.go(async_task, "1", on_success=async_on_success)
        assert stage.is_closing is False

    assert stage.is_closing is True
    async_response.get()
    expected_values = [
        "sync_task start 1",
        "sync_task end 1",
        "on_success 1",
    ]
    time.sleep(0.1)
    assert all(value in counter.value for value in expected_values)


def test_on_error():
    counter = Counter()

    with Stage() as stage:

        def sync_task() -> Counter:
            counter.increment("sync_task start")
            raise Exception("sync_task error")
            counter.increment("sync_task end")
            return counter

        def handle_error(e):
            assert str(e) == "sync_task error"
            counter.increment("handle_error")

        async_response = stage.go(
            sync_task, on_success=lambda res: res.increment("on_success 1"), on_error=handle_error
        )

        async_response_ignore = stage.go(
            sync_task, on_success=lambda res: res.increment("on_success 1"), ignore_exception=True
        )

        assert stage.is_closing is False

    assert stage.is_closing is True
    with pytest.raises(Exception, match="sync_task error"):
        async_response.get()
    async_response_ignore.get()

    time.sleep(0.1)
    res = ["sync_task start", "handle_error", "sync_task start"]
    assert all(value in counter.value for value in res)


def test_async_on_error():
    counter = Counter()

    with Stage() as stage:

        async def async_sync_task():
            counter.increment("async_task start")
            await asyncio.sleep(0)
            raise Exception("async_task error")
            counter.increment("async_task end")
            return counter

        async def handle_error(e):
            await asyncio.sleep(0)
            assert str(e) == "async_task error"
            counter.increment("handle_error")

        async def long_task():
            await asyncio.sleep(2)
            counter.increment("long_task")

        async_response = stage.go(
            async_sync_task, on_success=lambda res: res.increment(f"on_success {1}"), on_error=handle_error
        )
        stage.get(long_task)

        assert stage.is_closing is False

    assert stage.is_closing is True
    with pytest.raises(Exception, match="async_task error"):
        async_response.get()

    time.sleep(0.1)
    res = ["async_task start", "handle_error", "long_task"]
    assert all(value in counter.value for value in res)


def test_on_finally():
    counter = Counter()

    with Stage() as stage:

        def sync_task(value: str):
            counter.increment(f"sync_task start {value}")
            time.sleep(2)
            counter.increment(f"sync_task end {value}")
            return counter

        def handle_finally():
            counter.increment("on_finally 1")

        async_response = stage.go(sync_task, "1", on_finally=handle_finally)
        assert stage.is_closing is False

    assert stage.is_closing is True
    async_response.get()
    expected_values = [
        "sync_task start 1",
        "sync_task end 1",
        "on_finally 1",
    ]
    time.sleep(0.1)
    assert all(value in counter.value for value in expected_values)


def test_async_on_finally():
    counter = Counter()

    with Stage() as stage:

        async def async_task(value: str):
            counter.increment(f"sync_task start {value}")
            time.sleep(2)
            counter.increment(f"sync_task end {value}")
            return counter

        def handle_finally():
            counter.increment("on_finally 1")

        async_response = stage.go(async_task, "1", on_finally=handle_finally)
        assert stage.is_closing is False

    assert stage.is_closing is True
    async_response.get()
    expected_values = [
        "sync_task start 1",
        "sync_task end 1",
        "on_finally 1",
    ]
    time.sleep(0.1)
    assert all(value in counter.value for value in expected_values)


def test_all_callbacks():
    counter = Counter()

    with Stage() as stage:

        def sync_task(value: str):
            counter.increment(f"sync_task start {value}")
            time.sleep(2)
            counter.increment(f"sync_task end {value}")
            return counter

        def handle_success(res):
            res.increment(f"on_success {1}")

        def handle_error(e):
            assert str(e) == "sync_task error"

        def handle_finally():
            counter.increment("on_finally 1")

        async_response = stage.go(
            sync_task, "1", on_success=handle_success, on_error=handle_error, on_finally=handle_finally
        )
        assert stage.is_closing is False

    assert stage.is_closing is True
    async_response.get()
    expected_values = [
        "sync_task start 1",
        "sync_task end 1",
        "on_success 1",
        "on_finally 1",
    ]
    time.sleep(0.1)
    assert all(value in counter.value for value in expected_values)
