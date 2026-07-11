from __future__ import annotations

import asyncio
import time

from agently_stage import Stage, Tunnel


def test_put_get():
    tunnel = Tunnel()
    tunnel.put(1)
    tunnel.put(1)
    tunnel.put_stop()
    assert tunnel.get() == [1, 1]


def test_not_get():
    tunnel = Tunnel(timeout=1)
    tunnel.put(1)
    # NOTE: 如果没有正常结束，说明有问题


def test_put_get_timeout():
    tunnel = Tunnel(timeout=1)
    tunnel.put(1)
    assert tunnel.get() == [1]
    # NOTE: 如果没有正常结束，说明有问题


def test_sync_async_iter():
    order_execution = []
    res = []
    tunnel = Tunnel()
    with Stage() as stage:

        def consumer():
            order_execution.append("consumer")
            for data in tunnel:
                res.append(f"sync_consumer: {data}")

        async def async_consumer():
            order_execution.append("async_consumer")
            async for data in tunnel:
                res.append(f"async_consumer: {data}")

        def provider(n: int):
            order_execution.append("provider")
            for i in range(n):
                tunnel.put(i + 1)
            tunnel.put_stop()

        sync_res = stage.go(consumer)
        async_res = stage.go(async_consumer)

        time.sleep(1)
        stage.get(provider, 5)

    sync_res.get()
    async_res.get()
    assert set(order_execution[:2]) == {"consumer", "async_consumer"}
    assert order_execution[-1] == "provider"
    assert [item for item in res if item.startswith("sync_consumer")] == [f"sync_consumer: {i + 1}" for i in range(5)]
    assert [item for item in res if item.startswith("async_consumer")] == [f"async_consumer: {i + 1}" for i in range(5)]


# 测试 async 控制权让出
def test_async_control():
    order_execution = []
    res = []
    tunnel = Tunnel()
    with Stage() as stage:

        def consumer():
            order_execution.append("consumer")
            for data in tunnel:
                res.append(f"sync_consumer: {data}")

        async def async_consumer():
            order_execution.append("async_consumer")
            async for data in tunnel:
                await asyncio.sleep(0.1)
                res.append(f"async_consumer: {data}")

        def provider(n: int):
            order_execution.append("provider")
            for i in range(n):
                tunnel.put(i + 1)
            tunnel.put_stop()

        sync_res = stage.go(consumer)
        async_res = stage.go(async_consumer)

        time.sleep(1)
        stage.get(provider, 5)

    sync_res.get()
    async_res.get()
    assert set(order_execution[:2]) == {"consumer", "async_consumer"}
    assert order_execution[-1] == "provider"
    assert [item for item in res if item.startswith("sync_consumer")] == [f"sync_consumer: {i + 1}" for i in range(5)]
    assert [item for item in res if item.startswith("async_consumer")] == [f"async_consumer: {i + 1}" for i in range(5)]
