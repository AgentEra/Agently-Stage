"""Recompute tables and paired descriptive differences from raw evidence."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import statistics
from pathlib import Path

METRICS = (
    "wall_s",
    "throughput",
    "cpu_s",
    "cpu_per_op_us",
    "average_cores",
    "rss_endpoint_bytes",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "notifications",
    "resolutions",
    "fill_s",
    "pool_setup_s",
    "loops_observed",
    "subprocess_wall_s",
)


def summarize(folder):
    groups = {}
    failures = []
    for path in sorted(list(folder.glob("*-r*.json")) + list(folder.glob("*-r*.json.gz"))):
        row = json.loads(gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes())
        if row["status"] != "valid":
            failures.append({"file": path.name, "case": row["case"], "error": row.get("stderr", row.get("error"))})
            continue
        assert row["result"]["correct"] is True, path
        row["result"]["subprocess_wall_s"] = row["subprocess_wall_s"]
        groups.setdefault(row["id"], []).append(row)
    summary = []
    for identifier, rows in sorted(groups.items()):
        assert len({r["repeat"] for r in rows}) == len(rows)
        metrics = {}
        for name in METRICS:
            values = [r["result"][name] for r in rows if name in r["result"]]
            if values:
                metrics[name] = {"median": statistics.median(values), "min": min(values), "max": max(values)}
        summary.append(
            {
                "id": identifier,
                "case": rows[0]["case"],
                "repeats": len(rows),
                "metrics": metrics,
                "runs": {
                    str(r["repeat"]): {name: r["result"][name] for name in METRICS if name in r["result"]} for r in rows
                },
            }
        )
    expected = json.loads((folder / "manifest.json").read_text())
    complete = len(groups) == len(expected["cases"]) and all(len(r) == expected["repetitions"] for r in groups.values())
    return {"complete": complete, "failures": failures, "configs": summary}


def compare(data):
    entries = data["configs"]
    lookup = {json.dumps(e["case"], sort_keys=True): e for e in entries}
    comparisons = []
    for candidate in entries:
        c = candidate["case"]
        base = c.copy()
        group = c["group"]
        metric, direction, changed = "wall_s", "lower", None
        if group == "dispatch":
            if "loop" in c:
                del base["loop"]
                changed = "uvloop"
            elif c["mode"] == "carrier_batch":
                base["mode"] = "carrier_each"
                changed = "batch"
            elif c["mode"] == "caller":
                base["mode"] = "asyncio"
                changed = "lifecycle-overhead"
        elif group == "carrier" and c["lanes"] != 1:
            base["lanes"] = 1
            changed = "lanes"
        elif group == "compute":
            if c["workers"] != 1:
                base["workers"] = 1
                changed = "workers"
            elif c["mode"] == "stage":
                base["mode"] = "thread"
                changed = "stage-overhead"
            elif c["mode"] == "process":
                base["mode"] = "thread"
                changed = "process"
        elif group == "replay" and c["storage"] != "deque":
            base["storage"] = "deque"
            changed = "storage"
        elif group == "broadcast" and c["wake"] != "baseline":
            base["wake"] = "baseline"
            changed = "wake"
            metric = "p99_ms" if c["interval"] else "wall_s"
        elif group == "mixed" and c["mode"] == "split":
            base["mode"] = "shared"
            metric, changed = "p99_ms", "pool-allocation"
        elif group == "boundary" and c["mode"] == "batch":
            base["mode"] = "each"
            changed = "ffi-batch"
        elif group == "callbacks" and c["workers"] != 1:
            base["workers"] = 1
            changed = "native-python-callback-workers"
        if not changed:
            continue
        baseline = lookup.get(json.dumps(base, sort_keys=True))
        if baseline is None:
            continue
        paired = [
            (1 - candidate["runs"][r][metric] / baseline["runs"][r][metric]) * 100
            for r in candidate["runs"]
            if r in baseline["runs"]
        ]
        median = statistics.median(paired)
        comparisons.append(
            {
                "candidate": candidate["id"],
                "baseline": baseline["id"],
                "change": changed,
                "metric": metric,
                "lower_is_better": True,
                "paired_improvement_percent": paired,
                "paired_median_improvement_percent": median,
                "improved_rounds": sum(x > 0 for x in paired),
                "rounds": len(paired),
            }
        )
    return comparisons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    data = summarize(args.folder)
    data["paired_comparisons"] = compare(data)
    (args.folder / "summary.json").write_text(json.dumps(data, indent=2))
    lines = [
        "# 全配置描述统计",
        "",
        "自动复算；筛选决策由报告解释，不由脚本自动认定。区间为五轮极值，非置信区间。",
        "",
        "| ID / 配置 | wall ms（中位/最小–最大） | CPU ms | 平均核数 | P99 ms |",
        "|---|---:|---:|---:|---:|",
    ]
    for e in data["configs"]:
        m = e["metrics"]
        w = m["wall_s"]
        p99 = str(round(m["p99_ms"]["median"], 3)) if "p99_ms" in m else "—"
        lines.append(
            f"| {e['id']} `{json.dumps(e['case'], sort_keys=True)}` | {w['median'] * 1000:.3f} / {w['min'] * 1000:.3f}–{w['max'] * 1000:.3f} | {m['cpu_s']['median'] * 1000:.3f} | {m['average_cores']['median']:.2f} | {p99} |"
        )
    (args.folder / "TABLES.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps({"complete": data["complete"], "configs": len(data["configs"]), "failures": len(data["failures"])})
    )


if __name__ == "__main__":
    main()
