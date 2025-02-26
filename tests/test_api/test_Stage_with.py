from __future__ import annotations

import asyncio
import concurrent.futures
import time

import pytest

from agently_stage import Stage


class Counter:
    def __init__(self):
        self.value = []

    def increment(self, value: str):
        self.value.append(value)


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

        async_response = stage.go(sync_task, "1", on_success=lambda res: res.increment(f"on_success {1}"))
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

        def sync_task():
            counter.increment("sync_task start")
            raise Exception("sync_task error")
            counter.increment("sync_task end")
            return counter

        def handle_error(e):
            assert str(e) == "sync_task error"

        async_response = stage.go(
            sync_task, on_success=lambda res: res.increment(f"on_success {1}"), on_error=handle_error
        )

        assert stage.is_closing is False

    assert stage.is_closing is True
    async_response.get()

    time.sleep(0.1)
    assert counter.value == ["sync_task start"]


def test_on_finally():
    counter = Counter()

    with Stage() as stage:

        def sync_task(value: str):
            counter.increment(f"sync_task start {value}")
            time.sleep(2)
            counter.increment(f"sync_task end {value}")
            return counter

        def handle_finally():
            nonlocal counter
            counter.increment(f"on_finally {1}")

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
            nonlocal counter
            counter.increment(f"on_finally {1}")

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


def test_max_workers_error():
    with Stage(max_workers=1) as stage:

        def sync_task(value: str):
            time.sleep(2)
            return value

        with pytest.raises(AssertionError, match="Callback function count: 1, exceeds maximum worker threads: 1"):
            async_response = stage.go(sync_task, "1", on_success=lambda res: res.increment(f"on_success {1}"))


# ========== benchmark ==========

TEST_COUNT = 100


def task_func():
    return 1 + 1


def test_stage_create(benchmark):
    def create_stage():
        res_list = []
        with Stage(max_workers=3) as stage:
            for _ in range(TEST_COUNT):
                res_list.append(stage.go(task_func))

        temp_check_count = 0
        for res in res_list:
            temp_check_count += res.get()

        assert temp_check_count == TEST_COUNT * 2

    benchmark(create_stage)


def test_thread_pool_executor(benchmark):
    def create_ThreadPoolExecutor():
        res_list = []
        # 创建 ThreadPoolExecutor，手动提交任务
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
        # 提交任务
        for _ in range(TEST_COUNT):
            res_list.append(executor.submit(task_func))
        executor.shutdown(wait=False)
        temp_check_count = 0
        for res in res_list:
            temp_check_count += res.result()
        assert temp_check_count == TEST_COUNT * 2

    benchmark(create_ThreadPoolExecutor)
