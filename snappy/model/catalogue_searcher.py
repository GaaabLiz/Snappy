from collections import Counter
from dataclasses import dataclass, field


from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, Signal, QObject
from PySide6.QtGui import QStandardItemModel, QStandardItem

from loguru import logger
from pylizlib.core.os.snap import (
    QueryType,
    SearchTarget,
    Snapshot,
    SnapshotCatalogue,
    SnapshotOperationCancelled,
    SnapshotOperationUpdate,
    SnapshotSearcher,
    SnapshotSearchParams,
    SnapshotSearchReport,
    SnapshotSearchResult,
    run_snapshot_operation,
)
from pylizlib.qt.handler.operation_core import Operation, Task
from pylizlib.qt.handler.operation_domain import OperationInfo, OperationStatus
from pylizlib.qt.handler.operation_runner import OperationRunner, RunnerStatistics

from snappy.application.app import AppSettings, app_settings
from snappy.application.i18n import tr
from snappy.model.operation import operation_status


RESULT_FILE_PATH_ROLE = Qt.ItemDataRole.UserRole + 1


class InvalidRegexError(ValueError):
    """The regex query could not be compiled."""


@dataclass
class SearchOutcome:
    cancelled: bool = False
    failures: list[tuple[str, str]] = field(default_factory=list)
    limited: list[tuple[str, str]] = field(default_factory=list)


class SearchResultsTableModel(QAbstractTableModel):
    """
    A table model for displaying snapshots being searched.

    This model manages the data for a table view that shows a list of snapshots,
    their search status, the number of results found, and the progress of the
    search operation for each.
    """

    def __init__(self, parent=None):
        """
        Initializes the SearchResultsTableModel.

        Args:
            parent (QObject, optional): The parent object. Defaults to None.
        """
        super().__init__(parent)
        self._headers = [tr("Snapshot name"), tr("Status"), tr("Values found"), tr("Progress"), "ETA"]
        self._data: list[Snapshot] = []
        self._progress_data = {}
        self._status_data = {}
        self._results_count_data = {}

    def rowCount(self, parent=QModelIndex()):
        """Returns the number of rows in the model."""
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        """Returns the number of columns in the model."""
        return len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """
        Returns the data for a given index and role.

        Args:
            index (QModelIndex): The index to retrieve data for.
            role (Qt.ItemDataRole): The role for which to retrieve data.

        Returns:
            Any: The data for the specified index and role.
        """
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None

        snapshot = self._data[index.row()]
        col = index.column()

        if col == 0:
            return snapshot.name
        elif col == 1:
            return self._status_data.get(snapshot.id, tr("Pending"))
        elif col == 2:
            return self._results_count_data.get(snapshot.id, "")
        elif col == 3:
            progress = self._progress_data.get(snapshot.id, 0)
            return f"{progress}%"
        elif col == 4:
            return "--"  # ETA
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """Returns the header data for a given section, orientation, and role."""
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return None

    def update_data(self, new_data: list[Snapshot]):
        """
        Updates the model's data with a new list of snapshots and notifies the view.
        
        Args:
            new_data (list[Snapshot]): The new list of snapshots to display.
        """
        self.beginResetModel()
        self._data = list(new_data)
        self._progress_data.clear()
        self._status_data.clear()
        self._results_count_data.clear()
        self.endResetModel()

    def remove_snapshot(self, row: int):
        """
        Removes a snapshot from the model at the given row.

        Args:
            row (int): The row index of the snapshot to remove.
        """
        if 0 <= row < self.rowCount():
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._data[row]
            self.endRemoveRows()

    def reset_search_state(self):
        """Resets the progress, status, and results data for all rows."""
        if not self._data:
            return
        self._progress_data.clear()
        self._status_data.clear()
        self._results_count_data.clear()
        # Emit dataChanged for all rows and the relevant columns (status, progress, results)
        top_left = self.index(0, 1)
        bottom_right = self.index(self.rowCount() - 1, 3)
        self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])

    def get_data(self) -> list[Snapshot]:
        """
        Returns the list of all snapshots currently in the model.

        Returns:
            list[Snapshot]: The list of snapshots.
        """
        return self._data

    def _emit_data_changed(self, snap_id: str, column: int):
        """
        Helper method to emit dataChanged for a specific snapshot and column.
        """
        for i, snapshot in enumerate(self._data):
            if snapshot.id == snap_id:
                index = self.index(i, column)
                self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
                return

    def update_progress_for_snapshot(self, snap_id: str, progress: int):
        """
        Finds a snapshot by its ID and updates its progress percentage.

        Args:
            snap_id (str): The ID of the snapshot to update.
            progress (int): The new progress value (0-100).
        """
        self._progress_data[snap_id] = progress
        self._emit_data_changed(snap_id, 3)

    def update_status_for_snapshot(self, snap_id: str, status: str):
        """
        Finds a snapshot by its ID and updates its status message.

        Args:
            snap_id (str): The ID of the snapshot to update.
            status (str): The new status string.
        """
        self._status_data[snap_id] = status
        self._emit_data_changed(snap_id, 1)

    def update_results_for_snapshot(self, snap_id: str, count: str):
        """
        Finds a snapshot by its ID and updates its results count.

        Args:
            snap_id (str): The ID of the snapshot to update.
            count (str): The new results count as a string.
        """
        self._results_count_data[snap_id] = count
        self._emit_data_changed(snap_id, 2)


