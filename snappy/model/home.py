from pathlib import Path

from PySide6.QtCore import QObject, Signal
from loguru import logger
from pylizlib.core.os.snap import BackupType, SnapshotCatalogue

from snappy.application.app import app_settings, AppSettings
from snappy.domain.data import SnappySnapshotData


class HomeModel(QObject):
    """
    Model for the Home screen.

    Responsible for computing statistics from snapshots and reading 
    global settings like backup counts and catalogue paths.
    Communicates with the Controller exclusively via Signals.
    """
    
    # Emits stats object, backup_count, catalogue_path
    statistics_updated = Signal(object, object, str)

    def __init__(self, parent=None, catalogue: SnapshotCatalogue | None = None):
        """
        Initializes the HomeModel.

        Args:
            parent (QObject, optional): Parent object. Defaults to None.
            catalogue (SnapshotCatalogue, optional): Shared catalogue used to identify managed backups.
        """
        super().__init__(parent)
        self.catalogue = catalogue

    def compute_and_emit_statistics(self, snapshot_data: SnappySnapshotData):
        """
        Computes the latest statistics from snapshot_data and reads global configuration
        (backup counts, catalogue path). Once done, emits the statistics_updated signal.

        Args:
            snapshot_data (SnappySnapshotData): The snapshot data block to analyze.
        """
        logger.debug("Calculating Home statistics...")
        stats = getattr(snapshot_data, "home_statistics", None)
        if stats is None:
            stats = snapshot_data.compute_home_statistics()
        logger.debug(f"Statistics calculated: {stats}")

        # Compute backup count
        backup_path = Path(app_settings.get(AppSettings.backup_path))
        backup_count: int | None = 0 if not backup_path.exists() else None
        if backup_path.exists() and backup_path.is_dir() and self.catalogue is not None:
            managed_backup_types = {
                BackupType.ASSOCIATED_DIRECTORIES,
                BackupType.SNAPSHOT_DIRECTORY,
            }
            try:
                backup_count = sum(
                    1
                    for backup in self.catalogue.list_backups(backup_path)
                    if not backup.is_export
                    and backup.backup_type in managed_backup_types
                    and backup.created_at is not None
                    and bool(backup.snapshot_id)
                )
            except Exception as error:
                logger.warning(f"Cannot count managed backups in '{backup_path}': {error}")
        elif backup_path.exists() and not backup_path.is_dir():
            logger.warning(f"Backup path is not a directory: {backup_path}")

        # Get catalogue path
        catalogue_path = app_settings.get(AppSettings.catalogue_path)
        
        # Emit signal to notify that data has changed
        self.statistics_updated.emit(stats, backup_count, str(catalogue_path))
