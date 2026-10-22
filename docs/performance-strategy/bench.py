"""Synthetic infrastructure workloads, exact results, no model/network calls.

Each invocation executes exactly one case. suite.py isolates and randomizes cases.
"""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures as cf
import contextvars
import ctypes
import hashlib
import json
import multiprocessing
import os
import platform
import resource
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from candidates import ReplayTunnel, WakeTunnel  # noqa: E402 - script-local imports after repository bootstrap

from agently_stage import Stage, StageSettlementError, Tunnel  # noqa: E402 - import the selected checkout

MASK = (1 << 64) - 1


def quantiles(values):
    ordered = sorted(values)
    if not ordered:
        return {}
    return {f"p{p}_ms": ordered[min(len(ordered) - 1, int((len(ordered) - 1) * p / 100))] * 1000 for p in (50, 95, 99)}


def usage():
    # Children are reaped only after the measured interval. Their CPU is added
    # by explicit live-worker snapshots in compute(), not RUSAGE_CHILDREN.
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime, r.ru_nvcsw, r.ru_nivcsw


class Meter:
    def __init__(self):
        self.cpu, self.voluntary, self.involuntary = usage()
        self.start = time.perf_counter()

    def finish(self, count, **extra):
        wall = time.perf_counter() - self.start
        cpu, voluntary, involuntary = usage()
        import psutil

        result = {
            "wall_s": wall,
            "cpu_s": cpu - self.cpu,
            "count": count,
            "throughput": count / wall,
            "cpu_per_op_us": (cpu - self.cpu) * 1e6 / count,
            "average_cores": (cpu - self.cpu) / wall,
            "voluntary_switches": voluntary - self.voluntary,
            "involuntary_switches": involuntary - self.involuntary,
            "rss_endpoint_bytes": psutil.Process().memory_info().rss,
        }
        result.update(extra)
        return result


def kernel(seed, iterations):
    x = seed + 1
    for _ in range(iterations):
        x = ((x ^ (x >> 7)) * 6364136223846793005 + 1) & MASK
    return x


def hash_kernel(seed, iterations):
    return hashlib.pbkdf2_hmac("sha256", str(seed).encode(), b"stage-fixed-input", iterations)


def native_library(language):
    lib = ctypes.CDLL(str(Path(__file__).parent / "build" / f"{language}.dylib"))
    lib.kernel.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
    lib.kernel.restype = ctypes.c_uint64
    lib.batch.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
    lib.batch.restype = ctypes.c_uint64
    return lib


def compute(case):
    kind, workers, iterations, count = case["kind"], case["workers"], case["iterations"], case["count"]
    func = hash_kernel if kind == "hash" else kernel
    if kind in ("rust", "go"):
        lib = native_library(kind)

        # Same adapter in direct-thread and Stage arms. Stage 0.3.8's callable
        # classifier recurses on a bare ctypes function (first-run evidence).
        def native_call(seed, steps):
            return lib.kernel(seed, steps)

        func = native_call
    expected = [func(i, iterations) for i in range(count)]
    mode = case["mode"]
    started = time.perf_counter()
    pool = (
        cf.ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn"))
        if mode == "process"
        else cf.ThreadPoolExecutor(workers)
    )
    # Start every worker via overlapping warmup. Parent and child warmup excluded.
    list(pool.map(time.sleep, [0.03] * (workers * 2)))
    import psutil

    children = psutil.Process().children(recursive=True) if mode == "process" else []
    before = sum(sum(p.cpu_times()[:2]) for p in children)
    setup_s = time.perf_counter() - started
    if mode == "stage":

        async def run():
            stage = Stage(executor=pool)
            meter = Meter()
            values = await asyncio.gather(*(stage.go(func, i, iterations).async_get() for i in range(count)))
            await stage.async_close()
            return values, meter.finish(count)

        values, result = asyncio.run(run())
    else:
        meter = Meter()
        values = list(pool.map(func, range(count), [iterations] * count))
        result = meter.finish(count)
    after = sum(sum(p.cpu_times()[:2]) for p in children)
    result["worker_cpu_s"] = after - before
    result["cpu_s"] += after - before
    result["average_cores"] = result["cpu_s"] / result["wall_s"]
    result["cpu_per_op_us"] = result["cpu_s"] * 1e6 / count
    result["rss_endpoint_bytes"] += sum(p.memory_info().rss for p in children)
    result["pool_setup_s"] = setup_s
    result["worker_count_observed"] = len(children) if mode == "process" else workers
    pool.shutdown()
    assert values == expected
    result["correct"] = True
    result["checksum"] = hashlib.sha256(repr(values).encode()).hexdigest()
    return result


