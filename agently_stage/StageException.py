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

import traceback
import types
from typing import TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    from collections.abc import Iterable


class StageExceptionRecord(TypedDict):
    """Structured compatibility record returned by StageException."""

    exception_message: str
    exception: BaseException
    context: object | None


class StageError(Exception):
    """Base class for Stage-owned lifecycle and settlement failures."""


class StageClosedError(StageError):
    """Raised when work is submitted to an already closed Stage scope."""


class StageLifecycleError(StageError):
    """Raised when the private runtime carrier cannot preserve its contract."""


class StageBackpressureError(StageError):
    """Raised when a Stage cannot admit another root within its configured bounds."""


class StageIdleTimeoutError(StageError, TimeoutError):
    """Raised when unresolved Stage-owned work exceeds its idle budget."""

    def __init__(self, *, idle_timeout: float, unresolved_origins: Iterable[str]):
        self.idle_timeout = idle_timeout
        self.unresolved_origins = tuple(unresolved_origins)
        super().__init__(
            f"Stage idle timeout after {idle_timeout:.6g}s; unresolved origins: {list(self.unresolved_origins)}"
        )


class StageSettlementError(StageError):
    """Raised after body completion when retained settlement work failed."""

    def __init__(self, errors: Iterable[BaseException]):
        self.errors: tuple[BaseException, ...] = tuple(errors)
        super().__init__(f"{len(self.errors)} Stage settlement task(s) failed")


class TunnelClosedError(StageError):
    """Raised when a value is written after a Tunnel reaches terminal state."""


class TunnelLagError(StageError):
    """Raised when a bounded Tunnel reader falls behind retained history."""

    def __init__(self, *, expected_sequence: int, available_from: int):
        self.expected_sequence = expected_sequence
        self.available_from = available_from
        self.missed_count = available_from - expected_sequence
        super().__init__(
            "Tunnel reader fell behind retained history: "
            f"missed {self.missed_count} item(s), expected sequence "
            f"{expected_sequence}, earliest available sequence is {available_from}"
        )


class StageException(Exception):
    """Compatibility collector for explicitly captured exception records."""

    def __init__(self) -> None:
        super().__init__()
        self._raised = False
        self._exceptions: list[StageExceptionRecord] = []

    def __str__(self) -> str:
        if not self._exceptions:
            return "[Agently Stage] No exception captured."
        message = (
            "\n------------------\n[Agently Stage] Captured exceptions:\n\n"
            + f"Exception Count: {len(self._exceptions)}\n\n"
            + "Exception List:\n\n"
        )
        for index, exception_record in enumerate(self._exceptions):
            message += f"❌ [Exception {index + 1}]\n\n"
            context = exception_record["context"]
            if isinstance(context, dict):
                for key, content in cast("dict[object, object]", context).items():
                    message += f"   - {key}: {content}\n"
            elif isinstance(context, types.TracebackType):
                error = exception_record["exception"]
                context_message = "\n   ".join(
                    traceback.format_exception(
                        type(error),
                        error,
                        context,
                    )
                )
                message += context_message
            else:
                message += f"   {context}\n"
            message += "\n"
        message += "------------------\nUse <StageException>.get_exceptions() to get exception list."
        return message

    def add_exception(self, exception: BaseException, context: object | None = None) -> None:
        self._exceptions.append(
            StageExceptionRecord(
                exception_message=str(exception),
                exception=exception,
                context=context,
            )
        )

    def mark_raised(self) -> None:
        self._raised = True

    def has_exceptions(self) -> bool:
        return bool(self._exceptions) and not self._raised

    def get_exceptions(self) -> list[StageExceptionRecord]:
        return self._exceptions.copy()
