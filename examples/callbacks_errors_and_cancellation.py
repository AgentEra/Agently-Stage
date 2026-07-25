from __future__ import annotations

import asyncio
import threading

from agently_stage import Stage, StageSettlementError

# Expected key output from a real local run:
# callbacks=['success:42', 'finally']
# body_error=ValueError
# settlement_error=RuntimeError
# cancelled=True
# descendant_cancelled=True


def main() -> None:
    callbacks: list[str] = []
    callback_stage = Stage()
    callback_handle = (
        callback_stage.go(lambda: 42)
        .on_success(lambda value: callbacks.append(f"success:{value}"))
        .on_finally(lambda: callbacks.append("finally"))
    )
    callback_handle.get()
    callback_handle.wait_settled()
    callback_stage.close()

    def fail_body() -> None:
        raise ValueError("body failed")

    body_stage = Stage()
    body_handle = body_stage.go(fail_body)
    try:
        body_handle.get()
    except ValueError as error:
        body_error = type(error).__name__
    body_handle.wait_settled()
    body_stage.close()

    def fail_callback(value: int) -> None:
        raise RuntimeError(f"callback failed for {value}")

    settlement_stage = Stage()
    settlement_handle = settlement_stage.go(lambda: 42).on_success(fail_callback)
    settlement_handle.get()
    try:
        settlement_handle.wait_settled()
    except StageSettlementError as error:
        settlement_error = type(error.errors[0]).__name__
    try:
        settlement_stage.close()
    except StageSettlementError:
        pass

    cancellation_started = threading.Event()
    descendant_cancelled_event = threading.Event()

    async def wait_forever() -> None:
        async def descendant() -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                descendant_cancelled_event.set()
                raise

        asyncio.create_task(descendant())
        cancellation_started.set()
        await asyncio.Event().wait()

    cancellation_stage = Stage()
    cancellation_handle = cancellation_stage.go(wait_forever)
    assert cancellation_started.wait(timeout=1)
    cancelled = cancellation_handle.cancel(timeout=1)
    cancellation_handle.wait_settled(timeout=1)
    descendant_cancelled = descendant_cancelled_event.is_set()
    cancellation_stage.close()

    print(f"callbacks={callbacks}")
    print(f"body_error={body_error}")
    print(f"settlement_error={settlement_error}")
    print(f"cancelled={cancelled}")
    print(f"descendant_cancelled={descendant_cancelled}")


if __name__ == "__main__":
    main()
