import os
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QUrl, Qt, QTimer
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtWidgets import QFileDialog, QApplication
from pylizlib.qtfw.widgets.dialog.about import AboutMessageBox
from qfluentwidgets import MessageBox, InfoBar, InfoBarPosition

from snappy.application.app import app, RESOURCE_ID_LOGO
from snappy.application.i18n import tr
from snappy.model.dashboard import DashboardModel
from snappy.model.setting import SettingModel
from snappy.view.setting import WidgetSettings


class SettingController:
    """
    Controller for managing application settings.

    This controller handles interactions on the settings view, allowing the user
    to modify application configurations such as paths, language, theme, and more.
    It orchestrates the SettingModel and WidgetSettings by connecting their signals.
    """

    def __init__(self, dash_model: DashboardModel):
        """
        Initializes the SettingController.

        Args:
            dash_model (DashboardModel): The dashboard model, required to trigger UI updates
                and access the catalogue when settings change.
        """
        self.dash_model = dash_model
        
        # Instantiate Model and View
        self.model = SettingModel(dash_model)
        self.view = WidgetSettings()
        self._restart_pending = False

        # Connections: View -> Controller/Model
        self.view.signal_request_update.connect(self.dash_model.update)
        self.view.signal_ask_catalogue_path.connect(self.__ask_catalogue_path)
        self.view.signal_ask_backup_path.connect(self.__ask_backup_path)
        self.view.signal_open_dir_request.connect(self.__open_directory)
        self.view.signal_clear_backups_request.connect(self.__clear_backup_directory)
        self.view.signal_open_about_dialog_request.connect(self.__open_info_dialog)
        self.view.signal_language_changed.connect(self.__on_language_or_theme_changed)
        self.view.signal_theme_changed.connect(self.__on_language_or_theme_changed)

        # Connections: Model -> View/Controller
        self.model.catalogue_path_updated.connect(self.__on_catalogue_path_updated)
        self.model.backup_path_updated.connect(self.__on_backup_path_updated)

    def __on_catalogue_path_updated(self, directory: str):
        self.view.update_catalogue_path(directory)

    def __on_backup_path_updated(self, directory: str):
        self.view.update_backup_path(directory)

    def __on_language_or_theme_changed(self):
        """
        Handles language or theme changes by prompting the user to restart the application.

        If confirmed, it waits for active operations to finish before restarting.
        """
        if self._restart_pending:
            return

        w = MessageBox(tr("Restart required"), tr("The application needs to restart to apply the changes. Restart now?"), parent=self.view)
        if w.exec_():
            self._restart_pending = True
            if self.dash_model.operation_active:
                InfoBar.info(
                    title=tr("Restart queued"),
                    content=tr("The application will restart when current operations finish."),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=5000,
                    parent=self.view,
                )
                QTimer.singleShot(100, self.__restart_when_idle)
                return
            self.__restart_when_idle()

    def __restart_when_idle(self):
        """Waits for current work, then starts a replacement process before quitting."""
        if not self._restart_pending:
            return
        if self.dash_model.operation_active:
            QTimer.singleShot(100, self.__restart_when_idle)
            return

        args = sys.argv[:]
        if not args:
            self.__show_restart_error(tr("The application entry point is unavailable."))
            return
        try:
            if getattr(sys, "frozen", False):
                environment = QProcessEnvironment.systemEnvironment()
                environment.insert("PYINSTALLER_RESET_ENVIRONMENT", "1")
                process = QProcess()
                process.setProcessEnvironment(environment)
                process.setProgram(sys.executable)
                process.setArguments(args[1:])
                result = process.startDetached()
            else:
                args[0] = os.path.abspath(args[0])
                result = QProcess.startDetached(sys.executable, args)
            started = result[0] if isinstance(result, tuple) else bool(result)
        except Exception as error:
            started = False
            error_detail = str(error)
        else:
            error_detail = tr("Qt did not start the process.")

        if not started:
            self.__show_restart_error(error_detail)
            return

        self.model.log_restart_confirmed()
        self._restart_pending = False
        QApplication.instance().quit()

    def __show_restart_error(self, error: str):
        """Leaves the current session running and reports a failed restart."""
        self._restart_pending = False
        MessageBox(
            tr("Error"),
            tr("The new application process could not be started: {error}", error=error),
            parent=self.view,
        ).exec_()

    def __ask_catalogue_path(self):
        """
        Opens a directory selection dialog to choose a new catalogue path.
        Delegates the logic to the model.
        """
        if self.dash_model.operation_active:
            return
        directory = QFileDialog.getExistingDirectory(None, tr("Select the catalogue folder"))
        if directory:
            try:
                self.model.set_catalogue_path(directory)
            except Exception as error:
                MessageBox(
                    tr("Error"),
                    tr("The catalogue path could not be changed: {error}", error=str(error)),
                    parent=self.view,
                ).exec_()

    def __ask_backup_path(self):
        """
        Opens a directory selection dialog to choose a new backup path.
        Delegates the logic to the model.
        """
        directory = QFileDialog.getExistingDirectory(None, tr("Select the backup folder"))
        if directory:
            try:
                self.model.set_backup_path(directory)
            except Exception as error:
                MessageBox(
                    tr("Error"),
                    tr("The backup path could not be saved: {error}", error=str(error)),
                    parent=self.view,
                ).exec_()

    def __open_directory(self):
        """
        Opens the application's internal configuration directory in the file explorer.
        """
        path = app.path
        if Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def __clear_backup_directory(self):
        """
        Prompts the user for confirmation and then commands the model to delete 
        all application-managed backups.
        """
        w = MessageBox(
            tr("Backup folder cleanup"),
            tr(
                "Are you sure you want to delete all backups created by the application? "
                "Other files in the folder will be preserved."
            ),
            parent=self.view,
        )
        if not w.exec_():
            return

        self.dash_model.run_heavy_operation(
            tr("Clean backups"),
            tr("Cleaning backup folder"),
            self.model.clear_backup_directory,
            success_msg_title=tr("Backups cleaned"),
            success_msg=tr("All application-managed backups were deleted successfully."),
            error_msg_title=tr("Error"),
            error_msg_template=tr("An error occurred while cleaning the backup folder: {error}"),
            update_dashboard=True,
        )

    def __open_info_dialog(self):
        """
        Opens the 'About' dialog displaying application information and version details.
        """
        w = AboutMessageBox(QIcon(RESOURCE_ID_LOGO), app.name, app.version, self.view)
        if w.exec_():
            pass
