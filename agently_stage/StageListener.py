from __future__ import annotations

import threading
from multiprocessing import Pipe
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from multiprocessing.connection import Connection

    from agently_stage import Stage


class StageListener:
    _threading: threading.Thread | None = None
    _lock = threading.Lock()
    _send_conn: Connection[int] | None = None
    _recv_conn: Connection[int] | None = None
    _tack_dict: dict[int, Stage] = {}

    @classmethod
    def processor(cls):
        while stage_id := cls._recv_conn.recv():
            if cls._tack_dict[stage_id]._dispatch._dispatch_env.ready.is_set():
                cls._tack_dict[stage_id].close()
            with cls._lock:
                cls._tack_dict.pop(stage_id)
                print(f"_tack_dict: {cls._tack_dict}")
                if len(cls._tack_dict) == 0:
                    # clean up connections
                    cls._recv_conn.close()
                    cls._send_conn.close()
                    cls._recv_conn = None
                    cls._send_conn = None
                    break

        print(f"_recv_conn: {cls._recv_conn}")
        print(f"_send_conn: {cls._send_conn}")
        print("processor exit")

    @classmethod
    def unreg(cls, stage: Stage):
        cls._send_conn.send(id(stage))

    @classmethod
    def reg(cls, stage: Stage):
        with cls._lock:
            if cls._send_conn is None or cls._recv_conn is None:
                cls._send_conn, cls._recv_conn = Pipe()
            if cls._threading is None:
                cls._threading = threading.Thread(target=cls.processor)
                cls._threading.start()
            cls._tack_dict[id(stage)] = stage

    @classmethod
    def get_tack_dict(cls):
        return cls._tack_dict

    @classmethod
    def is_running(cls):
        return cls._threading.is_alive() if cls._threading else False

    @classmethod
    def has_stage(cls, stage: Stage):
        return id(stage) in cls._tack_dict

    @classmethod
    def reset(cls):
        cls._tack_dict = {}
        if cls._threading:
            cls._threading = None
        if cls._send_conn:
            cls._send_conn = None
        if cls._recv_conn:
            cls._recv_conn = None
