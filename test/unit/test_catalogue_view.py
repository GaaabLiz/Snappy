import pytest

from snappy.view.catalogue import DeleteAssociatedFoldersDialog, InstallSnapshotDialog, SnapshotCatalogueWidget, UpdateSnapshotDialog
from pylizlib.core.os.snap import SnapshotSortKey

def test_catalogue_view(qtbot):
    from PySide6.QtGui import QStandardItemModel
    class DummyModel:
        def get_all_snapshots(self): return []
        def filter(self, *args): pass
        table_model = QStandardItemModel()
    view = SnapshotCatalogueWidget(DummyModel())
    qtbot.addWidget(view)
    
    # Sort Type changed
    view._on_sort_type_changed(SnapshotSortKey.NAME)
    assert view._current_sort_key == SnapshotSortKey.NAME
    
    # Sort Direction changed
    view._on_sort_direction_changed(True)
    assert view._current_sort_reverse == True
    
    # Selection changed
    view.table.clearSelection()
    view._on_item_selection_changed()
    assert view.action_edit.isEnabled() == False


def test_delete_folder_confirmation_shows_every_path_literally(qtbot, tmp_path):
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    paths = [tmp_path / "Project & config <b>", *(tmp_path / f"folder {i}" for i in range(50))]
    dialog = DeleteAssociatedFoldersDialog(paths, parent)
    qtbot.addWidget(dialog)
    assert dialog.path_list.toPlainText().splitlines() == [str(path) for path in paths]
    assert dialog.path_list.isReadOnly()
    assert dialog.cancelButton.isDefault()
    



@pytest.mark.parametrize(("clear_destination", "label"), [(True, "Replace folders"), (False, "Merge folders")])
def test_install_confirmation_shows_paths_and_mode(qtbot, tmp_path, clear_destination, label):
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    paths = [tmp_path / "Config <b>", tmp_path / "Missing folder"]
    dialog = InstallSnapshotDialog(paths, clear_destination, parent)
    qtbot.addWidget(dialog)

    assert dialog.path_list.toPlainText().splitlines() == [str(path) for path in paths]
    assert dialog.viewLayout.itemAt(1).widget().text().startswith(label)
    assert dialog.cancelButton.isDefault()


def test_update_confirmation_marks_folders_that_will_be_emptied(qtbot, tmp_path):
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    populated = tmp_path / "populated"
    empty = tmp_path / "empty mount point"
    dialog = UpdateSnapshotDialog([populated, empty], [empty], parent)
    qtbot.addWidget(dialog)

    assert dialog.path_list.toPlainText().splitlines() == [
        str(populated),
        f"{empty} (will empty the stored copy)",
    ]
    assert "erase the contents" in dialog.viewLayout.itemAt(1).widget().text()
    assert dialog.yesButton.text() == "Update anyway"
    assert dialog.cancelButton.isDefault()
