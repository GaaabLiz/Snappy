"""Exercise the shared operation gate through the actual dashboard UI wiring."""

from threading import Event
from types import SimpleNamespace

from pylizlib.qt.handler.operation_core import GenericTask


def test_dashboard_locks_other_pages_until_search_has_really_stopped(qtbot, monkeypatch, tmp_path):
    from snappy.controller.dashboard import DashboardController
    from snappy.model import catalogue_searcher

    dashboard = DashboardController()
    qtbot.addWidget(dashboard.view)
    # Use predictable initial data, without scanning the host's applications.
    monkeypatch.setattr(dashboard.model.task_monitored_soft, "execute", lambda: [])
    monkeypatch.setattr(dashboard.model.task_snap, "execute", lambda: [])
    dashboard.start()
    assert dashboard.operation_active
    assert not dashboard.settings.view.isEnabled()
    qtbot.waitUntil(lambda: not dashboard.operation_active)
    assert dashboard.settings.view.isEnabled()

    started, exit_work = Event(), Event()

    def work():
        started.set()
        assert exit_work.wait(5)
        return []

    monkeypatch.setattr(
        catalogue_searcher, "SnapSearchTask", lambda **_kwargs: GenericTask("search", work)
    )
    searcher = dashboard.searcher
    searcher.model.table_model.update_data([SimpleNamespace(id="snap", name="Snapshot")])
    searcher.view.search_bar.setText("query")
    original_path = dashboard.model.snap_catalogue.path_catalogue
    try:
        searcher.view.action_start.trigger()
        qtbot.waitUntil(started.is_set)
        assert dashboard.operation_active
        assert searcher.view.isEnabled()
        assert searcher.view.action_stop.isEnabled()
        for page in (dashboard.settings, dashboard.backup, dashboard.catalogue):
            assert not page.view.isEnabled()
        dashboard.view.f5_pressed.emit()
        assert not dashboard.settings.model.set_catalogue_path(str(tmp_path / "other"))
        assert dashboard.model.snap_catalogue.path_catalogue == original_path
        searcher.view.action_stop.trigger()
        assert dashboard.operation_active
        assert not searcher.view.action_start.isEnabled()
        assert not dashboard.settings.view.isEnabled()
        exit_work.set()
        qtbot.waitUntil(lambda: not dashboard.operation_active)
        assert searcher.view.action_start.isEnabled()
        assert dashboard.settings.view.isEnabled()
    finally:
        exit_work.set()
        searcher.model.runner.thread_pool.waitForDone(5000)
        dashboard.model.runner.thread_pool.waitForDone(5000)
