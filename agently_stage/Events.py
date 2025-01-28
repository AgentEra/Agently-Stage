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

import threading

class Event(threading.Event):
    def __init__(self, events_data, name):
        super().__init__()
        self._events_data = events_data
        self._name = name
    
    def get_data(self):
        return self._events_data[self._name]
        
    def set_data(self, data):
        self._events_data.update({ self._name: data })
    
    def update_data(self, key, value):
        data = self.get_data()
        if data is None:
            data = {}
        if isinstance(data, dict):
            data.update({ key: value })
            self.set_data(data)
        else:
            raise TypeError(f"[Agently Stage] Event '{ self._name }' can not update data because current data is not a dictionary.")
    
    def handle_data(self, handler):
        data = self.get_data()
        result = handler(data)
        if result:
            self.set_data(result)

    def set(self, data=None):
        if data is not None:
            self._events_data.update({ self._name: data })
        super().set()
    
    def clear(self):
        if self._name in self._events_data:
            del self._events_data[self._name]
        super().clear()
    
    def wait(self):
        super().wait()
        return self._events_data[self._name] if self._name in self._events_data else None

class Events:
    def __init__(self):
        self._events = {}
        self._events_data = {}
    
    def create(self, name):
        if name not in self._events:
            event = Event(self._events_data, name)
            self._events.update({
                name: event
            })
        return self._events[name]
    
    def wait_all(self):
        for event in self._events:
            event.wait()
    
    def get_events(self):
        return self._events