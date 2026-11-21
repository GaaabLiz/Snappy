from pathlib import Path

from loguru import logger
from pylizlib.core.os.snap import BackupType, Snapshot, SnapshotCatalogue, SnapshotCatalogueStatistics
from pylizlib.core.os.commands import is_software_installed
from pylizlib.core.os.windows.processes import WindowsOsUtils
from pylizlib.qt.handler.operation_core import Task
from pylizlib.qtfw.domain.sw import SoftwareData
from qfluentwidgets import FluentIcon

from snappy.application.app import app_settings, AppSettings
from snappy.application.i18n import tr


class TaskGetMonitoredSoftware(Task):
    """
    Task to retrieve the list of monitored software.

    This task fetches the configured software executables from settings and 
    checks their installation status, running state, and version.
    """

    def __init__(self):
        """
        Initializes the TaskGetMonitoredSoftware task.
        """
        super().__init__(tr("Retrieving Monitored Software"))

    def execute(self) -> list[SoftwareData]:
        """
        Executes the task to fetch and process monitored software.

        Returns:
            list[SoftwareData]: A list of SoftwareData objects representing the monitored applications.
        """
        logger.debug("Fetching monitored software list...")
        setting_item = getattr(AppSettings, "starred_exes", None)
        if setting_item is None:
            return []

        data_list: list[str] = app_settings.get(setting_item)
        data_objs: list[SoftwareData] = []
        # for i in range(1, 50000000):
        #     progress = int((i / 50000000) * 100)
            #self.update_task_progress(progress)
        for data in data_list:
            obj = SoftwareData(
                path=Path(data),
                is_service=False,
                icon=FluentIcon.APPLICATION,
                installed=is_software_installed(Path(data)),
                running=WindowsOsUtils.is_exe_running(Path(data)),
                version=WindowsOsUtils.get_windows_exe_version(Path(data))
            )
            data_objs.append(obj)

        return data_objs


class TaskGetSnapshots(Task):
    """
    Task to retrieve all saved snapshots from the catalogue.
    """

    def __init__(self, catalogue: SnapshotCatalogue):
        """
        Initializes the TaskGetSnapshots task.

        Args:
            catalogue (SnapshotCatalogue): The snapshot catalogue instance to query.
        """
        super().__init__(tr("Retrieving saved snapshots"))
        self.catalogue = catalogue
        self.home_statistics: SnapshotCatalogueStatistics | None = None
        self.backup_count: int | None = None

    def execute(self) -> list[Snapshot]:
        """
        Executes the task to fetch all snapshots.

        Returns:
            list[Snapshot]: A list of all available snapshots in the catalogue.
        """
        logger.debug("Fetching saved snapshots...")
        self.home_statistics = None
        self.backup_count = None
        snapshots = self.catalogue.get_all()
        try:
            self.home_statistics = self.catalogue.get_statistics(include_backups=False)
        except Exception as error:
            logger.warning(f"Cannot calculate catalogue statistics: {error}")

        self.backup_count = self._count_managed_backups()
        return snapshots

    def _count_managed_backups(self) -> int | None:
        """Count the automatic backups shown by the Home card."""
        backup_path = self.catalogue.settings.backup_path
        if backup_path is None:
            return 0
        try:
            backup_path.stat()
            return sum(
                1
                for backup in self.catalogue.list_backups(backup_path)
                if not backup.is_export
                and backup.backup_type in (BackupType.ASSOCIATED_DIRECTORIES, BackupType.SNAPSHOT_DIRECTORY)
                and backup.created_at is not None
                and bool(backup.snapshot_id)
            )
        except FileNotFoundError:
            return 0
        except Exception as error:
            logger.warning(f"Cannot count managed backups in '{backup_path}': {error}")
            return None
