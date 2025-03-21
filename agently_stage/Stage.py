# Copyright 2024-2025 Maplemx(Mo Xin), AgentEra Ltd. Agently Team(https://Agently.tech)
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

import asyncio
import functools
import inspect
import types
from concurrent.futures import Future
from typing import Any, Callable

from .StageDispatch import StageDispatch
from .StageFunction import StageFunction
from .StageHybridGenerator import StageHybridGenerator
from .StageResponse import StageResponse


class Stage:
    _atexit_registered = False

    def __init__(
        self,
        reuse_env: bool = False,
        exception_handler: Callable[[Exception], Any] = None,
        max_workers: int = None,
        auto_close: bool = False,
    ):
        """
        Agently Stage create an stage instance to help you execute sync and async tasks in its dispatch environment outside the main thread.

        Agently Stage dispatch environment will execute tasks in an independent thread with an independent async event loop. Sync task will be transformed into async task by thread pool executor and put into this independent event loop to dispatch too.

        Args:

        - `exception_handler`: [Optional] Customize exception handler to handle runtime exception.
        - `is_daemon`: [Default: False] When an stage instance is set as daemon, it will try to ensure all executed tasks then close its dispatch environment with the main thread. If you come across unexpect task closing, try set `is_daemon` to `False` and close stage instance with `stage.close()` manually.
        """
        self._dispatch = StageDispatch(
            reuse_env=reuse_env,
            exception_handler=exception_handler,
            max_workers=max_workers,
            auto_close=auto_close,
        )
        self._responses = set()
        self._raise_exception = self._dispatch.raise_exception
        self._is_closing = False

    # Basic
    def _classify_task(self, task):
        if isinstance(task, StageFunction):
            return "stage_func"
        if isinstance(task, functools.partial):
            return self._classify_task(task.func)
        if isinstance(task, (classmethod, staticmethod, types.MethodType)):
            return self._classify_task(task.__func__)
        if inspect.isasyncgenfunction(task):
            return "async_gen_func"
        if inspect.isasyncgen(task):
            return "async_gen"
        if inspect.isgeneratorfunction(task):
            return "gen_func"
        if inspect.isgenerator(task):
            return "gen"
        if inspect.iscoroutinefunction(task):
            return "async_func"
        if inspect.iscoroutine(task):
            return "async_coro"
        if isinstance(task, Future):
            return "future"
        if inspect.isfunction(task) or inspect.isbuiltin(task):
            return "func"
        if callable(task):
            return self._classify_task(task.__call__)
        return None

    def go(
        self,
        task: Callable[[tuple[Any, ...], dict[str, Any]], Any],
        *args,
        lazy: bool = False,
        on_success: Callable[[Any], Any] = None,
        on_error: Callable[[Exception], Any] = None,
        on_finally: Callable[[None], None] = None,
        ignore_exception: bool = False,
        wait_interval: float = 0.1,
        **kwargs,
    ) -> StageResponse | StageHybridGenerator:
        """
        Start task in stage instance's dispatch environment.

        Usage:

        ```
        def task(sentence, options:dict):
            print(sentence)
            for key, value in options.items():
                print(key, value)
            raise Exception("Some Error")

        stage.go(
            task,
            "hello world",
            options={"AgentlyStage": "is very cool!"},
            on_error=lambda e: print("Something Wrong:", e),
        )
        ```
        """
        if not self.is_available:
            raise RuntimeError("[Agently Stage] Can not attempt threading operation on unavailable stage.")
        task_class = self._classify_task(task)

        # Stage Function
        if task_class == "stage_func":
            return task(*args, **kwargs)

        # Async Gen
        if task_class == "async_gen_func":
            go_task = task(*args, **kwargs)
            return StageHybridGenerator(
                self,
                go_task,
                lazy=lazy,
                on_success=on_success,
                on_error=on_error,
                on_finally=on_finally,
                ignore_exception=ignore_exception,
                wait_interval=wait_interval,
            )
        if task_class == "async_gen":
            return StageHybridGenerator(
                self,
                task,
                lazy=lazy,
                on_success=on_success,
                on_error=on_error,
                on_finally=on_finally,
                ignore_exception=ignore_exception,
                wait_interval=wait_interval,
            )
        # Sync Gen
        if task_class == "gen_func":

            async def async_gen():
                for item in task(*args, **kwargs):
                    try:
                        await asyncio.sleep(0)
                        yield item
                    except Exception as e:
                        yield e

            return StageHybridGenerator(
                self,
                async_gen(),
                lazy=lazy,
                on_success=on_success,
                on_error=on_error,
                on_finally=on_finally,
                ignore_exception=ignore_exception,
                wait_interval=wait_interval,
            )
        if task_class == "gen":

            async def async_gen():
                for item in task:
                    try:
                        await asyncio.sleep(0)
                        yield item
                    except Exception as e:
                        yield e

            return StageHybridGenerator(
                self,
                async_gen(),
                lazy=lazy,
                on_success=on_success,
                on_error=on_error,
                on_finally=on_finally,
                ignore_exception=ignore_exception,
                wait_interval=wait_interval,
            )

        # Async Func
        if task_class == "async_func" or task_class == "async_coro":
            go_task = self._dispatch.run_async_function(task, *args, **kwargs)
            return StageResponse(
                self,
                go_task,
                on_success=on_success,
                on_error=on_error,
                on_finally=on_finally,
                ignore_exception=ignore_exception,
            )
        if task_class == "future":
            return StageResponse(
                self,
                task,
                on_success=on_success,
                on_error=on_error,
                on_finally=on_finally,
                ignore_exception=ignore_exception,
            )
        # Sync Func
        if task_class == "func":
            go_task = self._dispatch.run_sync_function(task, *args, **kwargs)
            return StageResponse(
                self,
                go_task,
                on_success=on_success,
                on_error=on_error,
                on_finally=on_finally,
                ignore_exception=ignore_exception,
            )

        # Other
        raise Exception(f"[Agently Stage] Not a supported task type: {task}")

    def get(
        self,
        task: Callable[[tuple[Any, ...], dict[str, Any]], Any],
        *args,
        lazy: bool = False,
        on_success: Callable[[Any], Any] = None,
        on_error: Callable[[Exception], Any] = None,
        on_finally: Callable[[None], None] = None,
        ignore_exception: bool = False,
        wait_interval: float = 0.1,
        **kwargs,
    ):
        return self.go(
            task,
            *args,
            lazy=lazy,
            on_success=on_success,
            on_error=on_error,
            on_finally=on_finally,
            ignore_exception=ignore_exception,
            wait_interval=wait_interval,
            **kwargs,
        ).get()

    def close(self):
        self._is_closing = True
        self._dispatch.close()

    @property
    def is_closing(self):
        """
        is_closing: bool.  True if stage instance is trying to close and can not accept new task.
        """
        return self._is_closing

    @property
    def is_available(self):
        """
        is_available: bool.  True if stage environment is ready and can accept new task.
        """
        return not self._dispatch._dispatch_env.closing and not self._is_closing

    # With
    def __enter__(self):
        if self.is_available:
            return self
        raise RuntimeError(f"[Agently Stage] Can not start stage {self} because it is not available.")

    def __exit__(self, type, value, traceback):
        self.close()

    # Func
    def func(self, task) -> StageFunction:
        return StageFunction(self, task)
