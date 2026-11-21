import os

from qfluentwidgets import MessageBox
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from loguru import logger
from pylizlib.core.os.snap import SnapshotCatalogue, Snapshot

from snappy.model.history import log_action, ActionCategory, ActionType
from snappy.model.catalogue_searcher import CatalogueSearcherModel, SearchOutcome, SearchResultsTreeModel
from snappy.view.catalogue_searcher import CatalogueSearcherView, SnapshotResultsDialog
from snappy.application.i18n import tr

class CatalogueSearcherController:
    """
    Controller for the catalogue searcher component.

    This class connects the CatalogueSearcherView (the UI) with the
    CatalogueSearcherModel (the business logic and data). It handles user
    interactions from the view and invokes the corresponding actions in the model.
    """

    def __init__(self, catalogue: SnapshotCatalogue, parent=None, dash_model=None):
        """
        Initializes the CatalogueSearcherController.

        Args:
            catalogue (SnapshotCatalogue): The catalogue data source.
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        self.view = CatalogueSearcherView(parent)
        self.model = CatalogueSearcherModel(catalogue, dash_model)
        self._snapshots: list[Snapshot] = []
        self._selected_ids: set[str] | None = None

        # Connect view and model
        self.view.setModel(self.model.table_model)
        self.view.tree_view.setModel(self.model.tree_model_manager.model)

        # Connect signals
        self.model.signal_search_finished.connect(self._on_search_finished)
        self.view.action_start.triggered.connect(self._perform_search)
        self.view.action_stop.triggered.connect(self._stop_search)
        self.view.signal_delete_requested.connect(self._on_delete_requested)
        self.view.signal_file_double_clicked.connect(self._on_file_double_clicked)
        self.view.signal_tree_open_parent_folder.connect(self._on_tree_open_parent_folder)
        self.view.signal_snapshot_double_clicked.connect(self._on_snapshot_double_clicked)
        self.view.signal_snapshot_filter_changed.connect(self._on_snapshot_filter_changed)

        # Connect the status card update signal directly to the view's slot
        self.model.signal_status_card_update.connect(self.view.update_status_card)

    def _on_snapshot_filter_changed(self, snap_ids: list[str]):
        """Apply the dropdown selection to the cached catalogue."""
        if self.model.is_search_active:
            self.view.update_snapshot_menu(self._snapshots, self._selected_ids)
            return
        self._selected_ids = set(snap_ids) if snap_ids else None
        self._apply_scope()

    def _on_delete_requested(self, row: int):
        """
        Handles the request to delete a snapshot from the search table.

        Args:
            row (int): The row index of the snapshot to remove.
        """
        if self.model.is_search_active:
            return

        logger.debug(f"Removing row {row} from search results")
        self.model.remove_snapshot(row)
        self._selected_ids = {snapshot.id for snapshot in self.model.table_model.get_data()}
        self.view.update_snapshot_menu(self._snapshots, self._selected_ids)
        log_action(ActionCategory.SEARCH, ActionType.SEARCH_SNAPSHOT_REMOVED, f"row={row}")

    def _on_file_double_clicked(self, file_path: str):
        """
        Handles the double-click event on a file in the results tree.
        Attempts to open the file with the default system application.

        Args:
            file_path (str): The path to the file to open.
        """
        logger.info(f"Opening file in search results: {file_path}")
        if os.path.isfile(file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
        elif os.path.isdir(file_path):
            logger.warning(f"Cannot open directory in _on_file_double_clicked: {file_path}")

    def _on_tree_open_parent_folder(self, file_path: str):
        """
        Handles the context menu action to open the parent folder of a file.

        Args:
            file_path (str): The path to the file whose parent folder should be opened.
        """
        logger.info(f"Opening parent folder for file {file_path}")
        parent_dir = os.path.dirname(file_path)
        if os.path.exists(parent_dir):
            QDesktopServices.openUrl(QUrl.fromLocalFile(parent_dir))

    def _on_snapshot_double_clicked(self, row: int):
        """
        Handles the double-click event on the snapshot table.
        Opens a dialog with search results specifically for the clicked snapshot.
        """
        snapshot = self.model.table_model.get_data()[row]
        results = self.model.get_results_for_snapshot(snapshot.id)

        dialog = SnapshotResultsDialog(snapshot.name, self.view)
        
        tree_model_manager = SearchResultsTreeModel()
        tree_model_manager.populate_from_results([(snapshot, results)])
        
        dialog.tree_view.setModel(tree_model_manager.model)
        
        dialog.signal_file_double_clicked.connect(self._on_file_double_clicked)
        dialog.signal_tree_open_parent_folder.connect(self._on_tree_open_parent_folder)
        
        dialog.exec()

    def _perform_search(self):
        """
        Gathers search parameters from the view and triggers a search in the model.
        """
        if self.model.is_search_active:
            return

        search_text = self.view.search_bar.text()
        if not search_text.strip():
            m = MessageBox(
                tr("Missing text"),
                tr("Please enter a text before starting the search."),
                self.view
            )
            m.exec()
            return

        self.view.set_operation_status(True)
        query_type = self.view.get_selected_query_type()
        search_target = self.view.get_selected_search_target()
        extensions = self.view.get_selected_extensions()

        # Toggle button states
        self.view.action_start.setEnabled(False)
        self.view.action_stop.setEnabled(True)

        logger.info(f"Starting search: text='{search_text}', type={query_type}, target={search_target}")
        try:
            search_started = self.model.search(search_text, query_type, search_target, extensions)
        except Exception as error:
            logger.exception("Failed to start catalogue search")
            log_action(ActionCategory.SEARCH, ActionType.SEARCH_FAILED, str(error))
            self.view.set_operation_status(False)
            self.view.action_start.setEnabled(True)
            self.view.action_stop.setEnabled(False)
            MessageBox(
                tr("Search error"),
                tr("The search could not be started: {error}", error=str(error)),
                self.view
            ).exec()
            return

        if not search_started:
            self.view.set_operation_status(False)
            self.view.action_start.setEnabled(True)
            self.view.action_stop.setEnabled(False)
            return

        log_action(ActionCategory.SEARCH, ActionType.SEARCH_STARTED, f"query={search_text}")

    def _stop_search(self):
        """Stops the search operation in the model and updates the UI state."""
        logger.info("Search interrupted by user")
        self.model.stop_search()
        # Controls are restored by _on_search_finished once the worker has exited.
        self.view.action_stop.setEnabled(False)

    def _on_search_finished(self, outcome: SearchOutcome):
        """Restore controls and record how the search ended."""
        self.view.set_operation_status(False)
        self.view.action_start.setEnabled(True)
        self.view.action_stop.setEnabled(False)

        details = outcome.failures + outcome.limited
        if outcome.cancelled:
            log_action(ActionCategory.SEARCH, ActionType.SEARCH_STOPPED, "")
            return
        if not details:
            log_action(ActionCategory.SEARCH, ActionType.SEARCH_COMPLETED, "")
            return

        if outcome.failures:
            title = tr("Search completed with errors")
            action = ActionType.SEARCH_COMPLETED_WITH_ERRORS
        else:
            title = tr("Search results are incomplete")
            action = ActionType.SEARCH_PARTIAL
        log_action(ActionCategory.SEARCH, action, f"failed_snapshots={len(outcome.failures)}, limits_reached={len(outcome.limited)}")
        message = "\n\n".join(f"• {snapshot_name}\n{cause}" for snapshot_name, cause in details)
        MessageBox(title, message, self.view).exec()

    def update_snapshots(self, snapshots: list[Snapshot], *, reset_scope: bool = False):
        """Refresh available snapshots, resetting the filter when switching catalogues."""
        if reset_scope:
            self._selected_ids = None
        self._snapshots = snapshots
        self._apply_scope()

    def open(self, snapshot_or_snapshots: Snapshot | list[Snapshot] | None = None):
        """Open the search page with the explicitly requested scope."""
        if self.model.is_search_active:
            return
        if snapshot_or_snapshots is None:
            self._selected_ids = None
        else:
            snapshots = snapshot_or_snapshots if isinstance(snapshot_or_snapshots, list) else [snapshot_or_snapshots]
            self._selected_ids = {snapshot.id for snapshot in snapshots}
        self._apply_scope()

    def _apply_scope(self):
        visible = self._snapshots if self._selected_ids is None else [
            snapshot for snapshot in self._snapshots if snapshot.id in self._selected_ids
        ]
        if self.model.set_snapshots(visible):
            self.view.update_snapshot_menu(self._snapshots, self._selected_ids)
