"""Regression tests with real Qt runners and deliberately blocked disk work."""

import importlib
import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pylizlib.core.os.snap import QueryType, SearchTarget
from pylizlib.qt.handler.operation_core import GenericTask

from snappy.model.operation import OperationState


@pytest.fixture
def models(qapp, monkeypatch):
    modules = []
    for name in ("dashboard", "catalogue_searcher", "setting"):
        full_name = f"snappy.model.{name}"
        monkeypatch.delitem(sys.modules, full_name, raising=False)
        modules.append(importlib.import_module(full_name))
    dashboard_module, search_module, setting_module = modules
    monkeypatch.setattr(
        dashboard_module, "TaskGetMonitoredSoftware", lambda: GenericTask("software", lambda: [])
    )
    monkeypatch.setattr(
        dashboard_module,
        "TaskGetSnapshots",
        lambda _catalogue: GenericTask("snapshots", lambda: []),
    )
    dashboard = dashboard_module.DashboardModel()
    dashboard.operation_info.delay_each_task = 0
    search = search_module.CatalogueSearcherModel(dashboard.snap_catalogue, dashboard.operations)
    search.table_model.update_data([SimpleNamespace(id="snapshot", name="Snapshot")])
    settings = setting_module.SettingModel(dashboard)
    yield dashboard, search, settings, search_module
    dashboard.runner.thread_pool.waitForDone(5000)
    search.runner.thread_pool.waitForDone(5000)
    for runner in dashboard._heavy_runners:
        runner.thread_pool.waitForDone(5000)


def test_exclusive_lease_ignores_duplicate_and_stale_releases():
    state = OperationState()
    changes = []
    state.active_changed.connect(changes.append)
    first = state.try_acquire(object())
    assert state.try_acquire(object()) is None
    first.release()
    second = state.try_acquire(object())
    first.release()
    assert state.operation_active
    second.release()
    second.release()
    assert changes == [True, False, True, False]


def test_heavy_work_blocks_all_entry_points_through_follow_up_refresh(
    models, qtbot, monkeypatch, tmp_path
):
    dashboard, search, settings, _ = models
    work_started, work_exit = Event(), Event()
    refresh_started, refresh_exit = Event(), Event()
    transitions, data_received = [], []
    dashboard.operations.active_changed.connect(transitions.append)
    dashboard.signal_on_updated_data_available.connect(
        lambda _data: data_received.append(dashboard.operation_active)
    )

    def work(_task):
        work_started.set()
        assert work_exit.wait(5)

    def refresh():
        refresh_started.set()
        assert refresh_exit.wait(5)
        return []

    dashboard.task_snap.func = refresh
    original_path = dashboard.snap_catalogue.path_catalogue
    try:
        assert dashboard.run_heavy_operation("install", "Installing", work)
        qtbot.waitUntil(work_started.is_set)
        assert dashboard.operation_active
        assert not dashboard.update()
        assert not dashboard.run_heavy_operation("delete", "Deleting", lambda: None)
        assert not search.search("text", QueryType.TEXT, SearchTarget.FILE_NAME, [])
        assert not settings.set_catalogue_path(str(tmp_path / "other-catalogue"))
        assert not settings.set_backup_path(str(tmp_path / "other-backups"))
        assert not settings.clear_backup_directory()
        assert dashboard.snap_catalogue.path_catalogue == original_path
        work_exit.set()
        qtbot.waitUntil(refresh_started.is_set)
        assert transitions == [True]
        assert dashboard.operation_active
        assert not dashboard.update()
        refresh_exit.set()
        qtbot.waitUntil(lambda: not dashboard.operation_active)
        assert transitions == [True, False]
        assert data_received == [True]
    finally:
        work_exit.set()
        refresh_exit.set()


def test_search_stop_holds_global_state_until_worker_exits(models, qtbot, monkeypatch):
    dashboard, search, _, search_module = models
    started, exit_work = Event(), Event()

    def work():
        started.set()
        assert exit_work.wait(5)
        return []

    monkeypatch.setattr(
        search_module, "SnapSearchTask", lambda **_kwargs: GenericTask("search", work)
    )
    try:
        assert search.search("text", QueryType.TEXT, SearchTarget.FILE_NAME, [])
        qtbot.waitUntil(started.is_set)
        search.stop_search()
        assert search.is_search_active
        assert dashboard.operation_active
        assert not dashboard.update()
        assert not search.search("other", QueryType.TEXT, SearchTarget.FILE_NAME, [])
        exit_work.set()
        qtbot.waitUntil(lambda: not dashboard.operation_active)
        assert not search.is_search_active
    finally:
        exit_work.set()


def test_failures_and_launch_errors_release_ownership(models, qtbot, monkeypatch):
    dashboard, search, _, _ = models
    errors = []
    dashboard.signal_on_heavy_operation_error.connect(lambda _title, error: errors.append(error))

    def fail():
        raise OSError("disk unavailable")

    assert dashboard.run_heavy_operation("delete", "Deleting", fail)
    qtbot.waitUntil(lambda: not dashboard.operation_active)
    assert "disk unavailable" in errors[-1]
    assert dashboard.cached_data is None

    monkeypatch.setattr(dashboard.runner, "start", Mock(side_effect=RuntimeError("cannot launch")))
    assert not dashboard.update()
    assert not dashboard.operation_active
    assert "cannot launch" in errors[-1]

    monkeypatch.setattr(search.runner, "start", Mock(side_effect=RuntimeError("cannot search")))
    with pytest.raises(RuntimeError, match="cannot search"):
        search.search("text", QueryType.TEXT, SearchTarget.FILE_NAME, [])
    assert not dashboard.operation_active
    assert not search.is_search_active


def test_empty_search_releases_ownership(models):
    dashboard, search, _, _ = models
    search.table_model.update_data([])
    assert not search.search("text", QueryType.TEXT, SearchTarget.FILE_NAME, [])
    assert not dashboard.operation_active


def test_catalogue_change_is_admitted_before_mutation_and_stays_locked_for_refresh(
    models, qtbot, tmp_path
):
    dashboard, _, settings, _ = models
    observations = []
    settings.catalogue_path_updated.connect(
        lambda path: observations.append((path, dashboard.operation_active))
    )
    destination = tmp_path / "catalogue"
    destination.mkdir()
    assert settings.set_catalogue_path(str(destination))
    assert observations == [(str(destination), True)]
    assert dashboard.operation_active
    qtbot.waitUntil(lambda: not dashboard.operation_active)
    assert dashboard.snap_catalogue.path_catalogue == destination


def test_refresh_stop_waits_for_active_task(models, qtbot):
    dashboard, _, _, _ = models
    started, exit_work = Event(), Event()

    def work():
        started.set()
        assert exit_work.wait(5)
        return []

    dashboard.task_snap.func = work
    try:
        assert dashboard.update()
        qtbot.waitUntil(started.is_set)
        dashboard.runner.stop()
        assert dashboard.operation_active
        assert not dashboard.update()
        exit_work.set()
        qtbot.waitUntil(lambda: not dashboard.operation_active)
        assert dashboard.cached_data is None
    finally:
        exit_work.set()


def test_heavy_launch_error_releases_ownership(models, monkeypatch):
    dashboard, _, _, _ = models
    module = sys.modules[type(dashboard).__module__]
    monkeypatch.setattr(module, "GenericTask", Mock(side_effect=RuntimeError("cannot create task")))
    assert not dashboard.run_heavy_operation("install", "Installing", lambda: None)
    assert not dashboard.operation_active
    assert not dashboard._heavy_runners
