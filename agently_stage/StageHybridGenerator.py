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

import queue
import asyncio
import threading

class StageHybridGenerator:
    def __init__(self,
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
        self._task = task
        self._is_lazy = lazy
        self._wait_interval = wait_interval
        self._ignore_exception = ignore_exception
        self._on_success = on_success
        self._on_error = on_error
        self._on_finally = on_finally
        self.result_ready = threading.Event()
        self._result = {
            "result": [],
            "exceptions": [],
            "queue": queue.Queue()
        }
        self._is_started = False
        self._iter_lock = threading.RLock()
        if not self._is_lazy:
            self._start_consume_async_gen()
    
    def _start_consume_async_gen(self):
        if not self._is_started:
            self._is_started = True
            consume_result = self._stage._loop_thread.run_coroutine(self._consume_async_gen())
            consume_result.add_done_callback(self._on_consume_async_gen_done)
    
    async def _consume_async_gen(self):
        try:
            async for item in self._task:
                result = (
                    item
                    if self._on_success is None
                    else self._on_success(item)
                )
                if isinstance(result, Exception):
                    raise result
                self._result["queue"].put(result)
                self._result["result"].append(result)
        except Exception as e:
            result = (
                e
                if self._on_error is None
                else self._on_error(e)
            )
            self._result["queue"].put(result)
            self._result["result"].append(result)
            if isinstance(result, Exception):
                self._result["exceptions"].append(result)
                if self._on_error is None and not self._ignore_exception:
                    self._stage._raise_exception(result)
        finally:
            self._result["queue"].put(StopIteration)
    
    def _on_consume_async_gen_done(self, future):
        future.done()
        if self._on_finally is not None:
            self._on_finally(self._result["result"])
        self.result_ready.set()
        
    async def __aiter__(self):
        with self._iter_lock:
            if self.result_ready.is_set():
                for item in self._result["result"]:
                    yield item
            else:
                if self._is_lazy:
                    self._start_consume_async_gen()
                while True:
                    try:
                        item = self._result["queue"].get_nowait()
                        if item is StopIteration:
                            break
                        yield item
                    except queue.Empty:
                        await asyncio.sleep(self._wait_interval)

    def __iter__(self):
        with self._iter_lock:
            if self.result_ready.is_set():
                for item in self._result["result"]:
                    yield item
            else:
                if self._is_lazy:
                    self._start_consume_async_gen()
                while True:
                    item = self._result["queue"].get()
                    if item is StopIteration:
                        break
                    yield item

    def is_ready(self):
        return self.result_ready.is_set()

    def get(self):
        if self._is_lazy:
            self._start_consume_async_gen()
        self.result_ready.wait()
        return self._result["result"]
    
    def __call__(self):
        return self.get()