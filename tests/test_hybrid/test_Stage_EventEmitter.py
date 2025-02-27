from __future__ import annotations

import pytest

from agently_stage import EventEmitter, Stage


@pytest.mark.skip(reason="Something wrong when go out of with context that may cause on going tasks stuck.")
def test_with_stage_eventemitter():
    emitter = EventEmitter()

    async def listener(data):
        print(f"I got: {data}")
        # You can return value to emitter
        return True

    emitter.on("data", listener)

    with Stage() as stage:
        # Submit task that wait to run later
        stage.go(lambda: emitter.emit("data", "EventEmitter is Cool!"))

    responses = emitter.emit("data", "I'll say it again, EventEmitter is Cool!")

    # Get responses from all event listeners
    for response in responses:
        assert response.get()


@pytest.mark.skip(reason="Something wrong when go out of with context that may cause on going tasks stuck.")
def test_stage_eventemitter():
    stage = Stage()
    emitter = EventEmitter()

    async def listener(data):
        print(f"I got: {data}")
        # You can return value to emitter
        return True

    emitter.on("data", listener)

    # Submit task that wait to run later
    stage.go(lambda: emitter.emit("data", "EventEmitter is Cool!"))

    responses = emitter.emit("data", "I'll say it again, EventEmitter is Cool!")

    # Get responses from all event listeners
    for response in responses:
        assert response.get()

    stage.close()
