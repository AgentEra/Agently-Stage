from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = [
    REPOSITORY_ROOT / "examples" / "runtime_foundation.py",
    REPOSITORY_ROOT / "examples" / "basic_sync_async.py",
    REPOSITORY_ROOT / "examples" / "body_result_and_background_drain.py",
    REPOSITORY_ROOT / "examples" / "generation_and_pinned_context.py",
    REPOSITORY_ROOT / "examples" / "callbacks_errors_and_cancellation.py",
    REPOSITORY_ROOT / "examples" / "tunnel_broadcast.py",
    REPOSITORY_ROOT / "examples" / "stage_stream.py",
    REPOSITORY_ROOT / "examples" / "event_emitter.py",
    REPOSITORY_ROOT / "examples" / "automatic_process_exit.py",
]
EXPECTED_OUTPUT_MARKER = "# Expected key output from a real local run:"


def read_expected_output(example: Path) -> list[str]:
    lines = example.read_text(encoding="utf-8").splitlines()
    marker_index = lines.index(EXPECTED_OUTPUT_MARKER)
    expected: list[str] = []
    for line in lines[marker_index + 1 :]:
        if not line.startswith("# "):
            break
        expected.append(line.removeprefix("# "))
    assert expected, f"{example} has no recorded expected output"
    return expected


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda path: path.stem)
def test_example_matches_recorded_key_output(example: Path) -> None:
    expected = read_expected_output(example)
    result = subprocess.run(
        [sys.executable, str(example)],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.splitlines() == expected
