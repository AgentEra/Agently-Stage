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

from __future__ import annotations

import asyncio
from threading import Thread
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .Stage import Stage


class Task:
    def __init__(self, func: Callable, stage: Stage | None = None, use_async: bool = False):
        from .Stage import Stage

        assert stage is None or isinstance(stage, Stage), "stage must be None or Stage"
        self._func = func
        self._stage = stage
        self._use_async = use_async

    def async_run(self, *args: tuple[Any], **kwargs: dict[str, Any]):
        assert self._func, "Function is None"
        asyncio.create_task(self._func(*args, **kwargs))

    def sync_run(self, *args: tuple[Any], **kwargs: dict[str, Any]):
        assert self._func, "Function is None"
        th = Thread(target=self._func, args=args, kwargs=kwargs)
        th.start()

    def __call__(self, *args: tuple[Any], **kwargs: dict[str, Any]):
        if self._stage and self._stage.is_available:
            return self._stage.go(self._func, *args, **kwargs)
        if self._use_async:
            return self.async_run(*args, **kwargs)
        return self.sync_run(*args, **kwargs)


class StageTaskProxy:
    def __init__(
        self,
        func: Callable,
        stage: Stage | None = None,
        on_success: Callable | None = None,
        on_error: Callable | None = None,
        on_finally: Callable | None = None,
        ignore_exception: bool = False,
        use_async: bool = False,
    ):
        self._func = func
        self._on_success = Task(on_success, stage, use_async) if on_success else None
        self._on_error = Task(on_error, stage, use_async) if on_error else None
        self._on_finally = Task(on_finally, stage, use_async) if on_finally else None
        self._ignore_exception = ignore_exception
        self._use_async = use_async

    def add_on_success(self, on_success: Task[Callable]):
        self._on_success = on_success
        return self

    def add_on_error(self, on_error: Task[Callable]):
        self._on_error = on_error
        return self

    def add_on_finally(self, on_finally: Task[Callable]):
        self._on_finally = on_finally
        return self

    async def async_run(self, *args: tuple[Any], **kwargs: dict[str, Any]):
        assert self._func, "Function is None"

        try:
            result = await self._func(*args, **kwargs)
            if self._on_success:
                self._on_success(result)
            return result
        except Exception as e:
            if self._on_error:
                self._on_error(e)
            if self._ignore_exception:
                return
            raise e
        finally:
            if self._on_finally:
                self._on_finally()

    def sync_run(self, *args: tuple[Any], **kwargs: dict[str, Any]):
        assert self._func, "Function is None"

        try:
            result = self._func(*args, **kwargs)
            if self._on_success:
                self._on_success(result)
            return result
        except Exception as e:
            if self._on_error:
                self._on_error(e)
            if self._ignore_exception:
                return
            raise e
        finally:
            if self._on_finally:
                self._on_finally()

    def __call__(self, *args: tuple[Any], **kwargs: dict[str, Any]):
        if self._use_async:
            return self.async_run(*args, **kwargs)
        return self.sync_run(*args, **kwargs)
