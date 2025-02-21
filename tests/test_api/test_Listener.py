from __future__ import annotations

import time

from agently_stage import Stage, StageListener


def test_with_stage():
    with Stage() as stage:
        assert StageListener.is_running()
        assert StageListener.has_stage(stage)
        res = stage.go(lambda: 1 + 1)

    # NOTE: 在关闭的过程中, 会有一定的延迟
    time.sleep(0.1)
    assert not StageListener.is_running()
    assert not StageListener.has_stage(stage)
    assert stage._dispatch._dispatch_env.loop_thread is None
    assert StageListener._recv_conn is None
    assert StageListener._send_conn is None
    assert res.get() == 2


def test_stage():
    stage = Stage()
    res = stage.go(lambda: 1 + 1)
    assert StageListener.is_running()
    assert StageListener.has_stage(stage)
    stage.close()
    time.sleep(0.1)
    assert not StageListener.is_running()
    assert StageListener._recv_conn is None
    assert StageListener._send_conn is None
    assert res.get() == 2
