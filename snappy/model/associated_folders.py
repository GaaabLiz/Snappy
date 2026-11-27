"""Confirm and act on the local folders associated with a selected snapshot."""

from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from pylizlib.core.os.snap import (
    Snapshot,
    SnapshotCatalogue,
    SnapshotOperationResult,
    SourceChangedError,
)
from pylizlib.core.os.snap.callbacks import MessageCallback, SnapshotPercentCallback
from pylizlib.core.os.snap.storage.coordination import catalogue_access

from snappy.application.app import AppSettings, app_settings
from snappy.application.i18n import tr


@dataclass(frozen=True)
class InstallationPlan:
    """Exact snapshot targets and mode shown in the installation confirmation."""

    catalogue_path: Path
    snapshot_id: str
    associations: tuple[tuple[str, str], ...]
    clear_destination: bool

    @property
    def paths(self) -> list[Path]:
        return [Path(path) for _, path in self.associations]


def _require_snapshot(catalogue: SnapshotCatalogue, snapshot_id: str) -> Snapshot:
    snapshot = catalogue.get_by_id(snapshot_id)
    if snapshot is None:
        raise ValueError(tr("This snapshot is no longer in the catalogue."))
    return snapshot


def _installation_plan(catalogue: SnapshotCatalogue, snapshot: Snapshot) -> InstallationPlan:
    return InstallationPlan(
        catalogue_path=catalogue.path_catalogue,
        snapshot_id=snapshot.id,
        associations=tuple(
            (association.folder_id, str(Path(association.original_path).absolute()))
            for association in snapshot.directories
        ),
        clear_destination=app_settings.get(AppSettings.clear_snap_attached_folders_before_install),
    )


def get_installation_plan(catalogue: SnapshotCatalogue, snapshot_id: str) -> InstallationPlan:
    """Read the current destinations and mode before showing the confirmation."""
    catalogue_path = catalogue.path_catalogue
    with catalogue_access(catalogue_path, write=False):
        if catalogue.path_catalogue != catalogue_path:
            raise ValueError(tr("The catalogue changed. Review the folder list and try again."))
        return _installation_plan(catalogue, _require_snapshot(catalogue, snapshot_id))


def install_confirmed_snapshot(
    catalogue: SnapshotCatalogue,
    confirmed: InstallationPlan,
    *,
    progress_callback: SnapshotPercentCallback | None = None,
    message_callback: MessageCallback | None = None,
) -> SnapshotOperationResult:
    """Verify the confirmed plan and install while holding the same catalogue lock."""
    catalogue_path = catalogue.path_catalogue
    with catalogue_access(catalogue_path):
        if catalogue.path_catalogue != catalogue_path or catalogue_path != confirmed.catalogue_path:
            raise ValueError(tr("The catalogue changed. Review the folder list and try again."))
        snapshot = _require_snapshot(catalogue, confirmed.snapshot_id)
        current = _installation_plan(catalogue, snapshot)
        if current.associations != confirmed.associations:
            raise ValueError(tr("The associated folders changed. Review the list and try again."))
        if current.clear_destination != confirmed.clear_destination:
            raise ValueError(tr("The installation mode changed. Review the confirmation and try again."))

        return catalogue.install_with_result(
            snapshot,
            clear_destination=confirmed.clear_destination,
            progress_callback=progress_callback,
            message_callback=message_callback,
        )


def get_associated_folders_to_delete(catalogue: SnapshotCatalogue, snapshot_id: str) -> list[Path]:
    """List the exact local directories to show in the removal confirmation."""
    return catalogue.get_associated_paths_for_removal(snapshot_id)


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

        verify_backup = app_settings.get(AppSettings.verify_backup_before_removal)
        try:
            return catalogue.remove_associated_paths(
                snapshot_id,
                expected_paths=expected_paths,
                verify_backup=verify_backup,
                message_callback=message_callback,
            )
        except SourceChangedError as error:
            raise SourceChangedError(tr(
                "The local folders differ from the backup. Deletion was cancelled and the folders were restored. {error}",
                error=error,
            )) from error
