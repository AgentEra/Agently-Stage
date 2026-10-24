"""Lossless, reproducible gzip archival; verify bytes before removing originals."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

root = Path(__file__).parent / "evidence"
records = []
for folder in ("preflight", "main", "native-adapter"):
    for path in sorted((root / folder).glob("*-r*.json")):
        data = path.read_bytes()
        target = path.with_suffix(".json.gz")
        assert not target.exists(), target
        target.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
        assert gzip.decompress(target.read_bytes()) == data
        path.unlink()
    for path in sorted((root / folder).glob("*-r*.json.gz")):
        data = gzip.decompress(path.read_bytes())
        records.append(
            {
                "file": str(path.relative_to(root)),
                "bytes": len(data),
                "sha256_uncompressed": hashlib.sha256(data).hexdigest(),
                "sha256_archive": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
(root / "raw-index.json").write_text(json.dumps(records, indent=2) + "\n")
print(json.dumps({"files": len(records), "uncompressed_bytes": sum(r["bytes"] for r in records)}))
