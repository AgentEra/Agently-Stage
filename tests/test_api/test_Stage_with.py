from __future__ import annotations

import asyncio
import concurrent.futures
import time

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
