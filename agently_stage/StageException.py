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

import types
import traceback

class StageException(Exception):
    def __init__(self):
        super().__init__()
        self._raised = False
        self._exceptions = []
    
    def __str__(self):
        if len(self._exceptions) == 0:
            return "[Agently Stage] No exception captured."
        else:
            message = (
                "\n------------------\n[Agently Stage] Captured exceptions:\n\n" +
                f"Exception Count: { len(self._exceptions) }\n\n" +
                "Exception List:\n\n"
            )
            for index, exception in enumerate(self._exceptions):
                message += f"❌ [Exception { index + 1 }]\n\n"
                if isinstance(exception["context"], dict):
                    for key, content in exception["context"].items():
                        message += f"   - { key }: { content }\n"
                else:
                    if isinstance(exception["context"], types.TracebackType):
                        context_message = "\n   ".join(traceback.format_exception(
                            type(exception["exception"]),
                            exception["exception"],
                            exception["context"],
                        ))
                        message += context_message
                    else:
                        message += f"   { exception['context'] }\n"
                message += "\n"                
            message += "------------------\nUse <StageException>.get_exceptions() to get exception list."
            return message
    
    def add_exception(self, exception, context=None):
        self._exceptions.append({
            "exception_message": str(exception),
            "exception": exception,
            "context": context,
        })
    
    def mark_raised(self):
        self._raised = True
    
    def has_exceptions(self):
        return True if len(self._exceptions) > 0 and not self._raised else False
    
    def get_exceptions(self):
        return self._exceptions