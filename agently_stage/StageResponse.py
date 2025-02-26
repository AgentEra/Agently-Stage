# Copyright 2024 Maplemx(Mo Xin), AgentEra Ltd. Agently Team(https://Agently.tech)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Contact us: Developer@Agently.tech
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from concurrent.futures import Future

    from agently_stage import Stage


@dataclass
class CallbackFunctionData:
    func: Callable = field(default_factory=lambda: lambda: None)
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    event: threading.Event = field(default_factory=threading.Event)
    # 需不需要运行
    run: bool = field(default=True)


@dataclass
class TaskResult:
    result: any | None = field(default=None)
    status: bool | None = field(default=None)


class StageResponse:
    def __init__(
        self,
        stage: Stage,
        task: Future,
        *,
        ignore_exception: bool = False,
        on_success: Callable = None,
        on_error: Callable = None,
        on_finally: Callable = None,
    ):
        self._stage = stage

        # 默认值 copy 自 ThreadPoolExecutor.__init__, TODO: 在 3.13 版本中应该使用 process_cpu_count()
        max_workers = self._stage.max_workers if self._stage.max_workers else min(32, (os.cpu_count() or 1) + 4)
        # 计算非空回调函数的数量
        callback_count = sum(1 for cb in [on_success, on_error, on_finally] if cb is not None)
        # 确保回调函数数量不超过最大工作线程数
        assert max_workers >= callback_count + 1, (
            f"Callback function count: {callback_count}, exceeds maximum worker threads: {max_workers}"
        )

        self._stage._responses.add(self)
        self._task = task
        self._ignore_exception = ignore_exception
        # 目前只保证有跑, 不保证马上跑, 并且会完整的占用掉一个线程
        if on_success is not None:
            self._success_func_data = CallbackFunctionData(func=on_success, event=threading.Event())
            self._stage.go(self._go_callback_function, self._success_func_data)
        if on_error is not None:
            self._error_func_data = CallbackFunctionData(func=on_error, event=threading.Event())
            self._stage.go(self._go_callback_function, self._error_func_data)
        if on_finally is not None:
            self._finally_func_data = CallbackFunctionData(func=on_finally, event=threading.Event())
            self._stage.go(self._go_callback_function, self._finally_func_data)

        self.result_ready = threading.Event()
        self._result = TaskResult()
        self._task.add_done_callback(self._on_task_done)

    def _go_callback_function(self, callbackfunctionData: CallbackFunctionData):
        callbackfunctionData.event.wait()
        if callbackfunctionData.run:
            callbackfunctionData.func(*callbackfunctionData.args, **callbackfunctionData.kwargs)

    def _on_task_done(self, future):
        try:
            result = future.result()
            if isinstance(result, Exception):
                raise result
            self._result = TaskResult(status=True, result=result)

            if getattr(self, "_success_func_data", None):
                # 始终设置参数，如果result为None则使用空元组
                self._success_func_data.args = (result,) if result is not None else ()
                self._success_func_data.event.set()
            if getattr(self, "_error_func_data", None):
                self._error_func_data.run = False
                self._error_func_data.event.set()
        except Exception as e:
            self._result = TaskResult(status=False, result=e)

            # 取消运行 success
            if getattr(self, "_success_func_data", None):
                self._success_func_data.run = False
                self._success_func_data.event.set()

            if getattr(self, "_error_func_data", None):
                self._error_func_data.args = (e,)
                self._error_func_data.event.set()
            elif not self._ignore_exception:
                self._stage._raise_exception(e)
        finally:
            if getattr(self, "_finally_func_data", None):
                self._finally_func_data.event.set()
            self.result_ready.set()
            self._stage._responses.discard(self)

    def is_ready(self):
        return self.result_ready.is_set()

    def get(self):
        self.result_ready.wait()
        return self._result.result
