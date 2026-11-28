import sys
import types
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock

from pylizlib.core.os.snap import SnapDirAssociation, Snapshot, SnapshotOperationResult

def test_catalogue_controller(monkeypatch, tmp_path):
    # Mock i18n
    import snappy.application.i18n
    monkeypatch.setattr(snappy.application.i18n, "tr", lambda x, **kw: x.format(**kw) if kw else x)
    
    # Mock MessageBox
    import qfluentwidgets
    confirmations = []
    class FakeMessageBox:
        res = True
        def __init__(self, t, d, parent=None): confirmations.append(d)
        def exec_(self): return self.res
    monkeypatch.setattr(qfluentwidgets, "MessageBox", FakeMessageBox)
    
    # Mock QFileDialog
    class FakeQFileDialog:
        ret = "/some/dir"
        zip_file = "/some/example.zip"
        @classmethod
        def getExistingDirectory(cls, *args): return cls.ret
        @classmethod
        def getOpenFileName(cls, *args): return cls.zip_file, ""
    monkeypatch.setattr("PySide6.QtWidgets.QFileDialog", FakeQFileDialog)

    class FakeQInputDialog:
        source_index = 0
        accepted = True

        @classmethod
        def getItem(cls, parent, title, text, labels, current, editable):
            return labels[cls.source_index], cls.accepted

    monkeypatch.setattr("PySide6.QtWidgets.QInputDialog", FakeQInputDialog)
    
    # Mock UiUtils
    import pylizlib.qtfw.util.ui
    msgs = []
    class FakeUiUtils:
        @classmethod
        def show_message(cls, t, text, parent=None): msgs.append(text)
    monkeypatch.setattr(pylizlib.qtfw.util.ui, "UiUtils", FakeUiUtils)
    
    # Mock DialogConfig
    dl_mod = types.ModuleType("snappy.view.catalogue_imp_dialog")
    class FakeSnapshot:
        def __init__(self, id, name): self.id = id; self.name = name
    form_data = {
        "id": "d1",
        "name": "D1",
        "desc": "Description",
        "tags": ["test"],
        "custom_data": {"visible": "value"},
        "directories": ["/source/one"],
        "directories_changed": False,
    }
    class FakeDialogConfig:
        res = True
        def __init__(self, d, e, s, *, catalogue_path): self.output_data = form_data
        def exec(self): return self.res
    dl_mod.DialogConfig = FakeDialogConfig
    monkeypatch.setitem(sys.modules, "snappy.view.catalogue_imp_dialog", dl_mod)
    
    # Mock log_action
    import snappy.model.history as hist_mod
    actions = []
    def fake_log(c, t, n): actions.append((c,t,n))
    monkeypatch.setattr(hist_mod, "log_action", fake_log)
    
    # App Settings mock
    import snappy.application.app
    class AS:
        def get(self, k): return True
    monkeypatch.setattr(snappy.application.app, "app_settings", AS())
    class FakeApp: path = Path("/app")
    monkeypatch.setattr(snappy.application.app, "app", FakeApp())
    
    opened = []

    import PySide6.QtGui
    class FakeQDS:
        @classmethod
        def openUrl(cls, u): opened.append(str(u))
    monkeypatch.setattr(PySide6.QtGui, "QDesktopServices", FakeQDS)
    
    # Mock View & Model
    view_mod = types.ModuleType("snappy.view.catalogue")
    class FakeSignal:
        def __init__(self): self.c = None
        def connect(self, f): self.c = f
        def emit(self, *args): self.c(*args) if self.c else None
    class FakeView:
        def __init__(self, m):
            self.m = m
            self.signal_create_requested = FakeSignal()
            self.signal_import_requested = FakeSignal()
            self.signal_open_catalogue_folder_requested = FakeSignal()
            self.signal_install_requested = FakeSignal()
            self.signal_edit_requested = FakeSignal()
            self.signal_delete_requested = FakeSignal()
            self.signal_open_folder_requested = FakeSignal()
            self.signal_duplicate_requested = FakeSignal()
            self.signal_sort_requested = FakeSignal()
            self.signal_search_internal_content_all = FakeSignal()
            self.signal_search_internal_content_single = FakeSignal()
            self.signal_export_request_snapshot = FakeSignal()
            self.signal_export_request_assoc_folders = FakeSignal()
            self.signal_delete_installed_folders_requested = FakeSignal()
            self.signal_update_with_local_dirs_requested = FakeSignal()
            self.signal_open_assoc_folder_requested = FakeSignal()
            self.sort_calls = 0
        def sort(self): self.sort_calls += 1
        def reload_data(self): pass
    delete_confirmations = []
    class FakeDeleteAssociatedFoldersDialog:
        def __init__(self, paths, parent=None):
            delete_confirmations.append(paths)
        def exec(self):
            return FakeMessageBox.res
    install_confirmations = []

    class FakeInstallSnapshotDialog:
        def __init__(self, paths, clear_destination, parent=None):
            install_confirmations.append((paths, clear_destination))

        def exec(self):
            return FakeMessageBox.res

    update_confirmations = []

    class FakeUpdateSnapshotDialog:
        def __init__(self, paths, emptying_paths, parent=None):
            update_confirmations.append((paths, emptying_paths))

        def exec(self):
            return FakeMessageBox.res

    view_mod.UpdateSnapshotDialog = FakeUpdateSnapshotDialog
    view_mod.InstallSnapshotDialog = FakeInstallSnapshotDialog
    view_mod.SnapshotCatalogueWidget = FakeView
    view_mod.DeleteAssociatedFoldersDialog = FakeDeleteAssociatedFoldersDialog
    monkeypatch.setitem(sys.modules, "snappy.view.catalogue", view_mod)
    
    model_mod = types.ModuleType("snappy.model.catalogue")
    class FakeTM:
        def update_headers(self): pass
    class FakeModel:
        def __init__(self): self.table_model = FakeTM()
        def set_snapshots(self, snapshots, statistics): pass
    model_mod.CatalogueModel = FakeModel
    monkeypatch.setitem(sys.modules, "snappy.model.catalogue", model_mod)
    
    # Mock DashboardModel
    dash_mod = types.ModuleType("snappy.model.dashboard")
    class FakeTask:
        def update_task_progress(self, p): pass
        def update_task_message(self, m): pass
    task = FakeTask()

    class FakeCat:
        def __init__(self):
            self.path_catalogue = tmp_path / "catalogue"
            self.get_all = Mock()
            self.get_by_id = Mock()
            self.create_snapshot = Mock(return_value=FakeSnapshot("d1", "D1"))
            self.import_snapshot = Mock()
            self.import_catalogue = Mock()
            self.update_snapshot_with_result = Mock(return_value=types.SimpleNamespace(
                snapshot=FakeSnapshot("s1", "Edited"), backup_path=Path("/backups/edit.zip"),
            ))
            self.install_with_result = Mock(return_value=SnapshotOperationResult(None))
            self.delete_with_result = Mock(return_value=SnapshotOperationResult(Path("/backups/delete.zip")))
            self.export_assoc_dirs = Mock()
            self.export_captured_assoc_dirs = Mock()
            self.get_sync_plan = Mock()
            self.sync_with_result = Mock(return_value=SnapshotOperationResult(Path("/backups/sync.zip")))
        def get_snap_directory_path(self, s): return Path("/snap/dir")
        def duplicate_by_id(self, id, progress_callback=None, message_callback=None): pass
        def export_snapshot(self, id, d, progress_callback=None, message_callback=None): pass
    class FakeDash:
        def __init__(self):
            self.cached_data = None
            self.snap_catalogue = FakeCat()
            self.result_messages = []
        def run_heavy_operation(self, n, d, func, success_msg_title="", success_msg="", update_dashboard=True, *, show_result_message=False):
            result = func(task)
            if show_result_message:
                self.result_messages.append(result)
    dash_mod.DashboardModel = FakeDash
    monkeypatch.setitem(sys.modules, "snappy.model.dashboard", dash_mod)

    sys.modules.pop("snappy.controller.catalogue", None)
    import snappy.controller.catalogue as catalogue_module
    from snappy.domain.data import SnappySnapshotData
    monkeypatch.setattr(catalogue_module, "get_system_username", lambda: "Author")
    
    search_page_calls = []
    ctrl = catalogue_module.CatalogueController(FakeDash(), lambda s: search_page_calls.append(s))
    ctrl.init()
    catalogue = ctrl.dash_model.snap_catalogue
    folder_paths = [tmp_path / "local folder", tmp_path / "other folder"]
    list_associated_folders = Mock(return_value=folder_paths)
    remove_associated_folders = Mock(return_value=Path("/backups/remove.zip"))
    monkeypatch.setattr(catalogue_module, "get_associated_folders_to_delete", list_associated_folders)
    monkeypatch.setattr(catalogue_module, "delete_associated_folders", remove_associated_folders)
    
    ctrl.update_data(SnappySnapshotData([]))
    
    snap = Snapshot("s1", "Snap1", "Original", tags=["test"], data={"visible": "old"})
    catalogue.get_by_id.return_value = snap
    
    from snappy.model.history import ActionType
    # The create form captures local folders.
    ctrl.view.signal_create_requested.emit()
    catalogue.create_snapshot.assert_called_once_with(
        snap_id="d1", name="D1", desc="Description", author="Author", tags=["test"],
        directory_paths=["/source/one"], data={"visible": "value"},
        progress_callback=task.update_task_progress, message_callback=task.update_task_message,
    )
    assert actions[-1][1] == ActionType.CATALOGUE_SNAPSHOT_CREATED

    # ZIP import goes through the corresponding library entry points.
    ctrl.view.signal_import_requested.emit()
    catalogue.import_snapshot.assert_called_once_with(Path(FakeQFileDialog.zip_file))
    assert actions[-1][1:] == (ActionType.CATALOGUE_SNAPSHOTS_IMPORTED, "example.zip (1)")
    assert ctrl.dash_model.result_messages[-1][0] == "Import complete"
    FakeQInputDialog.source_index = 1
    catalogue.get_all.side_effect = [[snap], [snap, FakeSnapshot("s2", "Imported")]]
    ctrl.view.signal_import_requested.emit()
    catalogue.import_catalogue.assert_called_once_with(Path(FakeQFileDialog.zip_file))
    assert actions[-1][1:] == (ActionType.CATALOGUE_SNAPSHOTS_IMPORTED, "example.zip (1)")
    assert ctrl.dash_model.result_messages[-1][0] == "Archive processed"

    catalogue.import_catalogue_with_report = Mock(return_value=types.SimpleNamespace(
        imported=["s2"], skipped=["s1"], failed={"s3": "Missing capture."},
    ))
    ctrl.view.signal_import_requested.emit()
    catalogue.import_catalogue_with_report.assert_called_once_with(Path(FakeQFileDialog.zip_file))
    title, description = ctrl.dash_model.result_messages[-1]
    assert title == "Import incomplete"
    assert "Imported: 1. Already present: 1. Failed: 1." in description
    assert "s3: Missing capture." in description
    FakeQInputDialog.source_index = 0
    filename = FakeQFileDialog.zip_file
    FakeQFileDialog.zip_file = ""
    ctrl.view.signal_import_requested.emit()
    assert catalogue.import_snapshot.call_count == 1
    FakeQFileDialog.zip_file = filename
    
    # __open_config_dialog (edit_mode=True) -> signal_edit_requested
    ctrl.view.signal_edit_requested.emit(snap)
    catalogue.update_snapshot_with_result.assert_called_once_with(
        "s1", name="D1", desc="Description", tags=None, directory_paths=None,
        data_updates={"visible": "value"}, message_callback=task.update_task_message,
    )
    assert actions[-1][1:] == (ActionType.CATALOGUE_SNAPSHOT_UPDATED, "Edited")

    retained_form = dict(form_data)
    externally_edited = snap.clone()
    externally_edited.name = "Concurrent name"
    externally_edited.data["visible"] = "concurrent value"
    externally_edited.date_created += timedelta(seconds=1)  # Legacy JSON can omit this timestamp.
    form_data.update(name=snap.name, custom_data={"visible": "old", "unset": ""})
    catalogue.get_by_id.return_value = externally_edited
    ctrl.view.signal_edit_requested.emit(snap)
    assert "name" not in catalogue.update_snapshot_with_result.call_args.kwargs
    assert catalogue.update_snapshot_with_result.call_args.kwargs["data_updates"] is None

    form_data["name"] = "Different name"
    edit_call_count = catalogue.update_snapshot_with_result.call_count
    ctrl.view.signal_edit_requested.emit(snap)
    assert catalogue.update_snapshot_with_result.call_count == edit_call_count
    catalogue.get_by_id.return_value = snap
    form_data.update(retained_form)

    form_data["directories_changed"] = True
    ctrl.view.signal_edit_requested.emit(snap)
    assert catalogue.update_snapshot_with_result.call_args.kwargs["directory_paths"] == ["/source/one"]
    
    # __install_snapshot
    confirmed_target = tmp_path / "install target"
    snap.directories = [SnapDirAssociation(0, str(confirmed_target), "folder")]
    prior_actions = len(actions)
    ctrl.view.signal_install_requested.emit(snap)
    assert install_confirmations[-1] == ([confirmed_target], True)
    catalogue.install_with_result.assert_called_once_with(
        snap, clear_destination=True, progress_callback=task.update_task_progress, message_callback=task.update_task_message,
    )
    assert [action[1] for action in actions[prior_actions:]] == [ActionType.CATALOGUE_SNAPSHOT_INSTALLED]

    catalogue.install_with_result.return_value = SnapshotOperationResult(Path("/backups/install.zip"))
    ctrl.view.signal_install_requested.emit(snap)
    
    # __delete_snapshot
    ctrl.view.signal_delete_requested.emit(snap)
    catalogue.delete_with_result.assert_called_once_with(snap, message_callback=task.update_task_message)
    assert actions[-1][1] == ActionType.CATALOGUE_SNAPSHOT_DELETED
    
    # __open_snap_directory (exists mock)
    old_exists = Path.exists
    Path.exists = lambda self: True
    ctrl.view.signal_open_folder_requested.emit(snap)
    assert "/snap/dir" in opened[-1]
    
    # __open_snap_directory (not exists mock)
    Path.exists = lambda self: False
    ctrl.view.signal_open_folder_requested.emit(snap)
    assert "no longer exists" in msgs[-1]
    Path.exists = old_exists

    lookup = catalogue.get_snap_directory_path
    catalogue.get_snap_directory_path = Mock(return_value=None)
    ctrl.dash_model.update = Mock()
    opened_before = list(opened)
    ctrl.view.signal_open_folder_requested.emit(snap)
    assert "no longer in the catalogue" in msgs[-1]
    assert opened == opened_before
    ctrl.dash_model.update.assert_called_once_with()
    catalogue.get_snap_directory_path = lookup
    
    # __duplicate_snapshot
    ctrl.view.signal_duplicate_requested.emit(snap)
    assert actions[-1][1] == ActionType.CATALOGUE_SNAPSHOT_DUPLICATED
    
    # sort
    ctrl.view.signal_sort_requested.emit()
    assert ctrl.view.sort_calls == 1
    
    # searcher all
    ctrl.view.signal_search_internal_content_all.emit()
    assert search_page_calls[-1] is None
    
    # searcher single
    ctrl.view.signal_search_internal_content_single.emit(snap)
    assert search_page_calls[-1] == snap
    
    # __export_snapshot
    ctrl.view.signal_export_request_snapshot.emit(snap)
    assert actions[-1][1] == ActionType.CATALOGUE_SNAPSHOT_EXPORTED
    
    # __export_snapshot_folders
    ctrl.view.signal_export_request_assoc_folders.emit(snap)
    assert actions[-1][1] == ActionType.CATALOGUE_ASSOCIATED_FOLDERS_EXPORTED
    catalogue.export_captured_assoc_dirs.assert_called_once_with(
        "s1", Path("/some/dir"), message_callback=task.update_task_message,
    )
    catalogue.export_assoc_dirs.assert_not_called()
    FakeQInputDialog.source_index = 1
    ctrl.view.signal_export_request_assoc_folders.emit(snap)
    catalogue.export_assoc_dirs.assert_called_once_with(
        "s1", Path("/some/dir"), message_callback=task.update_task_message,
    )
    FakeQInputDialog.accepted = False
    ctrl.view.signal_export_request_assoc_folders.emit(snap)
    assert catalogue.export_assoc_dirs.call_count == 1
    FakeQInputDialog.accepted = True
    
    # __delete_snap_installed_dirs
    ctrl.view.signal_delete_installed_folders_requested.emit(snap)
    assert delete_confirmations[-1] == folder_paths
    list_associated_folders.assert_called_once_with(catalogue, "s1")
    remove_associated_folders.assert_called_once_with(
        catalogue, "s1", expected_catalogue_path=catalogue.path_catalogue,
        expected_paths=frozenset(folder_paths), message_callback=task.update_task_message,
    )
    assert actions[-1][1] == ActionType.CATALOGUE_INSTALLED_FOLDERS_DELETED

    list_associated_folders.return_value = []
    confirmation_count = len(delete_confirmations)
    ctrl.view.signal_delete_installed_folders_requested.emit(snap)
    assert "No associated folders" in msgs[-1]
    assert len(delete_confirmations) == confirmation_count
    assert remove_associated_folders.call_count == 1
    list_associated_folders.return_value = folder_paths
    
    # Missing local paths stop the update before the confirmation.
    catalogue.get_sync_plan.side_effect = FileNotFoundError("Original path does not exist")
    ctrl.view.signal_update_with_local_dirs_requested.emit(snap)
    assert "does not exist" in msgs[-1]
    assert not update_confirmations
    catalogue.sync_with_result.assert_not_called()

    plan = types.SimpleNamespace(paths=tuple(folder_paths), emptying_paths=(folder_paths[0],))
    catalogue.get_sync_plan.side_effect = None
    catalogue.get_sync_plan.return_value = plan
    FakeMessageBox.res = False
    ctrl.view.signal_update_with_local_dirs_requested.emit(snap)
    assert update_confirmations[-1] == (plan.paths, plan.emptying_paths)
    catalogue.sync_with_result.assert_not_called()

    FakeMessageBox.res = True
    ctrl.view.signal_update_with_local_dirs_requested.emit(snap)
    catalogue.sync_with_result.assert_called_once_with("s1", expected_plan=plan, message_callback=task.update_task_message)
    assert actions[-1][1] == ActionType.CATALOGUE_ASSOCIATED_FOLDERS_UPDATED
    automatic_backups = {
        (action_type, details)
        for _, action_type, details in actions
        if action_type == ActionType.BACKUP_CREATED
    }
    assert automatic_backups == {
        (ActionType.BACKUP_CREATED, "snapshot=Snap1; before=edit; archive=edit.zip"),
        (ActionType.BACKUP_CREATED, "snapshot=Snap1; before=install; archive=install.zip"),
        (ActionType.BACKUP_CREATED, "snapshot=Snap1; before=delete; archive=delete.zip"),
        (ActionType.BACKUP_CREATED, "snapshot=Snap1; before=remove installed folders; archive=remove.zip"),
        (ActionType.BACKUP_CREATED, "snapshot=Snap1; before=update with local; archive=sync.zip"),
    }
    
    # test cancel modal / dialogs
    FakeDialogConfig.res = False
    ctrl.view.signal_create_requested.emit() # does nothing
    
    FakeMessageBox.res = False
    ctrl.view.signal_install_requested.emit(snap)
    ctrl.view.signal_delete_requested.emit(snap)
    ctrl.view.signal_export_request_snapshot.emit(snap)
    ctrl.view.signal_export_request_assoc_folders.emit(snap)
    ctrl.view.signal_delete_installed_folders_requested.emit(snap)
    assert remove_associated_folders.call_count == 1
    ctrl.view.signal_update_with_local_dirs_requested.emit(snap)
    
    FakeMessageBox.res = True
    FakeQFileDialog.ret = ""
    ctrl.view.signal_export_request_snapshot.emit(snap)
    ctrl.view.signal_export_request_assoc_folders.emit(snap)
    
    # test exceptions
    def error_action(*args, **kw): raise Exception("fail")
    
    import snappy.controller.catalogue
    old_dc = snappy.controller.catalogue.DialogConfig
    snappy.controller.catalogue.DialogConfig = error_action
    ctrl.view.signal_edit_requested.emit(snap) # emits show_message
    snappy.controller.catalogue.DialogConfig = old_dc
    
    old_exec = FakeDialogConfig.exec
    FakeDialogConfig.exec = error_action
    ctrl.view.signal_create_requested.emit() # caught, no assert
    FakeDialogConfig.exec = old_exec
    
    FakeMessageBox.exec_ = lambda self: False
    FakeMessageBox.res = False
    ctrl.view.signal_install_requested.emit(snap)
    ctrl.view.signal_delete_requested.emit(snap)
    ctrl.view.signal_export_request_snapshot.emit(snap)
    ctrl.view.signal_export_request_assoc_folders.emit(snap)
    ctrl.view.signal_delete_installed_folders_requested.emit(snap)
    ctrl.view.signal_update_with_local_dirs_requested.emit(snap)
    
    ctrl.search_page_opener = None
    ctrl.view.signal_search_internal_content_all.emit()
    ctrl.view.signal_search_internal_content_single.emit(snap)
    
    # test duplicate exception
    ctrl.dash_model.run_heavy_operation = error_action
    ctrl.view.signal_duplicate_requested.emit(snap)

