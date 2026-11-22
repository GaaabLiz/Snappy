from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from pylizlib.core.os.snap import SnapshotCatalogue, SnapshotSettings
from pylizlib.core.os.snap.storage.install_registry import InstalledCopyRegistry

from snappy.model.associated_folders import (
    delete_associated_folders,
    get_associated_folders_to_delete,
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
