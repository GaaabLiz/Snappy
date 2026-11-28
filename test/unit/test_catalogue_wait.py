"""Verify queued operation feedback and waiting cancellation with actual Qt workers."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from PySide6.QtCore import QThread
from pylizlib.core.os.snap import SnapshotOperationPhase
from pylizlib.core.os.snap.storage.coordination import catalogue_access

from snappy.application.app import AppSettings, app_settings
from snappy.model.dashboard import DashboardModel


def test_dashboard_receives_wait_feedback_on_gui_thread(qtbot, monkeypatch, tmp_path):
    original_get = app_settings.get

    def get_setting(key):
        if key is AppSettings.catalogue_path:
            return str(tmp_path / "catalogue")
        return original_get(key)

    monkeypatch.setattr(app_settings, "get", get_setting)
    model = DashboardModel()
    entered, release = Event(), Event()
    events = []
    errors = []

    def hold_catalogue():
        with catalogue_access(model.snap_catalogue.path_catalogue):
            entered.set()
            assert release.wait(10)

    def observe(update):
        events.append((update.phase, QThread.currentThread()))

    model.signal_on_operation_update.connect(observe)
    model.signal_on_heavy_operation_error.connect(lambda *args: errors.append(args))
    with ThreadPoolExecutor(max_workers=1) as worker:
        holder = worker.submit(hold_catalogue)
        try:
            assert entered.wait(5)
            assert model.update()
            qtbot.waitUntil(lambda: any(phase == SnapshotOperationPhase.WAITING_FOR_CATALOGUE for phase, _ in events))
            assert model.operation_active
            assert model.cached_data is None

            with qtbot.waitSignal(model.signal_on_update_complete):
                model.cancel_catalogue_wait()
            assert not holder.done()
            assert not model.operation_active
        finally:
            release.set()
            model.runner.thread_pool.waitForDone(5000)
        holder.result(timeout=5)

    assert events[-1][0] == SnapshotOperationPhase.CANCELLED
    assert all(thread == model.thread() for _, thread in events)
    assert errors == []

    with qtbot.waitSignal(model.signal_on_update_complete):
        assert model.update()
    assert model.cached_data is not None
    assert model.cached_data.snapshots == []
    assert events[-1][0] == SnapshotOperationPhase.COMPLETED
