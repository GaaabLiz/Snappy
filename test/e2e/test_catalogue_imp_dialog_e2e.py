import json
from zipfile import ZipFile

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QInputDialog

from snappy.domain.data import SnappyData
from snappy.view.catalogue_imp_dialog import DialogConfig

def test_catalogue_import_dialog_e2e(qtbot, monkeypatch, tmp_path):
    """
    Test E2E for the Catalogue Import Dialog.
    Navigates to the details tab, inputs text, tests validation, and clicks create.
    """
    
    from qfluentwidgets import MessageBox
    monkeypatch.setattr(MessageBox, "exec", lambda self: True)
    monkeypatch.setattr(MessageBox, "exec_", lambda self: True)

    # Empty data
    data = SnappyData(monitored_software=[], monitored_services=None, snapshots=[])

    dialog = DialogConfig(snappy_data=data, edit_mode=False, catalogue_path=tmp_path / "catalogue")
    qtbot.addWidget(dialog)

    # Show the dialog but don't block the event loop with exec()
    dialog.show()
    qtbot.waitForWindowShown(dialog)

    # The create button is enabled by default, but validation will fail if empty
    assert dialog.btn_create.isEnabled()

    # Mock UiUtils to track messages
    import snappy.view.catalogue_imp_dialog
    messages = []
    class FakeUiUtils:
        @classmethod
        def show_message(cls, title, text, parent=None):
            messages.append(text)
    monkeypatch.setattr(snappy.view.catalogue_imp_dialog, "UiUtils", FakeUiUtils)

    # Click create while empty
    qtbot.mouseClick(dialog.btn_create, Qt.LeftButton)

    # Validation message should be shown
    assert len(messages) > 0

    # Get the details tab
    details_tab = dialog._DialogConfig__tabs.tab_details

    # Type name and description
    qtbot.keyClicks(details_tab.form_name_input, "Test Config")
    qtbot.keyClicks(details_tab.form_desc_input, "Test Description")

    # Ensure UI reflects input
    assert details_tab.form_name_input.text() == "Test Config"
    
    # Click tags input to trigger the no-tags MessageBox
    qtbot.mouseClick(details_tab.form_tags_input, Qt.LeftButton)
    
    # pytest uses a system temporary directory. Exercise the destination checks
    # with their normal overlap logic and a local test root.
    monkeypatch.setattr("pylizlib.core.os.snap.operations.destinations.is_critical_system_path", lambda _: False)
    directories_tab = dialog._DialogConfig__tabs.tab_directories
    source = tmp_path / "source"
    child = source / "child"
    child.mkdir(parents=True)
    directories_tab.add_directory(source)
    directories_tab.add_directory(child)
    qtbot.mouseClick(dialog.btn_create, Qt.LeftButton)
    assert dialog.output_data is None
    assert "cannot be coincident or nested" in messages[-1]

    directories_tab._TabDirectories__delete_selected_item(directories_tab.listWidget.item(1))
    
    # Click the create button again
    qtbot.mouseClick(dialog.btn_create, Qt.LeftButton)

    # Check that output data is formed properly
    assert getattr(dialog, 'output_data', None) is not None
    assert dialog.output_data['name'] == "Test Config"
    assert dialog.output_data['desc'] == "Test Description"


@pytest.mark.parametrize("batch", [False, True])
def test_import_zip_action_migrates_a_legacy_snapshot(qtbot, monkeypatch, tmp_path, batch):
    from snappy.application.app import AppSettings, app_settings
    from snappy.controller.catalogue import CatalogueController
    from snappy.model.dashboard import DashboardModel

    previous_path = app_settings.get(AppSettings.catalogue_path)
    app_settings.set(AppSettings.catalogue_path, str(tmp_path / "catalogue"))
    try:
        dashboard = DashboardModel()
        monkeypatch.setattr(dashboard.snap_catalogue.settings, "allow_unverified_legacy_snapshots", True)
        controller = CatalogueController(dashboard)
        qtbot.addWidget(controller.view)
        controller.init()

        zip_path = tmp_path / "legacy.zip"
        prefix = "legacy/" if batch else ""
        metadata = {
            "id": "legacy",
            "name": "Legacy",
            "desc": "",
            "directories": [{"index": 1, "folder_id": "stable", "original_path": str(tmp_path / "data")}],
        }
        with ZipFile(zip_path, "w") as archive:
            archive.writestr(f"{prefix}snapshot.json", json.dumps(metadata))
            archive.writestr(f"{prefix}1-data/settings.txt", b"legacy content")

        monkeypatch.setattr(QInputDialog, "getItem", lambda _parent, _title, _text, options, *_: (options[batch], True))
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_: (str(zip_path), ""))
        errors = []
        dashboard.signal_on_heavy_operation_error.connect(lambda _title, error: errors.append(error))
        with qtbot.waitSignal(dashboard.signal_on_update_complete, timeout=5000):
            controller.view.action_import.trigger()

        assert errors == []
        (snapshot,) = dashboard.cached_data.snapshots
        assert snapshot.id == "legacy"
        assert snapshot.directories[0].integrity_manifest["settings.txt"]["size"] == len(b"legacy content")
        dashboard.runner.thread_pool.waitForDone()
    finally:
        app_settings.set(AppSettings.catalogue_path, previous_path)
