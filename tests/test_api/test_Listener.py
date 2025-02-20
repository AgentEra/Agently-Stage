from __future__ import annotations

import time

import pytest

from agently_stage import Stage, StageListener


@pytest.fixture
def reset():
    StageListener.reset()
    yield
    StageListener.reset()


def test_reg():
    StageListener.reset()

    with Stage() as stage:
        assert StageListener.is_running()
        assert StageListener.has_stage(stage)
        print(StageListener.get_tack_dict().keys())
        stage.go(lambda: 1 + 1)

    # NOTE: 在关闭的过程中, 会有一定的延迟
    time.sleep(0.1)
    assert not StageListener.is_running()
    assert StageListener._recv_conn is None
    assert StageListener._send_conn is None


if __name__ == "__main__":
    test_reg()
