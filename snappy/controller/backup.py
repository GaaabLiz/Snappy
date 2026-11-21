from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QDesktopServices
from loguru import logger
from pylizlib.core.os.snap.domain import SnapshotBackupInfo
from qfluentwidgets import MessageBox

from snappy.model.history import log_action, ActionCategory, ActionType
from snappy.application.i18n import tr
from snappy.model.backup import BackupModel
from snappy.model.dashboard import DashboardModel
from snappy.view.backup import BackupView


class BackupController(QObject):
    """
    Controller responsible for managing backups of the catalogue.

    Provides mechanisms to list, open, restore, and delete backups by
    interacting with the SnapshotCatalogue and communicating with the UI view.
    """

    def __init__(self, dash_model: DashboardModel):
        """
        Initializes the BackupController.

        Args:
            dash_model (DashboardModel): Shared catalogue and operation flag.
        """
        super().__init__()
        self.dash_model = dash_model
        self.snap_catalogue = dash_model.snap_catalogue
        self.model = BackupModel()
        self.view = BackupView(self.model)

        self.view.signal_open_requested.connect(self.__handle_open)
        self.view.signal_restore_requested.connect(self.__handle_restore)
        self.view.signal_delete_requested.connect(self.__handle_delete)

    def update_data(self, backups: list[SnapshotBackupInfo]):
        """Display the backups already loaded by the dashboard worker."""
        self.model.set_backups(backups)
        self.view.reload_data()

    def __handle_open(self, backup: SnapshotBackupInfo):
        """
        Opens the directory containing the specified backup in the system's file explorer.

        Args:
            backup (SnapshotBackupInfo): Information about the backup to locate.
        """
        logger.info(f"Opening backup folder in file system: {backup.file_name}")
        folder = backup.path.parent
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
            log_action(ActionCategory.BACKUPS, ActionType.BACKUP_OPENED_IN_FINDER, backup.file_name)
        except Exception as e:
            logger.error(f"Error opening backup folder: {e}")

    def __handle_restore(self, backup: SnapshotBackupInfo):
        """
        Prompts the user for confirmation and restores a given backup if confirmed.

        Overwrites current data with the backup contents and emits a refresh signal
        to update the rest of the application.

        Args:
            backup (SnapshotBackupInfo): Information about the backup to restore.
        """
        w = MessageBox(
            tr("Confirm Restore"),
            tr("Are you sure you want to restore this backup? This will overwrite current data."),
            parent=self.view
        )
        if not w.exec_():
            logger.debug("Backup restore cancelled by user.")
            return

        def action(task):
            task.update_task_message(backup.file_name)
            logger.info(f"Restoring backup {backup.file_name}...")
            self.snap_catalogue.restore_backup(backup.path)
            log_action(ActionCategory.BACKUPS, ActionType.BACKUP_RESTORED, backup.file_name)
            logger.info("Backup restored successfully.")

        self.dash_model.run_heavy_operation(
            tr("Restore backup"),
            tr("Restoring backup"),
            action,
            success_msg_title=tr("Backup restored"),
            success_msg=tr("The backup has been restored successfully."),
            error_msg_title=tr("Error"),
            error_msg_template=tr("An error occurred during restore: {error}"),
            update_dashboard=True,
        )

    def __handle_delete(self, backup: SnapshotBackupInfo):
        """
        Prompts the user for confirmation and deletes the specified backup.

        Args:
            backup (SnapshotBackupInfo): Information about the backup to delete.
        """
        w = MessageBox(
            tr("Confirm Delete"),
            tr("Are you sure you want to delete this backup? This action cannot be undone."),
            parent=self.view
        )
        if not w.exec_():
            logger.debug("Backup deletion cancelled by user.")
            return

        def action(task):
            task.update_task_message(backup.file_name)
            logger.info(f"Deleting backup {backup.file_name}...")
            self.snap_catalogue.delete_backup(backup.path)
            log_action(ActionCategory.BACKUPS, ActionType.BACKUP_DELETED, backup.file_name)
            logger.info("Backup deletion completed.")

        self.dash_model.run_heavy_operation(
            tr("Delete backup"),
            tr("Deleting backup"),
            action,
            success_msg_title=tr("Backup deleted"),
            success_msg=tr("The backup has been deleted successfully."),
            error_msg_title=tr("Error"),
            error_msg_template=tr("An error occurred during deletion: {error}"),
            update_dashboard=True,
        )
