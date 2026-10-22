"""Run sequential isolated cases; never overwrite evidence or silently skip failure."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def cases():
    out = []

    def add(group, **kwargs):
        out.append(dict(group=group, **kwargs))

    for delay in (0, 0.001):
        for mode in ("asyncio", "caller", "carrier_each", "carrier_batch"):
            add("dispatch", count=2000, delay=delay, mode=mode)
    for mode in ("asyncio", "caller"):
        add("dispatch", count=2000, delay=0, mode=mode, loop="uvloop")
    for lanes in (1, 2, 4):
        for scopes in (1, 16):
            for kind in ("io", "cpu"):
                add("carrier", lanes=lanes, scopes=scopes, kind=kind, count=1000)
    for kind, iterations, count in (("python", 64, 256), ("python", 100000, 32), ("hash", 50000, 32)):
        for mode in ("thread", "stage", "process"):
            for workers in (1, 2, 4, 8):
                add("compute", kind=kind, iterations=iterations, count=count, mode=mode, workers=workers)
    for n in (1000, 10000, 100000):
        for storage in ("deque", "list", "chunk"):
            for mode in ("sync", "async"):
                add("replay", count=n, storage=storage, mode=mode)
    for readers in (1, 8, 32):
        for wake in ("baseline", "grouped", "local"):
            for producer in ("loop", "thread"):
                for interval in (0, 0.001):
                    add(
                        "broadcast",
                        count=300 if interval else 1500,
                        readers=readers,
                        wake=wake,
                        producer=producer,
                        interval=interval,
                    )
    for mode in ("shared", "split"):
        add("mixed", mode=mode)
    for language in ("rust", "go"):
        for mode in ("each", "batch"):
            add("boundary", language=language, mode=mode, count=50000, iterations=1)
        for mode in ("thread", "stage"):
            for workers in (1, 4):
                add("compute", kind=language, iterations=5000000, count=32, mode=mode, workers=workers)
    for workers in (1, 4):
        add("callbacks", workers=workers, iterations=20000, count=64)
    return out


def case_id(case):
    return case["group"] + "-" + hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()[:12]


def run(command):
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--groups", default="")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--native-only", action="store_true")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    selected = [c for c in cases() if not a.groups or c["group"] in a.groups.split(",")]
    if a.native_only:
        selected = [c for c in selected if c.get("kind") in ("rust", "go") or c["group"] in ("boundary", "callbacks")]
    if a.smoke:
        first = {}
        for c in selected:
            first.setdefault(c["group"], c)
        selected = list(first.values())
    manifest = {
        "schema": 1,
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "baseline": run(["git", "rev-parse", "HEAD"]),
        "branch": run(["git", "branch", "--show-current"]),
        "python": sys.version,
        "executable": sys.executable,
        "machine": run(["uname", "-a"]),
        "hardware": run(["sysctl", "-n", "hw.model", "hw.logicalcpu", "hw.physicalcpu", "hw.memsize"]),
        "repetitions": a.repeats,
        "seed": 20261022,
        "cases": selected,
        "psutil": importlib.metadata.version("psutil"),
        "uvloop": importlib.metadata.version("uvloop"),
        "source_hashes": {
            str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in list((ROOT / "agently_stage").glob("*.py")) + list(HERE.glob("*.py")) + list(HERE.glob("native.*"))
        },
        "kind": "synthetic-infrastructure",
        "model_calls": 0,
        "external_calls": 0,
        "limits": "non-isolated workstation; no CPU affinity; GC enabled; no production capacity claim",
    }
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (a.out / "source").mkdir()
    for filename in ("bench.py", "suite.py", "candidates.py", "native.rs", "native.go", "PLAN.md"):
        shutil.copyfile(HERE / filename, a.out / "source" / filename)
    failures = 0
    total = len(selected) * a.repeats
    index = 0
    with (a.out / "schedule.jsonl").open("w") as schedule:
        for repeat in range(a.repeats):
            order = selected.copy()
            random.Random(20261022 + repeat).shuffle(order)
            for case in order:
                identifier = case_id(case)
                record = {
                    "id": identifier,
                    "repeat": repeat,
                    "case": case,
                    "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                schedule.write(json.dumps(record) + "\n")
                schedule.flush()
                started = time.perf_counter()
                try:
                    process = subprocess.run(
                        [sys.executable, str(HERE / "bench.py"), json.dumps(case)],
                        cwd=ROOT,
                        capture_output=True,
                        text=True,
                        timeout=90,
                        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                    )
                    record.update(
                        returncode=process.returncode,
                        stderr=process.stderr,
                        subprocess_wall_s=time.perf_counter() - started,
                    )
                    if process.returncode:
                        record.update(status="failed", stdout=process.stdout)
                        failures += 1
                    else:
                        record.update(status="valid", result=json.loads(process.stdout))
                except (subprocess.TimeoutExpired, json.JSONDecodeError) as error:
                    record.update(status="failed", error=str(error), subprocess_wall_s=time.perf_counter() - started)
                    failures += 1
                (a.out / f"{identifier}-r{repeat}.json").write_text(json.dumps(record, indent=2))
                index += 1
                print(f"{index}/{total} {identifier} r{repeat} {record['status']}", flush=True)
    (a.out / "completion.json").write_text(
        json.dumps(
            {
                "total": total,
                "failures": failures,
                "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
            indent=2,
        )
    )
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
