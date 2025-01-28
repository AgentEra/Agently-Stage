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

import asyncio
import threading

class StageFunction:
    def __init__(self, stage, func):
        self._stage = stage
        self._func = func
        self._response = None
        self._is_started = threading.Event()
    
    def __call__(self, *args, **kwargs):
        return self.go(*args, **kwargs)
    
    def go(self, *args, **kwargs):
        if self._response:
            return self._response
        self._response = self._stage.go(self._func, *args, **kwargs)
        self._is_started.set()
        return self._response
    
    def get(self, *args, **kwargs):
        return self.go(*args, **kwargs).get()

    def wait(self):
        self._is_started.wait()
        return self._response.get()
    
    def reset(self):
        self._response = None
        return self