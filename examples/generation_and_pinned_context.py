from __future__ import annotations

import asyncio

from agently_stage import Stage

# Expected key output from a real local run:
# plain_generation_reopened=True
# pinned_loop_reused=True


async def current_loop() -> asyncio.AbstractEventLoop:
    return asyncio.get_running_loop()


def main() -> None:
    plain_stage = Stage()
    first = plain_stage.go(lambda: "first")
    first.get()
    first.wait_settled()
    second = plain_stage.go(lambda: "second")
    second.get()
    second.wait_settled()
    plain_generation_reopened = first.generation_id != second.generation_id
    plain_stage.close()

    with Stage() as pinned_stage:
        first_loop = pinned_stage.get(current_loop)
        second_loop = pinned_stage.get(current_loop)
    pinned_loop_reused = first_loop is second_loop

    print(f"plain_generation_reopened={plain_generation_reopened}")
    print(f"pinned_loop_reused={pinned_loop_reused}")


if __name__ == "__main__":
    main()
