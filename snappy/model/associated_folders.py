"""Confirm and act on the local folders associated with a selected snapshot."""

from collections.abc import Collection
from pathlib import Path

from pylizlib.core.os.snap import (
    SnapshotCatalogue,
    SnapshotInstallationPlan,
    SnapshotOperationResult,
    SourceChangedError,
)
from pylizlib.core.os.snap.callbacks import MessageCallback, SnapshotPercentCallback

from snappy.application.app import AppSettings, app_settings
from snappy.application.i18n import tr


def get_installation_plan(catalogue: SnapshotCatalogue, snapshot_id: str) -> SnapshotInstallationPlan:
    """Read the destinations using the installation mode selected in Snappy."""
    return catalogue.get_installation_plan(
        snapshot_id, clear_destination=app_settings.get(AppSettings.clear_snap_attached_folders_before_install),
    )


def install_confirmed_snapshot(
    catalogue: SnapshotCatalogue,
    confirmed: SnapshotInstallationPlan,
    *,
    progress_callback: SnapshotPercentCallback | None = None,
    message_callback: MessageCallback | None = None,
) -> SnapshotOperationResult:
    """Install using the destinations shown by the confirmation."""
    return catalogue.install_with_result(
        confirmed.snapshot_id,
        clear_destination=app_settings.get(AppSettings.clear_snap_attached_folders_before_install),
        expected_plan=confirmed,
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
    verify_backup = app_settings.get(AppSettings.verify_backup_before_removal)
    try:
        return catalogue.remove_associated_paths(
            snapshot_id,
            expected_catalogue_path=expected_catalogue_path,
            expected_paths=expected_paths,
            verify_backup=verify_backup,
            message_callback=message_callback,
        )
    except SourceChangedError as error:
        raise SourceChangedError(tr(
            "The local folders differ from the backup. Deletion was cancelled and the folders were restored. {error}",
            error=error,
        )) from error