class SnapSearchTask(Task):
    """A background task for searching within a single snapshot."""

    def __init__(self, params: SnapshotSearchParams, snapshot: Snapshot, catalogue: SnapshotCatalogue):
        """
        Initializes the SnapSearchTask.

        Args:
            params (SnapshotSearchParams): The parameters for the search.
            snapshot (Snapshot): The snapshot to search within.
            catalogue (SnapshotCatalogue): The catalogue manager instance.
        """
        super().__init__(f"Search in {snapshot.name}")
        self.params = params
        self.snapshot = snapshot
        self.searcher = SnapshotSearcher(catalogue)

    def execute(self) -> SnapshotSearchReport:
        """
        Executes the search task.

        Connects a progress callback and runs the search using SnapshotSearcher.

        Returns:
            SnapshotSearchReport: Results and whether the search exceeded limits or was cancelled.
        """
        def on_progress(_file_name: str, _total_files: int, _current_file: int) -> bool:
            return not self.is_cancelled

        def on_update(update: SnapshotOperationUpdate):
            message = operation_status(update)
            if update.detail:
                message = f"{message} {update.detail}"
            self.task_update_message.emit(self.name, message)
            if update.progress is not None:
                self.update_task_progress(update.progress)

        try:
            return run_snapshot_operation(
                lambda: self.searcher.search_with_report(self.snapshot, self.params, on_progress=on_progress),
                on_update=on_update,
                is_cancelled=lambda: self.is_cancelled,
            )
        except SnapshotOperationCancelled:
            self.cancel()
            return SnapshotSearchReport([], cancelled=True)


class SearchResultsTreeModel:
    """Manages the data model for the search results tree view."""

    def __init__(self):
        """Initializes the SearchResultsTreeModel."""
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels([tr('Results')])

    def clear(self):
        """Clears the tree model and resets the header."""
        self.model.clear()
        self.model.setHorizontalHeaderLabels([tr('Results')])

    def populate_from_results(self, groups: list[tuple[Snapshot, list[SnapshotSearchResult]]]):
        """Show each snapshot's matches by file and line, keeping snapshot identities distinct."""
        self.clear()
        count = sum(len(results) for _, results in groups)
        self.model.setHorizontalHeaderLabels([tr("Results ({count})", count=count)])
        names = Counter(snapshot.name for snapshot, results in groups if results)

        for snapshot, results in groups:
            if not results:
                continue
            name = snapshot.name if names[snapshot.name] == 1 else f"{snapshot.name} [{snapshot.id}]"
            snapshot_item = QStandardItem(f"{name} ({len(results)})")
            snapshot_item.setEditable(False)

            files = {}
            for result in results:
                path = str(result.file_path)
                file_item = files.get(path)
                if file_item is None:
                    file_item = QStandardItem(path)
                    file_item.setEditable(False)
                    file_item.setData(path, RESULT_FILE_PATH_ROLE)
                    files[path] = file_item
                    snapshot_item.appendRow(file_item)

                if result.line_number is not None:
                    text = tr("Line {number} — {preview}", number=result.line_number, preview=result.line_content or "")
                    line_item = QStandardItem(text)
                    line_item.setEditable(False)
                    line_item.setData(path, RESULT_FILE_PATH_ROLE)
                    file_item.appendRow(line_item)
            self.model.appendRow(snapshot_item)


