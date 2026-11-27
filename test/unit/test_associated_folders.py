from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pylizlib.core.os.snap import SnapshotBusyError, SnapshotCatalogue, SnapshotSettings
from pylizlib.core.os.snap.storage.install_registry import InstalledCopyRegistry

from snappy.model import associated_folders
from snappy.model.associated_folders import (
    delete_associated_folders,
    get_associated_folders_to_delete,
    get_installation_plan,
    install_confirmed_snapshot,
)


@pytest.fixture
def workspace():
    # Snapshot safety checks reject OS-managed temporary directories.
    repo = Path(__file__).resolve().parents[2]
    with TemporaryDirectory(prefix=".test-associated-folders-", dir=repo) as folder:
        yield Path(folder)


@pytest.mark.parametrize("below_shared_folder", [False, True])
def test_delete_uses_selected_paths_even_when_another_snapshot_installed_there(
    workspace, monkeypatch, below_shared_folder
):
    shared = workspace / "local-project"
    nested = shared / "config"
    nested.mkdir(parents=True)
    data = nested / "settings.txt"
    data.write_text("captured settings", encoding="utf-8")
    absent = workspace / "absent"
    absent.mkdir()
    untouched = workspace / "unassociated"
    untouched.mkdir()
    catalogue = SnapshotCatalogue(
        workspace / "catalogue", SnapshotSettings(backup_path=workspace / "backups")
    )
    first = catalogue.create_snapshot(
        snap_id="first", name="First", directory_paths=[shared, absent]
    )
    second = catalogue.create_snapshot(
        snap_id="second", name="Second", directory_paths=[nested if below_shared_folder else shared]
    )
    catalogue.install(second)
    data.write_text("current local data", encoding="utf-8")
    absent.rmdir()

    def reject_registry_lookup(*args, **kwargs):
        pytest.fail("Removal consulted the installation registry")

    monkeypatch.setattr(InstalledCopyRegistry, "get", reject_registry_lookup)
    paths = get_associated_folders_to_delete(catalogue, first.id)
    assert paths == [shared]
    archive = delete_associated_folders(
        catalogue,
        first.id,
        expected_catalogue_path=catalogue.path_catalogue,
        expected_paths=paths,
    )

    assert not shared.exists()
    assert untouched.is_dir()
    assert catalogue.get_by_id(first.id).directories == first.directories
    assert catalogue.get_by_id(second.id).directories == second.directories
    assert archive is not None
    catalogue.restore_backup(archive)
    assert data.read_text(encoding="utf-8") == "current local data"
    assert not absent.exists()


def test_delete_rechecks_associations_after_confirmation(workspace):
    previous = workspace / "previous"
    replacement = workspace / "replacement"
    previous.mkdir()
    replacement.mkdir()
    backups = workspace / "backups"
    catalogue = SnapshotCatalogue(workspace / "catalogue", SnapshotSettings(backup_path=backups))
    snapshot = catalogue.create_snapshot(
        snap_id="sample", name="Sample", directory_paths=[previous]
    )
    confirmed = get_associated_folders_to_delete(catalogue, snapshot.id)
    catalogue.update_snapshot(snapshot.id, directory_paths=[replacement])

    with pytest.raises(ValueError, match="folders changed"):
        delete_associated_folders(
            catalogue,
            snapshot.id,
            expected_catalogue_path=catalogue.path_catalogue,
            expected_paths=confirmed,
        )
    assert previous.is_dir() and replacement.is_dir()
    assert not backups.exists()


def test_delete_requires_backup_for_a_folder_created_outside_snappy(workspace):
    source = workspace / "local-data"
    source.mkdir()
    data = source / "settings.txt"
    data.write_text("local data", encoding="utf-8")
    blocked = workspace / "backups"
    blocked.touch()
    catalogue = SnapshotCatalogue(workspace / "catalogue", SnapshotSettings(backup_path=blocked))
    snapshot = catalogue.create_snapshot(snap_id="sample", name="Sample", directory_paths=[source])
    confirmed = get_associated_folders_to_delete(catalogue, snapshot.id)
    assert confirmed == [source]

    with pytest.raises(OSError):
        delete_associated_folders(
            catalogue,
            snapshot.id,
            expected_catalogue_path=catalogue.path_catalogue,
            expected_paths=confirmed,
        )
    assert data.read_text(encoding="utf-8") == "local data"


@pytest.mark.parametrize(("change", "message"), [("association", "folders changed"), ("mode", "mode changed")])
def test_install_rejects_changes_after_confirmation(workspace, monkeypatch, change, message):
    first = workspace / "A"
    second = workspace / "B"
    first.mkdir()
    second.mkdir()
    (first / "config.ini").write_text("captured", encoding="utf-8")
    (second / "config.ini").write_text("keep B", encoding="utf-8")
    backup_path = workspace / "backups"
    settings = SnapshotSettings(backup_path=backup_path, backup_pre_install=True)
    catalogue = SnapshotCatalogue(workspace / "catalogue", settings)
    other = SnapshotCatalogue(catalogue.path_catalogue, settings)
    snapshot = catalogue.create_snapshot(snap_id="sample", name="Sample", directory_paths=[first])
    (first / "config.ini").write_text("keep A", encoding="utf-8")
    mode = True
    monkeypatch.setattr(associated_folders.app_settings, "get", lambda _: mode)
    confirmed = get_installation_plan(catalogue, snapshot.id)
    assert confirmed.paths == [first]
    assert confirmed.clear_destination is True

    if change == "association":
        other.update_snapshot(snapshot.id, directory_paths=[second])
    else:
        mode = False

    with pytest.raises(ValueError, match=message):
        install_confirmed_snapshot(catalogue, confirmed)
    assert (first / "config.ini").read_text(encoding="utf-8") == "keep A"
    assert (second / "config.ini").read_text(encoding="utf-8") == "keep B"
    assert not backup_path.exists()


@pytest.mark.parametrize("mode", [False, True])
def test_confirmed_install_keeps_lock_between_verification_and_install(workspace, monkeypatch, mode):
    source = workspace / "source"
    source.mkdir()
    (source / "config.ini").write_text("captured", encoding="utf-8")
    settings = SnapshotSettings()
    catalogue = SnapshotCatalogue(workspace / "catalogue", settings)
    other = SnapshotCatalogue(catalogue.path_catalogue, settings)
    snapshot = catalogue.create_snapshot(snap_id="sample", name="Sample", directory_paths=[source])
    extra = source / "keep-in-merge.txt"
    extra.touch()
    monkeypatch.setattr(associated_folders.app_settings, "get", lambda _: mode)
    confirmed = get_installation_plan(catalogue, snapshot.id)
    install = catalogue.install_with_result

    with ThreadPoolExecutor(max_workers=1) as executor:
        def install_while_recheck_lock_is_held(*args, **kwargs):
            with pytest.raises(SnapshotBusyError):
                executor.submit(other.update_snapshot, snapshot.id, name="Changed").result(timeout=5)
            return install(*args, **kwargs)

        monkeypatch.setattr(catalogue, "install_with_result", install_while_recheck_lock_is_held)
        install_confirmed_snapshot(catalogue, confirmed)

    assert extra.exists() is (not mode)
