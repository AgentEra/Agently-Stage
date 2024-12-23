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
    """
    Agently Stage Hybrid Generator can be called by `for` and `async for` both.
    
    You can also use `.get()` to get a list result of all items yielded from the generator.

    The execution timing inside the generator task depends on the setting of parameter `lazy` when Stage Hybrid Generator was created.

    Example:

    ```
    from agently-stage import Stage
    async def run_gen(n):
        for i in range(n):
            yield f"Count: { i }"
    
    with Stage() as stage:
        gen = stage.go(run_gen, n)
        for item in gen:
            print(item)
        results = gen.get()
        print(results)
    ```
    """
    def __init__(self, stage, task, on_success=None, on_error=None, lazy=None, async_gen_interval=0.1):
        self._stage = stage
        self._stage._responses.add(self)
        self._loop = stage._loop
        self._on_success = on_success
        self._on_error = on_error
        self._task = task
        self._result = []
        self._error = None
        self._result_queue = queue.Queue()
        self._result_ready = threading.Event()
        self._completed = False
        self._iter_consumed = False
        self._final_result = None
        self._is_lazy = lazy
        self._async_gen_interval = async_gen_interval
        self._lock = threading.RLock()
        if not self._is_lazy:
            self._run_consume_async_gen(self._task)
    
    def _run_consume_async_gen(self, task):
        consume_result = asyncio.run_coroutine_threadsafe(self._consume_async_gen(task), self._loop)
        consume_result.add_done_callback(self._on_consume_async_gen_done)
    
    def _on_consume_async_gen_done(self, future):
        future.result()
        if self._error is not None:
            def raise_error():
                raise self._error
            self._loop.call_soon_threadsafe(raise_error)
        if self._on_success:
            self._final_result = self._on_success(self._result)
        self._result_ready.set()
        #self._stage._responses.discard(self)
    
    async def _consume_async_gen(self, task):
        try:
            async for item in task:
                self._result_queue.put(item)
                self._result.append(item)
            self._completed = True
        except Exception as e:
            if self._on_error:
                handled_result = self._on_error(e)
                self._result_queue.put(handled_result)
                self._result.append(handled_result)
            else:
                self._result_queue.put(e)
                self._result.append(e)
                self._error = e
        finally:
            self._result_queue.put(StopIteration)
    
    async def __aiter__(self):
        with self._lock:
            if self._iter_consumed:
                self._result_ready.wait()
                for item in self._result:
                    yield item
            else:
                if self._is_lazy:
                    self._run_consume_async_gen(self._task)
                while True:
                    try:
                        item = self._result_queue.get_nowait()
                        if item is StopIteration:
                            break
                        yield item
                    except queue.Empty:
                        await asyncio.sleep(self._async_gen_interval)
                self._iter_consumed = True

    def __iter__(self):
        with self._lock:
            if self._iter_consumed:
                self._result_ready.wait()
                for item in self._result:
                    yield item
            else:
                if self._is_lazy:
                    self._run_consume_async_gen(self._task)
                while True:
                    item = self._result_queue.get()
                    if item is StopIteration:
                        break
                    yield item
                self._iter_consumed = True
    
    def get(self):
        """
        Get a list result of all items yielded from the generator.

        Return:
        - [<yielded item 1>, <yielded item 2>, ...]
        """
        with self._lock:
            if self._iter_consumed:
                self._result_ready.wait()
                return self._result
            else:
                if self._is_lazy:
                    self._run_consume_async_gen(self._task)
                self._result_ready.wait()
                return self._result

    def get_final(self):
        """
        Get result from success callback handler that executed with input of a list result of all items yielded from the generator.
        """
        with self._lock:
            if self._iter_consumed:
                self._result_ready.wait()
                if self._final_result:
                    return self._final_result
                else:
                    return self._result
            else:
                if self._is_lazy:
                    self._run_consume_async_gen(self._task)
                self._result_ready.wait()
                if self._final_result:
                    return self._final_result
                else:
                    return self._result