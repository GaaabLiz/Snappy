"""Plan and remove the local folders associated with a selected snapshot."""

import stat
from collections.abc import Collection
from dataclasses import replace
from pathlib import Path

from pylizlib.core.os.filesystem.directories import remove_directory_or_move_to_temp
from pylizlib.core.os.paths.safety import assert_no_link_components
from pylizlib.core.os.snap import (
    BackupType,
    SnapDirAssociation,
    Snapshot,
    SnapshotCatalogue,
    SnapshotManager,
)
from pylizlib.core.os.snap.callbacks import MessageCallback
from pylizlib.core.os.snap.operations.destinations import validate_destructive_destinations
from pylizlib.core.os.snap.storage.coordination import catalogue_access, observer_callback

from snappy.application.i18n import tr


def _existing_associations(
    catalogue: SnapshotCatalogue, snapshot_id: str
) -> tuple[Snapshot, list[tuple[SnapDirAssociation, Path]]]:
    """Load and validate the selected snapshot's local directories under the catalogue lock."""
    snapshot = catalogue.get_by_id(snapshot_id)
    if snapshot is None:
        raise ValueError(tr("This snapshot is no longer in the catalogue."))

    targets = []
    for association in snapshot.directories:
        path = Path(association.original_path).absolute()
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(mode):
            raise NotADirectoryError(
                tr("The associated path {path} must point to a local folder.", path=path)
            )
        targets.append((association, path))

    if targets:
        validate_destructive_destinations(
            ((association.folder_id, path) for association, path in targets),
            catalogue_path=catalogue.path_catalogue,
            origin_os=snapshot.os_created,
            operation="delete associated folders",
        )
    return snapshot, targets


def get_associated_folders_to_delete(catalogue: SnapshotCatalogue, snapshot_id: str) -> list[Path]:
    """List the exact local directories to show in the removal confirmation."""
    with catalogue_access(catalogue.path_catalogue, write=False):
        _, targets = _existing_associations(catalogue, snapshot_id)
        return [path for _, path in targets]


def delete_associated_folders(
    catalogue: SnapshotCatalogue,
    snapshot_id: str,
    *,
    expected_catalogue_path: Path,
    expected_paths: Collection[Path],
    message_callback: MessageCallback | None = None,
) -> Path | None:
    """Recheck the confirmed paths, back them up and remove their live contents."""
    with catalogue_access(catalogue.path_catalogue):
        if catalogue.path_catalogue != expected_catalogue_path:
            raise ValueError(tr("The catalogue changed. Review the folder list and try again."))
        snapshot, targets = _existing_associations(catalogue, snapshot_id)
        if {path for _, path in targets} != set(expected_paths):
            raise ValueError(tr("The associated folders changed. Review the list and try again."))
        if not targets:
            return None

        backup_path = catalogue.settings.backup_path
        if backup_path is None:
            raise ValueError(tr("Set a backup folder before deleting associated folders."))
        backup_snapshot = replace(snapshot, directories=[association for association, _ in targets])
        manager = SnapshotManager(backup_snapshot, catalogue.path_catalogue, catalogue.settings)
        archive = manager.create_backup(
            backup_path,
            "beforeRemove",
            BackupType.ASSOCIATED_DIRECTORIES,
            message_callback=message_callback,
        )

        observer = observer_callback(message_callback)
        for _, path in targets:
            try:
                assert_no_link_components(path)
                remove_directory_or_move_to_temp(path, message_callback=observer)
            except Exception as error:
                raise RuntimeError(
                    tr(
                        "Could not delete {path}. The backup is saved at {archive}. {error}",
                        path=path,
                        archive=archive,
                        error=error,
                    )
                ) from error
        return archive
