"""Verify archived evidence, repetition coverage, source snapshots and selection."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from suite import case_id

root = Path(__file__).parent
evidence = root / "evidence"
index = json.loads((evidence / "raw-index.json").read_text())
rows = {}
for record in index:
    path = evidence / record["file"]
    packed = path.read_bytes()
    data = gzip.decompress(packed)
    assert hashlib.sha256(packed).hexdigest() == record["sha256_archive"]
    assert hashlib.sha256(data).hexdigest() == record["sha256_uncompressed"]
    rows[record["file"]] = json.loads(data)

selected = []
counts = {}
for run in ("main", "native-adapter"):
    manifest = json.loads((evidence / run / "manifest.json").read_text())
    for relative, digest in manifest["source_hashes"].items():
        saved = evidence / run / "source" / Path(relative).name
        archived = saved.with_suffix(saved.suffix + ".gz")
        source = saved if relative.startswith("docs/") and saved.exists() else root.parents[1] / relative
        data = (
            gzip.decompress(archived.read_bytes())
            if relative.startswith("docs/") and archived.exists()
            else source.read_bytes()
        )
        assert hashlib.sha256(data).hexdigest() == digest, (run, relative)
    runs = [r for p, r in rows.items() if p.startswith(run + "/")]
    assert len(runs) == len(manifest["cases"]) * manifest["repetitions"]
    assert len({(r["id"], r["repeat"]) for r in runs}) == len(runs)
    expected = {(case_id(c), repeat) for c in manifest["cases"] for repeat in range(manifest["repetitions"])}
    assert {(r["id"], r["repeat"]) for r in runs} == expected
    assert all(case_id(r["case"]) == r["id"] for r in runs)
    schedule = [json.loads(line) for line in (evidence / run / "schedule.jsonl").read_text().splitlines()]
    assert {(r["id"], r["repeat"]) for r in schedule} == expected
    valid = [r for r in runs if r["status"] == "valid"]
    assert all(r["result"]["correct"] is True for r in valid)
    counts[run] = {"total": len(runs), "valid": len(valid), "failed": len(runs) - len(valid)}
    for path, r in rows.items():
        if not path.startswith(run + "/"):
            continue
        native = r["case"].get("kind") in ("rust", "go") or r["case"]["group"] in ("boundary", "callbacks")
        if (run == "native-adapter") or not native:
            assert r["status"] == "valid"
            selected.append({"file": path, "id": r["id"], "repeat": r["repeat"]})

assert len(selected) == 640
assert len({(r["id"], r["repeat"]) for r in selected}) == 640
assert len({r["id"] for r in selected}) == 128
output = {
    "raw_archives_verified": len(rows),
    "formal_runs": counts,
    "selected_configs": 128,
    "selected_runs": 640,
    "selection": "main non-native arms + complete native-adapter arms; no cross-run H8 pairing",
    "selected": selected,
}
(evidence / "audit.json").write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps({k: v for k, v in output.items() if k != "selected"}))
