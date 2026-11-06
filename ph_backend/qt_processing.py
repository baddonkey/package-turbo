"""Run isolated filesystem functions without blocking Qt event delivery."""

from functools import wraps

from PySide6.QtCore import QEventLoop, QObject, QThread, Signal

from .processing import TaskCancelled, TaskControl, processing_context


class IOThread(QThread):
    def __init__(self, operation, phase, control, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.phase = phase
        self.control = control
        self.result = None
        self.error = None

    def run(self):
        try:
            with processing_context(self.control):
                self.control.start(self.phase)
                self.result = self.operation()
                self.control.checkpoint()
        except BaseException as exc:
            self.error = exc


class QtTaskExecutor(QObject):
    progressChanged = Signal(str, "qlonglong", "qlonglong")
    stateChanged = Signal()

    def __init__(self, control, parent=None):
        super().__init__(parent)
        self.control = control
        self.worker = None
        control.progress = self.progressChanged.emit
        control.state_changed = self.stateChanged.emit

    def execute(self, operation, phase):
        if QThread.currentThread() != self.thread():
            raise RuntimeError("Qt filesystem execution must be requested from the owning GUI thread.")
        if self.worker is not None:
            raise RuntimeError("A filesystem task is already running.")
        loop = QEventLoop()
        worker = IOThread(operation, phase, self.control, self)
        self.worker = worker
        worker.finished.connect(loop.quit)
        worker.start()
        try:
            loop.exec()
            if worker.isRunning():
                self.control.cancel()
            worker.wait()
            if worker.error is not None:
                raise worker.error
            self.control.checkpoint()
            return worker.result
        finally:
            worker.wait()
            self.worker = None
            worker.deleteLater()


def io_task(fallback=None):
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            if self._busy or self._io_active:
                return fallback
            control = TaskControl()
            executor = QtTaskExecutor(control, self)
            executor.progressChanged.connect(self._on_io_progress)
            executor.stateChanged.connect(self._on_io_state)
            self._task_control = control
            self._io_active = True
            self._io_completed = self._io_total = 0
            self._set_busy(True)
            self._on_io_state()

            def execute(operation, phase):
                self._io_waiting = True
                try:
                    return executor.execute(operation, phase)
                finally:
                    self._io_waiting = False

            try:
                with processing_context(control, execute):
                    return function(self, *args, **kwargs)
            except TaskCancelled:
                self._set_status("Vorgang abgebrochen")
                return fallback
            finally:
                self._io_waiting = False
                self._io_active = False
                self._task_control = None
                self._set_busy(False)
                self._on_io_state()
                executor.deleteLater()
        return wrapped
    return decorate