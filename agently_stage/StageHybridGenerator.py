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

import asyncio
import queue
import threading
import time


class StageHybridGenerator:
    def __init__(
        self,
        stage,
        task,
        *,
        lazy,
        wait_interval,
        ignore_exception,
        on_success,
        on_error,
        on_finally,
    ):
        self._stage = stage
        self._stage._responses.add(self)
        self._task = task
        self._is_lazy = lazy
        self._wait_interval = wait_interval
        self._ignore_exception = ignore_exception
        self._on_success = on_success
        self._on_error = on_error
        self._on_finally = on_finally
        self._consumer_start = threading.Event()
        self._iterated = False
        self._lock = threading.Lock()
        self.result_ready = threading.Event()
        self._result = {
            "result": [],
            "exceptions": [],
            "queue": queue.Queue(),
        }
        self._is_started = False
        if not self._is_lazy:
            self._start_consume_async_gen()

    def _start_consume_async_gen(self):
        if not self._consumer_start.is_set():
            self._consumer_start.set()
            consume_result = asyncio.run_coroutine_threadsafe(
                self._consume_async_gen(),
                loop=self._stage._dispatch._dispatch_env.loop,
            )
            consume_result.add_done_callback(self._on_consume_async_gen_done)

    async def run_handler(self, handler, *args):
        handler_class = self._stage._classify_task(handler)
        if handler_class == "async_func":
            return await handler(*args)
        elif handler_class == "func":
            return handler(*args)
        else:
            raise TypeError(
                f"[Agently Stage] Wrong type of generator runtime handler, expect function or async function, got: {self._on_success}"
            )

    async def _consume_async_gen(self):
        try:
            async for item in self._task:
                result = item
                if isinstance(result, Exception):
                    raise result
                if self._on_success is not None:
                    result = await self.run_handler(self._on_success, result)
                self._result["queue"].put(result)
                self._result["result"].append(result)
        except Exception as e:
            try:
                result = e
                if self._on_error is not None:
                    result = await self.run_handler(self._on_error, result)
                self._result["queue"].put(result)
                self._result["result"].append(result)
                if isinstance(result, Exception):
                    self._result["exceptions"].append(result)
                    if self._on_error is None and not self._ignore_exception:
                        self._stage._raise_exception(result)
            except Exception as e:
                self._stage._raise_exception(e)
        finally:
            self._result["queue"].put(StopIteration)

    def _on_consume_async_gen_done(self, _):
        if self._on_finally is not None:
            asyncio.run_coroutine_threadsafe(
                self.run_handler(self._on_finally),
                loop=self._stage._dispatch._dispatch_env.loop,
            )
        self.result_ready.set()
        self._stage._responses.discard(self)

    async def __aiter__(self):
        if self._is_lazy:
            self._start_consume_async_gen()
        if self._iterated:
            self.result_ready.wait()
            for item in self._result["result"]:
                yield item
        else:
            self._iterated = True
            while True:
                try:
                    item = self._result["queue"].get_nowait()
                    if item is StopIteration:
                        break
                    yield item
                except queue.Empty:
                    await asyncio.sleep(self._wait_interval)

    def __iter__(self):
        if self._is_lazy:
            self._start_consume_async_gen()
        if self._iterated:
            self.result_ready.wait()
            for item in self._result["result"]:
                yield item
        else:
            self._iterated = True
            while True:
                try:
                    item = self._result["queue"].get_nowait()
                    if item is StopIteration:
                        break
                    yield item
                except queue.Empty:
                    time.sleep(self._wait_interval)

    def is_ready(self):
        return self.result_ready.is_set()

    def get(self):
        if self._is_lazy:
            self._start_consume_async_gen()
        self.result_ready.wait()
        return self._result["result"]

    def __call__(self):
        return self.get()