class CatalogueSearcherModel(QObject):
    """
    The model for the catalogue searcher component.

    This class orchestrates the search process. It holds the data models for the
    views, manages the background search operations using an OperationRunner,
    and communicates state changes back to the UI via signals.

    Signals:
        signal_search_started: Emitted when the search runner starts.
        signal_search_stopped: Emitted when the search runner is stopped.
        signal_search_finished: Emitted when the search runner completes all operations.
        signal_status_card_update(str, int, str): Emitted to update the main status card
                                                   with a message, progress, and ETA.
    """
    signal_search_started = Signal()
    signal_search_stopped = Signal()
    signal_search_finished = Signal(object)
    signal_status_card_update = Signal(str, int, str)

    def __init__(self, catalogue: SnapshotCatalogue, dash_model=None):
        """
        Initializes the CatalogueSearcherModel.

        Args:
            catalogue (SnapshotCatalogue): The catalogue to be searched.
        """
        super().__init__()
        self.catalogue = catalogue
        self.dash_model = dash_model
        self.table_model = SearchResultsTableModel()
        self.tree_model_manager = SearchResultsTreeModel()
        self.runner = OperationRunner()

        self._current_message = tr("Waiting...")
        self._current_progress = 0
        self._current_eta = "--:--"
        self._search_active = False

        self.runner.runner_start.connect(self.signal_search_started)
        self.runner.runner_stop.connect(self.signal_search_stopped)
        self.runner.runner_finish.connect(self.on_runner_finished)
        self.runner.op_finished.connect(self.on_operation_finished)
        self.runner.op_update_status.connect(self.on_operation_status_changed)
        self.runner.op_update_progress.connect(self.on_operation_progress_changed)
        self.runner.task_start.connect(self.on_task_start)
        self.runner.task_update_message.connect(self.on_task_update_message)
        self.runner.runner_update_progress.connect(self.on_runner_progress)
        self.runner.op_eta_update.connect(self.on_eta_update)

        self._op_id_to_snap_id = {}

    @property
    def is_search_active(self) -> bool:
        """Whether a search is currently using the loaded snapshot scope."""
        return self._search_active

    def __get_runner_operations(self, params: SnapshotSearchParams) -> list[Operation]:
        """
        Creates a list of search operations for the runner.

        Args:
            params (SnapshotSearchParams): The search parameters to use for each operation.

        Returns:
            list[Operation]: A list of configured search operations.
        """
        ops = []
        self._op_id_to_snap_id.clear()
        for snap in self.table_model.get_data():
            current_task = SnapSearchTask(params=params, snapshot=snap, catalogue=self.catalogue)
            op = Operation([current_task], OperationInfo(delay_each_task=0.0, name=f"Search in {snap.name})",
                                                 description="Searching snapshot contents"))
            self._op_id_to_snap_id[op.id] = snap.id
            ops.append(op)
        return ops

    def set_snapshots(self, snapshots: list[Snapshot]) -> bool:
        """Apply the selected snapshots to the search table."""
        if self._search_active:
            logger.info("Ignoring snapshot scope change while search is running.")
            return False

        self.runner.clear()
        self._op_id_to_snap_id.clear()
        self.tree_model_manager.clear()
        self.table_model.update_data(snapshots)
        self._current_message = tr("Waiting...")
        self._current_progress = 0
        self._current_eta = "--:--"
        self._emit_status_card_update()
        return True

    def search(self, text: str, query_type: QueryType, search_target: SearchTarget, extensions: list[str]) -> bool:
        """
        Starts a new search operation.

        Resets the current state, creates search parameters and operations,
        and starts the operation runner.

        Args:
            text (str): The text or regex pattern to search for.
            query_type (QueryType): The type of query (TEXT or REGEX).
            search_target (SearchTarget): The target of the search (FILE_NAME or FILE_CONTENT).
            extensions (list[str]): A list of file extensions to filter by.

        Returns:
            bool: Whether a new search was started.
        """
        if self._search_active:
            logger.info("Ignoring search request because a search is already running.")
            return False

        if self.dash_model and self.dash_model.operation_active:
            return False

        params = SnapshotSearchParams(
            query=text,
            query_type=query_type,
            search_target=search_target,
            extensions=extensions,
            max_results=app_settings.get(AppSettings.search_max_results),
            regex_timeout_seconds=app_settings.get(AppSettings.search_regex_timeout),
        )
        try:
            SnapshotSearcher.validate_query(params)
        except ValueError as error:
            raise InvalidRegexError(str(error)) from error

        self.table_model.reset_search_state()
        self.tree_model_manager.clear()
        self._current_message = tr("Starting...")
        self._current_progress = 0
        self._current_eta = "--:--"
        self._emit_status_card_update()

        try:
            operations = self.__get_runner_operations(params)
            if not operations:
                logger.info("No snapshots are available for search.")
                self._current_message = tr("Waiting...")
                self._emit_status_card_update()
                return False

            self._search_active = True
            if self.dash_model:
                self.dash_model.operation_active = True
            self.runner.clear()
            self.runner.adds(operations)
            logger.debug("Starting search operations in model")
            self.runner.start()
            return True
        except Exception:
            self._search_active = False
            if self.dash_model:
                self.dash_model.operation_active = False
            self._current_message = tr("Waiting...")
            self._current_progress = 0
            self._current_eta = "--:--"
            self._emit_status_card_update()
            raise

    def stop_search(self):
        """Stops the ongoing search operation."""
        logger.debug("Stopping search operations in model")
        self.runner.stop()
        # Keep the flag set until runner_finish confirms all tasks have exited.

    def on_operation_status_changed(self, op_id: str, status: OperationStatus):
        """
        Slot to handle status changes for an operation. Updates the table view.

        Args:
            op_id (str): The ID of the operation that changed status.
            status (OperationStatus): The new status.
        """
        if op_id in self._op_id_to_snap_id:
            snap_id = self._op_id_to_snap_id[op_id]
            self.table_model.update_status_for_snapshot(snap_id, status.value)

    def on_operation_progress_changed(self, op_id: str, progress: int):
        """
        Slot to handle progress changes for an operation. Updates the table view.

        Args:
            op_id (str): The ID of the operation.
            progress (int): The new progress value (0-100).
        """
        if op_id in self._op_id_to_snap_id:
            snap_id = self._op_id_to_snap_id[op_id]
            self.table_model.update_progress_for_snapshot(snap_id, progress)

    def _emit_status_card_update(self):
        """Helper to emit the signal_status_card_update signal."""
        self.signal_status_card_update.emit(self._current_message, self._current_progress, self._current_eta)

    def on_task_start(self, task_name: str):
        """
        Slot to handle the start of a task. Updates the main status card.

        Args:
            task_name (str): The name of the task that started.
        """
        self._current_message = tr("Searching...")
        self._current_eta = "--:--"
        self._emit_status_card_update()

    def on_task_update_message(self, task_name: str, message: str):
        """
        Slot to handle a message update from a task. Updates the main status card.

        Args:
            task_name (str): The name of the task.
            message (str): The new message.
        """
        self._current_message = message
        self._emit_status_card_update()

    def on_runner_progress(self, progress: int):
        """
        Slot to handle overall progress updates from the runner.

        Args:
            progress (int): The overall progress percentage.
        """
        self._current_progress = progress
        self._emit_status_card_update()

    def on_eta_update(self, op_id: str, eta: str):
        """
        Slot to handle ETA updates from an operation. Updates the main status card.

        Args:
            op_id (str): The ID of the operation.
            eta (str): The new estimated time remaining string.
        """
        self._current_eta = eta
        self._emit_status_card_update()

    @staticmethod
    def _get_operation_report(op: Operation) -> SnapshotSearchReport:
        """Read the single search task's report when the task returned one."""
        task_results = op.get_task_results()
        if task_results and isinstance(task_results[0], SnapshotSearchReport):
            return task_results[0]
        return SnapshotSearchReport([])

    def on_runner_finished(self, statistics: RunnerStatistics):
        """Present the completed tasks' results and report incomplete outcomes."""
        outcome = SearchOutcome(cancelled=statistics.cancelled_operations > 0)
        snapshots = {snapshot.id: snapshot for snapshot in self.table_model.get_data()}
        groups = []
        try:
            for op in statistics.operations:
                snapshot_id = self._op_id_to_snap_id.get(op.id)
                snapshot = snapshots.get(snapshot_id)
                snapshot_name = snapshot.name if snapshot is not None else snapshot_id or tr("Unknown snapshot")
                report = self._get_operation_report(op)
                if snapshot is not None and report.results:
                    groups.append((snapshot, report.results))
                outcome.cancelled |= report.cancelled

                if op.is_failed():
                    cause = str(op.error).strip() if op.error else tr("No error details available.")
                    outcome.failures.append((snapshot_name, cause))
                if report.result_limit_exceeded:
                    outcome.limited.append((snapshot_name, tr("More matches were found than can be displayed.")))
                if report.file_limit_exceeded:
                    outcome.limited.append((snapshot_name, tr("The file limit was reached. Some files were skipped.")))

            self.tree_model_manager.populate_from_results(groups)
        except Exception as error:
            logger.exception("Failed to assemble search results.")
            cause = str(error).strip() or tr("No error details available.")
            outcome.failures.append((tr("Unknown snapshot"), cause))
        finally:
            self._search_active = False
            if self.dash_model:
                self.dash_model.operation_active = False
            if outcome.cancelled:
                self._current_message = tr("Search cancelled")
            elif outcome.failures:
                self._current_message = tr("Search completed with errors")
            elif outcome.limited:
                self._current_message = tr("Search results are incomplete")
            self._current_eta = "--:--"
            self._emit_status_card_update()
            self.signal_search_finished.emit(outcome)

    def remove_snapshot(self, row: int):
        """Remove the selected row and its matches from the search views."""
        self.table_model.remove_snapshot(row)
        snapshots = {snapshot.id: snapshot for snapshot in self.table_model.get_data()}
        groups = []
        for operation in self.runner._all_operations:
            snapshot = snapshots.get(self._op_id_to_snap_id.get(operation.id))
            if snapshot is not None:
                groups.append((snapshot, self._get_operation_report(operation).results))
        self.tree_model_manager.populate_from_results(groups)

    def get_results_for_snapshot(self, snap_id: str) -> list[SnapshotSearchResult]:
        """
        Retrieves the search results for a specific snapshot.
        """
        results = []
        for op in self.runner._all_operations:
            if self._op_id_to_snap_id.get(op.id) == snap_id:
                results.extend(self._get_operation_report(op).results)
                break
        return results

    def on_operation_finished(self, op: Operation):
        """
        Slot to handle the completion of a single search operation.

        Updates the results count for the corresponding snapshot in the table.

        Args:
            op (Operation): The operation that finished.
        """
        if op.id not in self._op_id_to_snap_id:
            return

        snap_id = self._op_id_to_snap_id[op.id]
        count_str = ""
        if op.is_completed():
            op_results = self._get_operation_report(op).results
            count_str = str(len(op_results))
        elif op.is_failed():
            count_str = "?"

        self.table_model.update_results_for_snapshot(snap_id, count_str)