async def dispatch(case):
    count, mode = case["count"], case["mode"]
    delay = case.get("delay", 0)

    async def unit(i):
        await asyncio.sleep(delay)
        return i

    async def batch():
        return await asyncio.gather(*(unit(i) for i in range(count)))

    stage = Stage(loop="stage") if mode.startswith("carrier") else Stage()
    release = cf.Future()

    async def hold():
        await asyncio.wrap_future(release)

    held = stage.go(hold) if mode != "asyncio" else None
    if mode != "asyncio":
        await stage.go(unit, -1).async_get()
    meter = Meter()
    if mode == "asyncio":
        values = await batch()
    elif mode == "carrier_batch":
        values = await stage.go(batch).async_get()
    else:
        values = await asyncio.gather(*(stage.go(unit, i).async_get() for i in range(count)))
    release.set_result(None)
    if held is not None:
        await held.async_get()
    await stage.async_close()
    result = meter.finish(count)
    assert values == list(range(count))
    result["correct"] = True
    return result


async def carrier(case):
    Stage.set_settings("runtime.carrier_loop_count", case["lanes"])
    scopes = [Stage(loop="stage") for _ in range(case["scopes"])]
    # Concurrent roots keep epochs active while the workload is submitted.
    release = cf.Future()

    async def hold():
        await asyncio.wrap_future(release)

    holds = [s.go(hold) for s in scopes]

    async def unit(i):
        if case["kind"] == "cpu":
            result = kernel(i, 1000)
        else:
            await asyncio.sleep(0.001)
            result = i
        return result, threading.get_ident()

    meter = Meter()
    values = await asyncio.gather(*(scopes[i % len(scopes)].go(unit, i).async_get() for i in range(case["count"])))
    result = meter.finish(case["count"], loops_observed=len({v[1] for v in values}))
    release.set_result(None)
    await asyncio.gather(*(h.async_get() for h in holds))
    await asyncio.gather(*(s.async_close() for s in scopes))
    expected = [kernel(i, 1000) if case["kind"] == "cpu" else i for i in range(case["count"])]
    assert [v[0] for v in values] == expected
    result["correct"] = True
    return result


def replay(case):
    n = case["count"]
    tunnel = ReplayTunnel(storage=case["storage"], timeout=None)
    fill = time.perf_counter()
    for i in range(n):
        tunnel.put(i)
    tunnel.close()
    fill_s = time.perf_counter() - fill
    meter = Meter()
    if case["mode"] == "async":

        async def read():
            return [v async for v in tunnel]

        values = asyncio.run(read())
    else:
        values = list(tunnel)
    result = meter.finish(n, fill_s=fill_s)
    assert values == list(range(n))
    result["correct"] = True
    return result


