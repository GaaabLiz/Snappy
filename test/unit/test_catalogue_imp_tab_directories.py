from PySide6.QtCore import QPoint
from snappy.view.catalogue_imp_tab_directories import TabDirectories
from pylizlib.core.os.snap import Snapshot, SnapDirAssociation
from pathlib import Path

def test_tab_directories(qtbot, monkeypatch):
    snap = Snapshot(
        id="1",
        name="n",
        desc="d",
        directories=[SnapDirAssociation(original_path="/tmp/dir1", folder_id="fid", index=0)],
    )
    tab = TabDirectories(payload_data=snap, starred_dirs=["/tmp/dir2"])
    qtbot.addWidget(tab)
    
    assert tab.listWidget.count() == 1
    
    # Test checking if directories changed
    assert tab._check_directories_changed() is None
    tab.add_directory(Path("/tmp/dir3"), execute_checks=False)
    assert tab._check_directories_changed() is None  # it emits signal internally
    
    # Test context menu deletion
    import snappy.view.catalogue_imp_tab_directories
    class FakeRoundMenu:
        def __init__(self, parent=None): self.acts = []
        def addAction(self, a): self.acts.append(a)
        def exec(self, pos):
            for a in self.acts: a.trigger()
    monkeypatch.setattr(snappy.view.catalogue_imp_tab_directories, "RoundMenu", FakeRoundMenu)
    
    tab._TabDirectories__show_context_menu(QPoint(0,0))
    # It deletes selected item if one is selected, but let's mock itemAt
    item = tab.listWidget.item(0)
    tab.listWidget.setCurrentItem(item)
    monkeypatch.setattr(tab.listWidget, "itemAt", lambda pos: item)
    tab._TabDirectories__show_context_menu(QPoint(0,0))
    
    # Test add directory via dialog
    class FakeQFileDialog:
        @classmethod
        def getExistingDirectory(cls, *args): return "/tmp/dir4"
    monkeypatch.setattr(snappy.view.catalogue_imp_tab_directories, "QFileDialog", FakeQFileDialog)
    
    # mock exists
    monkeypatch.setattr(Path, "exists", lambda self: True)
    monkeypatch.setattr(Path, "is_dir", lambda self: True)
    
    tab._TabDirectories__on_add_directory_request()
    
    # Try empty path
    class FakeQFileDialogEmpty:
        @classmethod
        def getExistingDirectory(cls, *args): return ""
    monkeypatch.setattr(snappy.view.catalogue_imp_tab_directories, "QFileDialog", FakeQFileDialogEmpty)
    tab._TabDirectories__on_add_directory_request()


def test_tab_directories_compares_paths_in_selection_order(qtbot, monkeypatch, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    alias = first / ".." / first.name
    snap = Snapshot(id="1", name="n", desc="", directories=[
        SnapDirAssociation(original_path=str(first), folder_id="a", index=0),
        SnapDirAssociation(original_path=str(second), folder_id="b", index=1),
    ])
    tab = TabDirectories(payload_data=snap)
    qtbot.addWidget(tab)
    messages = []
    monkeypatch.setattr("snappy.view.catalogue_imp_tab_directories.UiUtils.show_message", lambda *args: messages.append(args))

    tab.add_directory(alias)
    assert tab.directories == [first, second]
    assert messages
    tab.directories[:] = [alias, second]
    assert not tab.directories_changed
    tab.directories.reverse()
    assert tab.directories_changed
