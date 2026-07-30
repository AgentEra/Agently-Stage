import asyncio

from agently_stage import Stage


async def main() -> None:
    completed: list[tuple[str, bool]] = []

    def observe(task: asyncio.Task[object], origin: str) -> None:
        completed.append((origin, task.cancelled()))

    async def owned_work(value: int) -> int:
        await asyncio.sleep(0)
        return value * 2

    stage = Stage(on_adopted_done=observe)
    created = stage.create_task(
        owned_work(21),
        origin="example:created",
        name="stage-created-work",
    )

    existing = asyncio.create_task(owned_work(5))
    assert stage.adopt(existing, origin="example:adopted") is existing

    print(await created)
    print(await existing)
    await stage.async_close(timeout=1)
    print(sorted(completed))


asyncio.run(main())

# Expected key output from a real local run:
# 42
# 10
# [('example:adopted', False), ('example:created', False)]
