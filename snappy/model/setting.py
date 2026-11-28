from pathlib import Path

from PySide6.QtCore import QObject, Signal
from loguru import logger

from snappy.application.app import app_settings, AppSettings, snap_settings
from snappy.application.i18n import tr
from snappy.model.history import log_action, ActionCategory, ActionType


class SettingModel(QObject):
    """
    Model for application settings.

    Handles business logic related to changing configuration paths,
    clearing backups, and synchronizing global state.
    It communicates with the Controller exclusively via Signals.
    """

    # Signals
    catalogue_path_updated = Signal(str)
    backup_path_updated = Signal(str)
    settings_synchronized = Signal()

    def __init__(self, dash_model, parent=None):
        """
        Initializes the SettingModel.

        Args:
            dash_model: The dashboard model, required to access the catalogue.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self.dash_model = dash_model

        # Connect AppSettings changes to the synchronization method
        AppSettings.backup_before_install.valueChanged.connect(self.sync_snap_settings)
        AppSettings.backup_before_edit.valueChanged.connect(self.sync_snap_settings)
        AppSettings.backup_before_delete.valueChanged.connect(self.sync_snap_settings)

    def set_catalogue_path(self, directory: str):
        """
        Updates the global catalogue path and logs the action.

        Args:
            directory (str): The new catalogue directory path.
        """
        if self.dash_model.operation_active:
            return False
        catalogue_path = Path(directory)
        if not catalogue_path.is_absolute():
            raise ValueError(tr("Choose an absolute catalogue path."))

        previous_setting_path = app_settings.get(AppSettings.catalogue_path)
        previous_backend_path = getattr(self.dash_model.snap_catalogue, "path_catalogue", previous_setting_path)
        self.dash_model.operation_active = True
        try:
            logger.info(f"Changing catalogue path to: {directory}")
            self.dash_model.snap_catalogue.set_catalogue_path(catalogue_path)
            app_settings.set(AppSettings.catalogue_path, str(catalogue_path))
            if previous_backend_path != catalogue_path:
                self.dash_model.invalidate_catalogue_data()
            log_action(ActionCategory.SETTINGS, ActionType.SETTINGS_CATALOGUE_PATH_CHANGED, directory)
            self.catalogue_path_updated.emit(directory)
        except Exception:
            self.dash_model.snap_catalogue.path_catalogue = previous_backend_path
            try:
                if app_settings.get(AppSettings.catalogue_path) != previous_setting_path:
                    app_settings.set(AppSettings.catalogue_path, previous_setting_path)
            except Exception as rollback_error:
                logger.error("Unable to restore the configured catalogue path: {}", rollback_error)
            logger.exception("Failed to change catalogue path; restored the previous path.")
            raise

        finally:
            self.dash_model.operation_active = False

        # We also trigger a dashboard update since the catalogue path changed
        self.dash_model.update()

    def set_backup_path(self, directory: str):
        """
        Updates the global backup path and synchronizes snapshot settings.

        Args:
            directory (str): The new backup directory path.
        """
        if self.dash_model.operation_active:
            return False
        backup_path = Path(directory)
        option = AppSettings.backup_path
        previous_path = app_settings.get(option)
        try:
            app_settings.set(option, backup_path)
        except Exception:
            # QConfig changes the in-memory value before it attempts to save.
            app_settings.set(option, previous_path, save=False)
            raise

        snap_settings.backup_path = backup_path
        logger.info(f"Backup path changed to: {directory}")
        log_action(ActionCategory.SETTINGS, ActionType.SETTINGS_BACKUP_PATH_CHANGED, directory)
        self.backup_path_updated.emit(directory)
        self.dash_model.update()

    def clear_backup_directory(self) -> int:
        """Remove managed backups through the catalogue operation."""
        catalogue = self.dash_model.snap_catalogue
        backup_path = catalogue.settings.backup_path
        deleted_count = catalogue.clear_managed_backups()
        logger.info("Backup directory cleanup completed: {} file(s) deleted from {}", deleted_count, backup_path)
        log_action(ActionCategory.SETTINGS, ActionType.SETTINGS_BACKUP_CLEANED, f"path={backup_path}; deleted={deleted_count}")
        return deleted_count

    def sync_snap_settings(self, *args, **kwargs):
        """
        Synchronizes snapshot-specific settings with global application settings.
        """
        snap_settings.backup_pre_install = app_settings.get(AppSettings.backup_before_install)
        snap_settings.backup_pre_modify = app_settings.get(AppSettings.backup_before_edit)
        snap_settings.backup_pre_delete = app_settings.get(AppSettings.backup_before_delete)
        self.settings_synchronized.emit()

    def log_restart_confirmed(self):
        """
        Logs that the user confirmed the application restart due to theme/language change.
        """
        logger.info("User confirmed restart for language/theme change")
        log_action(ActionCategory.SETTINGS, ActionType.SETTINGS_RESTART_CONFIRMED, "theme/language change")
