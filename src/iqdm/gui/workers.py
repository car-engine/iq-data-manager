"""Run slow work off the Qt main thread: scans, database reads and writes.

CLAUDE.md requires a worker thread for anything that can take more than about
100 ms. A database on the NAS can take that long for one query, and a write can wait
up to about 18 s for a lock (DECISIONS.md D7).

TaskRunner.start(fn) runs fn(task) on a QThreadPool thread. fn may call
task.report(n) and task.is_cancelled(). The callbacks given to start() run on the
main thread, because TaskRunner lives there and receives the task's signals in its
own slots.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot


class _TaskSignals(QObject):
    progress = Signal(object, object)  # task, a count or a progress object
    succeeded = Signal(object, object)  # task, result
    failed = Signal(object, object)  # task, exception


class Task(QRunnable):
    """One function call on a pool thread. Create it through TaskRunner.start()."""

    def __init__(self, fn: Callable[["Task"], object]) -> None:
        super().__init__()
        self.setAutoDelete(False)  # TaskRunner holds the reference until the task ends
        self.signals = _TaskSignals()
        self._fn = fn
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def report(self, value: object) -> None:
        """Send progress to the main thread. Safe to call from any thread."""
        self.signals.progress.emit(self, value)

    def run(self) -> None:
        try:
            result = self._fn(self)
        except Exception as exc:  # every error goes back to the GUI
            self.signals.failed.emit(self, exc)
        else:
            self.signals.succeeded.emit(self, result)


@dataclass
class _Callbacks:
    on_success: Callable[[object], None] | None
    on_failure: Callable[[Exception], None] | None
    on_progress: Callable[[Any], None] | None


class TaskRunner(QObject):
    """Starts tasks on a thread pool and calls their callbacks on the main thread."""

    def __init__(self, parent: QObject | None = None, pool: QThreadPool | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool.globalInstance() if pool is None else pool
        self._running: dict[Task, _Callbacks] = {}

    def start(
        self,
        fn: Callable[[Task], object],
        *,
        on_success: Callable[[object], None] | None = None,
        on_failure: Callable[[Exception], None] | None = None,
        on_progress: Callable[[Any], None] | None = None,
    ) -> Task:
        task = Task(fn)
        self._running[task] = _Callbacks(on_success, on_failure, on_progress)
        task.signals.progress.connect(self._progress)
        task.signals.succeeded.connect(self._succeeded)
        task.signals.failed.connect(self._failed)
        self._pool.start(task)
        return task

    @property
    def busy(self) -> bool:
        """True while any task started here has not delivered its result."""
        return bool(self._running)

    def wait(self, msecs: int = -1) -> bool:
        """Block until the pool is idle. For tests and shutdown."""
        return self._pool.waitForDone(msecs)

    @Slot(object, object)
    def _progress(self, task: Task, value: object) -> None:
        callbacks = self._running.get(task)
        if callbacks is not None and callbacks.on_progress is not None:
            callbacks.on_progress(value)

    @Slot(object, object)
    def _succeeded(self, task: Task, result: object) -> None:
        callbacks = self._running.pop(task, None)
        if callbacks is not None and callbacks.on_success is not None:
            callbacks.on_success(result)

    @Slot(object, object)
    def _failed(self, task: Task, exc: Exception) -> None:
        callbacks = self._running.pop(task, None)
        if callbacks is not None and callbacks.on_failure is not None:
            callbacks.on_failure(exc)
