from __future__ import annotations

import asyncio

from agently_stage import Stage

# Expected key output from a real local run:
# plain_generation_reopened=True
# auto_backend_reselected=True


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

    auto_stage = Stage()
    carrier_loop = auto_stage.get(current_loop)
    auto_stage.wait_settled(timeout=1)

    async def use_caller_loop() -> bool:
        caller_loop = asyncio.get_running_loop()
        selected_loop = await auto_stage.go(current_loop).async_get()
        return selected_loop is caller_loop and selected_loop is not carrier_loop

    auto_backend_reselected = asyncio.run(use_caller_loop())
    auto_stage.close()

    print(f"plain_generation_reopened={plain_generation_reopened}")
    print(f"auto_backend_reselected={auto_backend_reselected}")


if __name__ == "__main__":
    main()