async def broadcast(case):
    n = case["count"]
    tunnel = WakeTunnel(wake=case["wake"], timeout=None)
    subscriptions = [tunnel.subscribe(start="earliest", timeout=None) for _ in range(case["readers"])]
    latencies = []

    async def consumer(sub):
        values = []
        async for i, due in sub:
            values.append(i)
            latencies.append(time.perf_counter() - due)
        return values

    tasks = [asyncio.create_task(consumer(sub)) for sub in subscriptions]
    await asyncio.sleep(0)
    interval = case.get("interval", 0)
    start = time.perf_counter() + 0.01 if interval else time.perf_counter()

    def sync_produce():
        for i in range(n):
            due = start + i * interval if interval else time.perf_counter()
            if interval:
                time.sleep(max(0, due - time.perf_counter()))
            tunnel.put((i, due))
        tunnel.close()

    async def async_produce():
        for i in range(n):
            due = start + i * interval if interval else time.perf_counter()
            if interval:
                await asyncio.sleep(max(0, due - time.perf_counter()))
            tunnel.put((i, due))
            if not interval:
                await asyncio.sleep(0)
        tunnel.close()

    meter = Meter()
    if case["producer"] == "thread":
        await asyncio.to_thread(sync_produce)
    else:
        await async_produce()
    values = await asyncio.gather(*tasks)
    result = meter.finish(n * case["readers"], **quantiles(latencies))
    assert all(v == list(range(n)) for v in values)
    result.update(
        correct=True, notifications=tunnel.notifications, resolutions=tunnel.resolutions, latencies_s=latencies
    )
    return result


async def mixed(case):
    # Both variants have four workers; one pool vs 3+1 pools changes allocation.
    slow_pool = cf.ThreadPoolExecutor(3 if case["mode"] == "split" else 4)
    fast_pool = cf.ThreadPoolExecutor(1) if case["mode"] == "split" else slow_pool
    slow = Stage(executor=slow_pool)
    fast = Stage(executor=fast_pool)
    await asyncio.gather(slow.go(time.sleep, 0.001).async_get(), fast.go(time.sleep, 0.001).async_get())
    meter = Meter()
    background = [slow.go(time.sleep, 0.03) for _ in range(32)]
    start = time.perf_counter()

    async def request(i):
        due = start + i * 0.002
        await asyncio.sleep(max(0, due - time.perf_counter()))
        await fast.go(time.sleep, 0.0005).async_get()
        return time.perf_counter() - due

    latencies = await asyncio.gather(*(request(i) for i in range(100)))
    await asyncio.gather(*(h.async_get() for h in background))
    await slow.async_close()
    await fast.async_close()
    result = meter.finish(132, **quantiles(latencies), latencies_s=latencies, correct=True)
    slow_pool.shutdown()
    if fast_pool is not slow_pool:
        fast_pool.shutdown()
    return result


def boundary(case):
    lib = native_library(case["language"])
    n, iterations = case["count"], case["iterations"]
    expected = sum(kernel(i, iterations) for i in range(n)) & MASK
    lib.batch(1, iterations)
    meter = Meter()
    if case["mode"] == "batch":
        value = lib.batch(n, iterations)
    else:
        value = sum(lib.kernel(i, iterations) for i in range(n)) & MASK
    result = meter.finish(n)
    assert value == expected
    return dict(result, correct=True, checksum=value)


def callbacks(case):
    lib = native_library("rust")
    callback_type = ctypes.CFUNCTYPE(ctypes.c_uint64, ctypes.c_uint64)
    callback = callback_type(lambda i: kernel(i, case["iterations"]))
    lib.callbacks.argtypes = [callback_type, ctypes.c_uint64, ctypes.c_uint64]
    lib.callbacks.restype = ctypes.c_uint64
    n = case["count"]
    expected = sum(kernel(i, case["iterations"]) for i in range(n)) & MASK
    meter = Meter()
    value = lib.callbacks(callback, n, case["workers"])
    result = meter.finish(n)
    assert value == expected
    return dict(result, correct=True, checksum=value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", help="JSON case")
    args = parser.parse_args()
    case = json.loads(args.case)
    if case.get("loop") == "uvloop":
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    if case["group"] in ("dispatch", "carrier", "broadcast", "mixed"):
        result = asyncio.run(globals()[case["group"]](case))
    else:
        result = globals()[case["group"]](case)
    result.update(
        case=case,
        python=sys.version,
        platform=platform.platform(),
        load_average=os.getloadavg(),
        model_calls=0,
        external_calls=0,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
