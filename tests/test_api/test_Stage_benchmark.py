from __future__ import annotations

import concurrent.futures

from agently_stage import Stage

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
