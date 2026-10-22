"""Independent-process paired baseline/candidate measurements; no model calls.

python compare.py BASELINE_PACKAGE_ROOT CANDIDATE_PACKAGE_ROOT OUTPUT_DIRECTORY
Uses this interpreter; five pairs with alternating order, raw observations kept.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path


def measure(root, case):
    sys.path.insert(0, root)
    from agently_stage import Tunnel

    source = Path(sys.modules[Tunnel.__module__].__file__)
    options = {"timeout": None, "max_history": case.get("limit")}
    if case["variant"] == "grouped":
        options["wake_mode"] = "grouped"
    tunnel = Tunnel(**options)
    count = case["count"]
    cpu = time.process_time()
    start = time.perf_counter()
    if case["kind"] == "replay":
        for value in range(count):
            tunnel.put(value)
        tunnel.close()
        fill = time.perf_counter() - start
        start = time.perf_counter()
        if case["mode"] == "async":

            async def read():
                return [value async for value in tunnel]

            values = asyncio.run(read())
        else:
            values = list(tunnel)
        wall = time.perf_counter() - start
        expected = list(range(max(0, count - (case.get("limit") or count)), count))
        assert values == expected
        result = {"wall_s": wall, "fill_s": fill}
    else:

        async def run():
            latencies = []

            async def reader():
                values = []
                async for value, due in tunnel:
                    values.append(value)
                    latencies.append(time.perf_counter() - due)
                assert values == list(range(count))

            tasks = [asyncio.create_task(reader()) for _ in range(case["readers"])]
            await asyncio.sleep(0)
            interval = case["interval"]
            due_start = time.perf_counter() + (0.01 if interval else 0)

            def produce():
                for value in range(count):
                    due = due_start + value * interval if interval else time.perf_counter()
                    if interval:
                        time.sleep(max(0, due - time.perf_counter()))
                    tunnel.put((value, due))
                tunnel.close()

            started = time.perf_counter()
            if case["producer"] == "thread":
                await asyncio.to_thread(produce)
            else:
                for value in range(count):
                    due = due_start + value * interval if interval else time.perf_counter()
                    if interval:
                        await asyncio.sleep(max(0, due - time.perf_counter()))
                    tunnel.put((value, due))
                    if not interval:
                        await asyncio.sleep(0)
                tunnel.close()
            await asyncio.gather(*tasks)
            return {
                "wall_s": time.perf_counter() - started,
                "latencies_s": latencies,
                "p99_s": sorted(latencies)[int((len(latencies) - 1) * 0.99)],
            }

        result = asyncio.run(run())
    result.update(
        cpu_s=time.process_time() - cpu,
        correct=True,
        python=sys.version,
        platform=platform.platform(),
        source=str(source),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        case=case,
    )
    return result


def compare(baseline, candidate, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    for count in (1000, 10000, 100000):
        for mode in ("sync", "async"):
            cases.append({"kind": "replay", "count": count, "mode": mode})
    for limit in (128, 10000):
        cases.append({"kind": "replay", "count": 100000, "limit": limit, "mode": "sync"})
    for readers in (1, 8, 32):
        for producer, interval in (("loop", 0), ("loop", 0.001), ("thread", 0.001)):
            cases.append(
                {"kind": "broadcast", "count": 400, "readers": readers, "producer": producer, "interval": interval}
            )
    summaries = []
    for index, case in enumerate(cases):
        variants = ["baseline", "default"] + (["grouped"] if case["kind"] == "broadcast" else [])
        runs = {variant: [] for variant in variants}
        for repeat in range(5):
            order = variants if repeat % 2 == 0 else list(reversed(variants))
            for variant in order:
                full = dict(case, variant=variant)
                args = [
                    sys.executable,
                    __file__,
                    "--worker",
                    baseline if variant == "baseline" else candidate,
                    json.dumps(full),
                ]
                process = subprocess.run(args, capture_output=True, text=True, timeout=20)
                raw = {
                    "command": args,
                    "returncode": process.returncode,
                    "stderr": process.stderr,
                    "stdout": process.stdout,
                    "repeat": repeat,
                }
                name = f"case-{index:02}-{variant}-{repeat}.json.gz"
                with gzip.open(output / name, "wt") as stream:
                    json.dump(raw, stream)
                if process.returncode:
                    raise RuntimeError(f"Failed run: {name}: {process.stderr}")
                runs[variant].append(json.loads(process.stdout))
        metrics = ["wall_s", "fill_s", "cpu_s"] if case["kind"] == "replay" else ["wall_s", "cpu_s", "p99_s"]
        summary = {"case": case, "metrics": {}}
        for metric in metrics:
            values = {v: [r[metric] for r in runs[v]] for v in variants}
            entry = {
                v: {"values": a, "median": statistics.median(a), "min": min(a), "max": max(a)}
                for v, a in values.items()
            }
            for variant in variants[1:]:
                reference = "default" if variant == "grouped" else "baseline"
                gains = [(old - new) / old * 100 for old, new in zip(values[reference], values[variant], strict=False)]
                entry[variant].update(
                    reference=reference,
                    paired_gain_pct=statistics.median(gains),
                    improvements=sum(g > 0 for g in gains),
                )
            summary["metrics"][metric] = entry
        summaries.append(summary)
        (output / "summary.json").write_text(json.dumps(summaries, indent=2))
        print(f"case {index}: {case}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "--worker":
        print(json.dumps(measure(sys.argv[2], json.loads(sys.argv[3]))))
    else:
        compare(*sys.argv[1:])
