from PySide6.QtCore import QObject, Signal

from snappy.application.app import app_settings, AppSettings
from snappy.domain.data import SnappySnapshotData


class HomeModel(QObject):
    """Publish dashboard refresh results to the Home view."""

    statistics_updated = Signal(object, object, str)

    def emit_statistics(self, snapshot_data: SnappySnapshotData):
        stats = snapshot_data.home_statistics
        catalogue_path = stats.catalogue_path if stats is not None else app_settings.get(AppSettings.catalogue_path)
        self.statistics_updated.emit(stats, snapshot_data.backup_count, str(catalogue_path))
