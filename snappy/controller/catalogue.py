from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from loguru import logger
from pylizlib.core.os.snap import Snapshot, SnapshotBusyError, SnapshotUpdateResult
from pylizlib.core.os.snap.storage.coordination import catalogue_access
from pylizlib.core.os.system import get_system_username
from pylizlib.qtfw.util.ui import UiUtils
from qfluentwidgets import MessageBox

from snappy.application.app import app, AppSettings, app_settings
from snappy.model.history import log_action, ActionCategory, ActionType
from snappy.domain.data import SnappySnapshotData
from snappy.model.associated_folders import (
    delete_associated_folders,
    get_associated_folders_to_delete,
    get_installation_plan,
    install_confirmed_snapshot,
)
from snappy.model.catalogue import CatalogueModel
from snappy.model.dashboard import DashboardModel
from snappy.view.catalogue import DeleteAssociatedFoldersDialog, InstallSnapshotDialog, SnapshotCatalogueWidget, UpdateSnapshotDialog
from snappy.view.catalogue_imp_dialog import DialogConfig
from snappy.application.i18n import tr


class CatalogueController:
    """
    Controller for managing the snapshot catalogue view and its associated actions.

    This class bridges the user interface (SnapshotCatalogueWidget) and the underlying
    catalogue model, handling tasks such as creating, editing, installing, exporting,
    and deleting snapshots.
    """

    def __init__(self, dash_model: DashboardModel, search_page_opener=None):
        """
        Initializes the CatalogueController.

        Args:
            dash_model (DashboardModel): The dashboard model, required for tracking global state
                and launching heavy operations.
            search_page_opener (Callable, optional): A callback function used to navigate to the
                search page, optionally scoped to a specific snapshot.
        """
        self.dash_model = dash_model
        self.model = CatalogueModel()
        self.view = SnapshotCatalogueWidget(self.model)
        self.search_page_opener = search_page_opener

    def init(self):
        """
        Sets up signal-slot connections for the catalogue view.

        Connects UI interactions (buttons, context menus) to their respective handler methods.
        """
        self.view.signal_create_requested.connect(lambda: self.__open_config_dialog(False, None))
        self.view.signal_import_requested.connect(self.__import_zip)
        self.view.signal_open_catalogue_folder_requested.connect(self.__open_catalogue_directory)
        self.view.signal_install_requested.connect(self.__install_snapshot)
        self.view.signal_edit_requested.connect(self.__edit_snapshot)
        self.view.signal_delete_requested.connect(self.__delete_snapshot)
        self.view.signal_open_folder_requested.connect(self.__open_snap_directory)
        self.view.signal_duplicate_requested.connect(self.__duplicate_snapshot)
        self.view.signal_sort_requested.connect(self.view.sort)
        self.view.signal_search_internal_content_all.connect(self.__open_snapshot_searcher)
        self.view.signal_search_internal_content_single.connect(self.__open_snapshot_searcher_single)
        self.view.signal_export_request_snapshot.connect(self.__export_snapshot)
        self.view.signal_export_request_assoc_folders.connect(self.__export_snapshot_folders)
        self.view.signal_delete_installed_folders_requested.connect(self.__delete_snap_installed_dirs)
        self.view.signal_update_with_local_dirs_requested.connect(self.__update_assoc_dirs_from_installed)
        self.view.signal_open_assoc_folder_requested.connect(self.__open_directory)

    def update_data(self, snapshot_data: SnappySnapshotData):
        """
        Updates the catalogue view with new snapshot data.

        Args:
            snapshot_data (SnappySnapshotData): The new snapshot data to display.
        """
        self.model.set_snapshots(snapshot_data.snapshot_list, snapshot_data.home_statistics)
        self.model.table_model.update_headers()
        self.view.reload_data()

    @staticmethod
    def __log_automatic_backup(snap: Snapshot, backup_path: Path | None, operation: str):
        if backup_path is not None:
            log_action(
                ActionCategory.BACKUPS,
                ActionType.BACKUP_CREATED,
                f"snapshot={snap.name}; before={operation}; archive={backup_path.name}",
            )

    def __save_snapshot_changes(self, original: Snapshot, form: dict, message_callback) -> SnapshotUpdateResult:
        """Apply the edited fields after checking them against the form's original values."""
        catalogue = self.dash_model.snap_catalogue
        fields = {key: form[key] for key in ("name", "desc") if form[key] != getattr(original, key)}
        tags = form["tags"] if set(form["tags"]) != set(original.tags) else None
        custom = {
            key: value for key, value in form["custom_data"].items()
            if value != original.data.get(key, "")
        }
        directories = form["directories"] if form["directories_changed"] else None
        conflict = tr("This snapshot changed in another instance. Reopen it and try again.")

        with catalogue_access(catalogue.path_catalogue):
            current = catalogue.get_by_id(original.id)
            if current is None:
                raise ValueError(conflict)
            if any(getattr(current, key) not in (getattr(original, key), value) for key, value in fields.items()):
                raise ValueError(conflict)
            if tags is not None and set(current.tags) not in (set(original.tags), set(tags)):
                raise ValueError(conflict)
            if any(current.data.get(key) not in (original.data.get(key), value) for key, value in custom.items()):
                raise ValueError(conflict)
            if directories is not None:
                previous_paths = [(item.folder_id, item.original_path) for item in original.directories]
                current_paths = [(item.folder_id, item.original_path) for item in current.directories]
                if current_paths != previous_paths:
                    raise ValueError(conflict)

            return catalogue.update_snapshot_with_result(
                original.id, **fields, tags=tags, directory_paths=directories,
                data_updates=custom or None, message_callback=message_callback,
            )

    def __open_config_dialog(self, edit_mode: bool, snap: Snapshot | None = None):
        """
        Opens a dialog for creating or editing a snapshot configuration.

        Args:
            edit_mode (bool): True if editing an existing snapshot, False if creating a new one.
            snap (Snapshot | None): The snapshot to edit if edit_mode is True, otherwise None.
        """
        log_action(ActionCategory.CATALOGUE, ActionType.CATALOGUE_CONFIG_DIALOG_OPENED, "edit" if edit_mode else "create")
        dialog = DialogConfig(
            self.dash_model.cached_data, edit_mode, snap,
            catalogue_path=self.dash_model.snap_catalogue.path_catalogue,
        )
        try:
            if dialog.exec():
                raw_data = dialog.output_data
                if raw_data is None:
                    return
                if edit_mode:
                    if snap is None:
                        return
                    op_name = tr("Modify configuration")
                    op_desc = tr("Modifying configuration")
                    
                    def action(task):
                        result = self.__save_snapshot_changes(snap, raw_data, task.update_task_message)
                        self.__log_automatic_backup(snap, result.backup_path, "edit")
                        log_action(ActionCategory.CATALOGUE, ActionType.CATALOGUE_SNAPSHOT_UPDATED, result.snapshot.name)
                        
                    titolo = tr("Configuration modified")
                    testo = tr("The configuration has been modified successfully.")
                else:
                    op_name = tr("Create configuration")
                    op_desc = tr("Creating configuration")
                    
                    def action(task):
                        new = self.dash_model.snap_catalogue.create_snapshot(
                            snap_id=raw_data["id"],
                            name=raw_data["name"],
                            desc=raw_data["desc"],
                            author=get_system_username(),
                            tags=raw_data["tags"],
                            directory_paths=raw_data["directories"],
                            data=raw_data["custom_data"],
                            progress_callback=task.update_task_progress,
                            message_callback=task.update_task_message,
                        )
                        log_action(ActionCategory.CATALOGUE, ActionType.CATALOGUE_SNAPSHOT_CREATED, new.name)
                        
                    titolo = tr("Configuration created")
                    testo = tr("The configuration has been created successfully.")
                
                self.dash_model.run_heavy_operation(
                    op_name, op_desc, action, 
                    success_msg_title=titolo, success_msg=testo, update_dashboard=True
                )
        except Exception as e:
            logger.error(f"Error executing dialog: {e}")

    def __import_zip(self):
        """Import a snapshot or catalogue archive using the corresponding library workflow."""
        single = tr("Single snapshot")
        batch = tr("Whole catalogue")
        kind, accepted = QInputDialog.getItem(
            self.view, tr("Import ZIP"), tr("Choose the archive type"), [single, batch], 0, False
        )
        if not accepted:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self.view, tr("Select a ZIP archive"), str(app.path), tr("ZIP archives (*.zip)")
        )
        if not filename:
            return
        archive = Path(filename)
        catalogue = self.dash_model.snap_catalogue

        def action(task):
            task.update_task_message(archive.name)
            title = tr("Import complete")
            message = tr("Imported snapshots are available in the catalogue.")
            if kind == single:
                catalogue.import_snapshot(archive)
                count = 1
            elif import_with_report := getattr(catalogue, "import_catalogue_with_report", None):
                report = import_with_report(archive)
                count = len(report.imported)
                message = tr(
                    "Imported: {imported}. Already present: {skipped}. Failed: {failed}.",
                    imported=count, skipped=len(report.skipped), failed=len(report.failed),
                )
                if report.failed:
                    title = tr("Import incomplete")
                    first_entry, first_error = next(iter(report.failed.items()))
                    message += "\n\n" + tr("First failure in {entry}: {error}", entry=first_entry, error=first_error)
                    if len(report.failed) > 1:
                        message += "\n" + tr("See the log for the other failures.")
            else:
                # The published 1.0.4 API does not return individual outcomes.
                with catalogue_access(catalogue.path_catalogue):
                    existing = {snapshot.id for snapshot in catalogue.get_all()}
                    catalogue.import_catalogue(archive)
                    count = sum(snapshot.id not in existing for snapshot in catalogue.get_all())
                title = tr("Archive processed")
                message = tr("Imported {count} new snapshots. See the log for skipped entries and errors.", count=count)
            if count:
                log_action(ActionCategory.CATALOGUE, ActionType.CATALOGUE_SNAPSHOTS_IMPORTED, f"{archive.name} ({count})")
            return title, message

        self.dash_model.run_heavy_operation(
            tr("Import ZIP"),
            tr("Importing archive"),
            action,
            show_result_message=True,
            update_dashboard=True,
        )

    def __open_snapshot_searcher(self):
        """
        Opens the search view to look for content across all snapshots.
        """
        if self.search_page_opener:
            self.search_page_opener(None)

    def __open_snapshot_searcher_single(self, snapshot: Snapshot):
        """
        Opens the search view restricted to a specific snapshot.

        Args:
            snapshot (Snapshot): The snapshot to restrict the search context to.
        """
        if self.search_page_opener:
            self.search_page_opener(snapshot)

    def __install_snapshot(self, snap: Snapshot):
        """Confirm the persisted destinations and the current installation mode."""
        logger.debug(f"Installation requested for {snap.name}")
        try:
            catalogue = self.dash_model.snap_catalogue
            confirmed = get_installation_plan(catalogue, snap.id)
            dialog = InstallSnapshotDialog(confirmed.paths, confirmed.clear_destination, parent=self.view)
            if not dialog.exec():
                return

            def action(task):
                result = install_confirmed_snapshot(
                    catalogue,
                    confirmed,
                    progress_callback=task.update_task_progress,
                    message_callback=task.update_task_message,
                )
                logger.info(f"Configuration installation {snap.name} completed.")
                self.__log_automatic_backup(snap, result.backup_path, "install")
                log_action(ActionCategory.CATALOGUE, ActionType.CATALOGUE_SNAPSHOT_INSTALLED, snap.name)

            self.dash_model.run_heavy_operation(
                tr("Install configuration"),
                tr("Installing configuration"),
                action,
                success_msg_title=tr("Configuration installed"),
                success_msg=tr("The configuration has been installed successfully."),
                update_dashboard=True,
            )
        except Exception as error:
            UiUtils.show_message(tr("Installation error"), str(error), self.view)

    def __edit_snapshot(self, snap: Snapshot):
        """
        Initiates the process to edit an existing snapshot configuration.

        Args:
            snap (Snapshot): The snapshot to edit.
        """
        try:
            self.__open_config_dialog(True, snap)
        except Exception as e:
            UiUtils.show_message(tr("Edit error"), tr("An error occurred during editing: {error}", error=str(e)))

    def __delete_snapshot(self, snap: Snapshot):
        """
        Prompts the user to confirm, then deletes the specified snapshot.

        Args:
            snap (Snapshot): The snapshot to delete.
        """
        logger.debug(f"Deletion requested for {snap.name}")
        try:
            w = MessageBox(tr("Delete configuration"), tr("Are you sure you want to delete the selected configuration? This operation cannot be undone."), parent=self.view)
            if w.exec_():
                def action(task):
                    result = self.dash_model.snap_catalogue.delete_with_result(snap, message_callback=task.update_task_message)
                    logger.info(f"Configuration deletion {snap.name} completed.")
                    self.__log_automatic_backup(snap, result.backup_path, "delete")
                    log_action(ActionCategory.CATALOGUE, ActionType.CATALOGUE_SNAPSHOT_DELETED, snap.name)
                
                self.dash_model.run_heavy_operation(
                    tr("Delete configuration"),
                    tr("Deleting configuration"),
                    action,
                    success_msg_title=tr("Configuration deleted"),
                    success_msg=tr("The configuration has been deleted successfully."),
                    update_dashboard=True
                )
        except Exception as e:
            logger.error(f"Error during delete process: {e}")

    def __open_snap_directory(self, snap: Snapshot):
        """
        Opens the file system directory corresponding to a given snapshot.

        Args:
            snap (Snapshot): The snapshot whose directory will be opened.
        """
        try:
            path = self.dash_model.snap_catalogue.get_snap_directory_path(snap)
        except (OSError, SnapshotBusyError) as error:
            logger.warning("Cannot locate the snapshot folder: {}", error)
            UiUtils.show_message(tr("Warning"), str(error), self.view)
            return
        if path is None:
            UiUtils.show_message(tr("Warning"), tr("This snapshot is no longer in the catalogue."), self.view)
            self.dash_model.update()
            return
        self.__open_directory(path)

    def __duplicate_snapshot(self, snap: Snapshot):
        """
        Duplicates an existing snapshot as a new entry.

        Args:
            snap (Snapshot): The snapshot to duplicate.
        """
        logger.debug(f"Duplication requested for {snap.name}")
        try:
            def action(task):
                self.dash_model.snap_catalogue.duplicate_by_id(snap.id, message_callback=task.update_task_message)
                logger.info(f"Configuration duplication {snap.name} completed.")
                log_action(ActionCategory.CATALOGUE, ActionType.CATALOGUE_SNAPSHOT_DUPLICATED, snap.name)
            
            self.dash_model.run_heavy_operation(
                tr("Duplicate configuration"),
                tr("Duplicating configuration"),
                action,
                success_msg_title=tr("Configuration duplicated"),
                success_msg=tr("The configuration has been duplicated successfully."),
                update_dashboard=True
            )
        except Exception as e:
            logger.error(f"Error during duplicate process: {e}")

    def __execute_export(
            self,
            snap: Snapshot,
            file_dialog_text: str,
            export_method,
            action_type: ActionType,
            log_prefix: str,
            op_title: str,
            op_desc: str
    ):
        logger.debug(f"{log_prefix} requested for {snap.name}")
        try:
            directory = QFileDialog.getExistingDirectory(
                None,
                file_dialog_text,
                app.path.__str__()
            )
            if directory:
                def action(task):
                    export_method(snap.id, Path(directory), message_callback=task.update_task_message)
                    logger.info(f"{log_prefix} of {snap.name} to {directory} completed.")
                    log_action(ActionCategory.CATALOGUE, action_type, f"{snap.name} -> {directory}")

                self.dash_model.run_heavy_operation(
                    op_title,
                    op_desc,
                    action,
                    success_msg_title="", success_msg="", update_dashboard=False
                )
        except Exception as e:
            UiUtils.show_message(tr("Export error"), tr("An error occurred during export: {error}", error=str(e)))

    def __export_snapshot(self, snap: Snapshot):
        confirmation = MessageBox(
            tr("Export snapshot"),
            tr("Are you sure you want to export the selected snapshot?"),
            parent=self.view,
        )
        if not confirmation.exec_():
            return
        self.__execute_export(
            snap,
            file_dialog_text=tr("Select the save folder for the snapshot"),
            export_method=self.dash_model.snap_catalogue.export_snapshot,
            action_type=ActionType.CATALOGUE_SNAPSHOT_EXPORTED,
            log_prefix="Export",
            op_title=tr("Export snapshot"),
            op_desc=tr("Exporting snapshot")
        )

    def __export_snapshot_folders(self, snap: Snapshot):
        catalogue = self.dash_model.snap_catalogue
        sources = {
            tr("Captured copies in the snapshot"): catalogue.export_captured_assoc_dirs,
            tr("Current files in the local folders"): catalogue.export_assoc_dirs,
        }
        source, accepted = QInputDialog.getItem(
            self.view, tr("Export associated folders"), tr("Choose the source of the exported files"),
            list(sources), 0, False,
        )
        if not accepted:
            return
        self.__execute_export(
            snap,
            file_dialog_text=tr("Select the save folder for the associated folders"),
            export_method=sources[source],
            action_type=ActionType.CATALOGUE_ASSOCIATED_FOLDERS_EXPORTED,
            log_prefix=source,
            op_title=tr("Export associated folders"),
            op_desc=tr("Exporting folders")
        )

    def __delete_snap_installed_dirs(self, snap: Snapshot):
        """Confirm and remove the local folders at the selected snapshot's associated paths."""
        logger.debug(f"Installed folders deletion requested for {snap.name}")
        try:
            catalogue = self.dash_model.snap_catalogue
            catalogue_path = catalogue.path_catalogue
            paths = get_associated_folders_to_delete(catalogue, snap.id)
            if not paths:
                UiUtils.show_message(
                    tr("Delete installed folders"),
                    tr("No associated folders exist on this computer."),
                    self.view,
                )
                return

            confirmed_paths = frozenset(paths)
            dialog = DeleteAssociatedFoldersDialog(paths, parent=self.view)
            if dialog.exec():
                def action(task):
                    backup = delete_associated_folders(
                        catalogue,
                        snap.id,
                        expected_catalogue_path=catalogue_path,
                        expected_paths=confirmed_paths,
                        message_callback=task.update_task_message,
                    )
                    if backup is not None:
                        logger.info(f"Installed folders deletion for {snap.name} completed.")
                        self.__log_automatic_backup(snap, backup, "remove installed folders")
                        log_action(ActionCategory.CATALOGUE, ActionType.CATALOGUE_INSTALLED_FOLDERS_DELETED, snap.name)
                
                self.dash_model.run_heavy_operation(
                    tr("Delete installed folders"),
                    tr("Deleting folders"),
                    action,
                    success_msg_title="", success_msg="", update_dashboard=True
                )
        except Exception as e:
            UiUtils.show_message(tr("Deletion error"), tr("An error occurred during deletion: {error}", error=str(e)), self.view)

    def __update_assoc_dirs_from_installed(self, snap: Snapshot):
        """
        Updates the snapshot's internal directories with the contents currently installed on the system.

        Args:
            snap (Snapshot): The snapshot to update.
        """
        logger.debug(f"Associated folders update requested for {snap.name}")
        try:
            catalogue = self.dash_model.snap_catalogue
            plan = catalogue.get_sync_plan(snap.id)
            dialog = UpdateSnapshotDialog(plan.paths, plan.emptying_paths, parent=self.view)
            if dialog.exec():
                def action(task):
                    result = catalogue.sync_with_result(
                        snap.id, expected_plan=plan, message_callback=task.update_task_message,
                    )
                    logger.info(f"Associated folders update for {snap.name} completed.")
                    self.__log_automatic_backup(snap, result.backup_path, "update with local")
                    log_action(ActionCategory.CATALOGUE, ActionType.CATALOGUE_ASSOCIATED_FOLDERS_UPDATED, snap.name)
                
                self.dash_model.run_heavy_operation(
                    tr("Update associated folders"),
                    tr("Updating folders"),
                    action,
                    success_msg_title="", success_msg="", update_dashboard=True
                )
        except Exception as e:
            UiUtils.show_message(tr("Update error"), tr("An error occurred during update: {error}", error=str(e)))

    def __open_catalogue_directory(self):
        """
        Opens the main catalogue directory in the system's file explorer.
        """
        path = app_settings.get(AppSettings.catalogue_path)
        self.__open_directory(Path(path))

    def __open_directory(self, path: Path):
        """
        Opens the specified directory path in the system's file explorer.

        Args:
            path (Path): The directory path to open.
        """
        logger.debug(f"Opening directory {path}")
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            UiUtils.show_message(tr("Warning"), tr("The folder no longer exists in {path}", path=path.__str__()))
