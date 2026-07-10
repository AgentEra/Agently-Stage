from __future__ import annotations

import subprocess
import sys
import textwrap


def _run_script(source: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        check=False,
        capture_output=True,
        cwd=".",
        text=True,
        timeout=5,
    )


def test_process_waits_for_retained_stage_work() -> None:
    result = _run_script(
        """
        import asyncio
        from agently_stage import Stage

        async def root():
            async def child():
                await asyncio.sleep(0.05)
                print("child-finished")

            asyncio.create_task(child())
            return "body-finished"

        print(Stage().get(root))
        """
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["body-finished", "child-finished"]
    assert "Task was destroyed" not in result.stderr
    assert "RuntimeWarning" not in result.stderr


def test_user_asyncio_run_works_before_and_after_stage() -> None:
    result = _run_script(
        """
        import asyncio
        from agently_stage import Stage

        async def value(number):
            await asyncio.sleep(0)
            return number

        print(asyncio.run(value(1)))
        print(Stage().get(value, 2))
        print(asyncio.run(value(3)))
        """
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["1", "2", "3"]
    assert result.stderr == ""


def test_empty_stage_script_exits_without_shutdown_hook() -> None:
    result = _run_script(
        """
        from agently_stage import Stage

        Stage()
        print("exited")
        """
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["exited"]
    assert result.stderr == ""


def test_multiple_generations_finish_before_process_exit() -> None:
    result = _run_script(
        """
        import time
        from agently_stage import Stage

        stage = Stage()
        first = stage.go(lambda: "first")
        print(first.get())
        first.wait_settled()
        time.sleep(0.02)
        second = stage.go(lambda: "second")
        print(second.get())
        """
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["first", "second"]
    assert "RuntimeWarning" not in result.stderr
