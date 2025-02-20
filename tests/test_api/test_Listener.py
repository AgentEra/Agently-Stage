from __future__ import annotations

import time

from agently_stage import Stage, StageListener


def test_reg():
    StageListener.reset()
    StageListener._threading = None
    with Stage() as stage:
        assert StageListener.is_running()
        assert StageListener.has_stage(stage)
        stage.go(lambda: 1 + 1)

    # NOTE: 在关闭的过程中, 会有一定的延迟
    time.sleep(0.1)
    assert not StageListener.is_running()
    assert StageListener._recv_conn is None
    assert StageListener._send_conn is None
