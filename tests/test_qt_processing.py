import threading

import pytest
from PySide6.QtCore import QThread
from PySide6.QtGui import QGuiApplication

from ph_backend.processing import TaskCancelled, TaskControl
from ph_backend.qt_processing import QtTaskExecutor


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication(["processing-test", "-platform", "offscreen"])


def test_gui_callbacks_run_while_worker_is_waiting(app):
    control = TaskControl()
    executor = QtTaskExecutor(control)
    released = threading.Event()
    callbacks = []

    def callback(phase, completed, total):
        callbacks.append(QThread.currentThread() == app.thread())
        released.set()

    def operation():
        assert QThread.currentThread() != app.thread()
        assert released.wait(2)
        return "finished"

    executor.progressChanged.connect(callback)
    assert executor.execute(operation, "Waiting worker") == "finished"
    assert callbacks and all(callbacks)
    assert executor.worker is None


def test_gui_can_cancel_worker_without_waiting_in_cancel(app):
    control = TaskControl()
    executor = QtTaskExecutor(control)
    executor.progressChanged.connect(lambda phase, completed, total: control.cancel())
    with pytest.raises(TaskCancelled):
        executor.execute(lambda: "not accepted", "Cancelable task")
    assert executor.worker is None


def test_progress_accepts_values_above_two_gib(app):
    control = TaskControl()
    executor = QtTaskExecutor(control)
    reports = []
    executor.progressChanged.connect(lambda phase, completed, total: reports.append((completed, total)))

    def operation():
        control.start("Large progress", 5 * 1024 ** 3)
        control.advance(4 * 1024 ** 3)

    executor.execute(operation, "Progress")
    assert (4 * 1024 ** 3, 5 * 1024 ** 3) in reports