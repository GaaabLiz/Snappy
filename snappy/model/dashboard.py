from collections.abc import Callable
from pathlib import Path

from loguru import logger
from pylizlib.core.os.snap import SnapshotCatalogue
from pylizlib.qt.handler.operation_core import Operation
from pylizlib.qt.handler.operation_domain import OperationInfo
from pylizlib.qt.handler.operation_runner import OperationRunner, RunnerStatistics
from PySide6.QtCore import QObject, Signal, Slot

from snappy.application.app import app_settings, AppSettings, snap_settings
from snappy.domain.data import SnappyData
from snappy.model.operation import CatalogueTask
from snappy.model.snappy_update import TaskGetMonitoredSoftware, TaskGetSnapshots
from snappy.application.i18n import tr


# noinspection PyMethodMayBeStatic
class DashboardModel(QObject):
    """
    Model responsible for handling data and logic for the application's dashboard.

    This class manages asynchronous operations, tracks dashboard statistics,
    and emits signals to update the UI when data changes or operations complete.
    """

    signal_on_update_started = Signal()
    signal_on_update_complete = Signal()
    signal_on_update_already_running = Signal()
    signal_on_update_progress = Signal(int)
    signal_on_update_text = Signal(str)
    signal_on_update_detail_text = Signal(str)
    signal_on_operation_update = Signal(object)
    _worker_operation_update = Signal(object)
    signal_on_updated_data_available = Signal(SnappyData)
    signal_on_catalogue_invalidated = Signal()
    signal_on_heavy_operation_success = Signal(str, str)
    signal_on_heavy_operation_error = Signal(str, str)

    def __init__(self):
        """
        Initializes the DashboardModel, setting up internal tasks, signals, and catalogue handlers.
        """
        super().__init__()
        self.cached_data: SnappyData | None = None
        self._catalogue_reload_pending = False
        catalogue_path = Path(app_settings.get(AppSettings.catalogue_path))
        if not catalogue_path.is_absolute():
            raise ValueError("An absolute catalogue path must be configured before opening the dashboard.")

        self.snap_catalogue = SnapshotCatalogue(
            path_catalogue=catalogue_path,
            settings=snap_settings
        )
        self.task_monitored_soft = TaskGetMonitoredSoftware()
        self.task_snap = TaskGetSnapshots(self.snap_catalogue)
        self._worker_operation_update.connect(self._forward_operation_update)
        self.task_snap.on_update = self._worker_operation_update.emit
        self._active_task: CatalogueTask | None = None
        self.operation_info = OperationInfo(
            name=tr("Dashboard Update"),
            description=tr("Dashboard data update"),
            delay_each_task=0.1
        )
        self.runner = OperationRunner(abort_all_on_error=True)
        self.operation_active = False
        self.runner.runner_start.connect(self.on_runner_started)
        self.runner.runner_stop.connect(self.on_runner_stopped)
        self.runner.runner_finish.connect(self.on_runner_finished)
        self._heavy_runners = []

    def run_heavy_operation(
        self,
        op_name: str,
        op_desc: str,
        func: Callable,
        success_msg_title: str = "",
        success_msg: str = "",
        update_dashboard: bool = True,
        error_msg_title: str = "",
        error_msg_template: str = "",
        *,
        show_result_message: bool = False,
        on_result: Callable | None = None,
    ):
        """
        Executes a potentially time-consuming heavy operation asynchronously.

        Args:
            op_name (str): The name of the operation.
            op_desc (str): A description of what the operation does.
            func (callable): The function to execute.
            success_msg_title (str, optional): The title of the success message to show when finished. Defaults to "".
            success_msg (str, optional): The detailed success message to show when finished. Defaults to "".
            update_dashboard (bool, optional): Whether to refresh the dashboard after the operation. Defaults to True.
            error_msg_title (str, optional): The title to use for a failed operation. Defaults to "Error".
            error_msg_template (str, optional): An optional translated error message with an {error} placeholder.
            show_result_message (bool): Use the task's returned (title, message) for completion feedback.
            on_result (Callable | None): Receive the result on the GUI thread after the worker is released.
        """
        if self.operation_active:
            self.signal_on_update_already_running.emit()
            return False
        if self._catalogue_reload_pending:
            self.signal_on_heavy_operation_error.emit(
                tr("Catalogue Error"),
                tr("Reload the new catalogue with F5 before starting operations."),
            )
            return False

        task = CatalogueTask(op_name, func, self._worker_operation_update.emit)
        op_info = OperationInfo(name=op_name, description=op_desc)
        op = Operation([task], op_info)

        runner = OperationRunner(abort_all_on_error=True)
        self._heavy_runners.append(runner)

        def on_finish(stats: RunnerStatistics):
            if runner in self._heavy_runners:
                self._heavy_runners.remove(runner)

            self._active_task = None
            cancelled = getattr(stats, "cancelled_operations", 0)
            failed = stats.has_ops_failed()
            if failed:
                error = stats.get_first_error()
                logger.error(f"Error during {op_name}: {error}")
                error_title = error_msg_title or tr("Error")
                error_message = (
                    error_msg_template.format(error=str(error))
                    if error_msg_template
                    else tr("An error occurred: {error}", error=str(error))
                )
                self.signal_on_heavy_operation_error.emit(error_title, error_message)
            elif not cancelled:
                if show_result_message and task.result is not None:
                    self.signal_on_heavy_operation_success.emit(*task.result)
                elif success_msg_title and success_msg:
                    self.signal_on_heavy_operation_success.emit(success_msg_title, success_msg)

            self.operation_active = False
            if update_dashboard and not cancelled:
                self.update()
            else:
                self.signal_on_update_complete.emit()
            if not (cancelled or failed) and on_result is not None:
                on_result(task.result)

        runner.runner_finish.connect(on_finish)
        self._active_task = task
        self.operation_active = True
        self.signal_on_update_started.emit()
        self.signal_on_update_text.emit(op_desc)
        self.signal_on_update_detail_text.emit("")
        self.signal_on_update_progress.emit(0)

        try:
            runner.add(op)
            runner.start()
            return True
        except Exception as e:
            if runner in self._heavy_runners:
                self._heavy_runners.remove(runner)
            logger.error(f"Error launching {op_name}: {e}")
            error_title = error_msg_title or tr("Error")
            error_message = (
                error_msg_template.format(error=str(e))
                if error_msg_template
                else tr("An error occurred: {error}", error=str(e))
            )
            self.signal_on_heavy_operation_error.emit(error_title, error_message)
            self._active_task = None
            self.operation_active = False
            self.signal_on_update_complete.emit()
            return False

    @Slot(object)
    def _forward_operation_update(self, update):
        """Deliver worker feedback on the GUI thread."""
        self.signal_on_operation_update.emit(update)

    def cancel_catalogue_wait(self):
        """Cancel the current worker if the library is still waiting for access."""
        if self._active_task is not None:
            self._active_task.request_cancellation()

    def get_cached_data(self) -> SnappyData | None:
        """
        Retrieves the most recently cached dashboard data.

        Returns:
            SnappyData | None: The cached data, or None if no data has been fetched yet.
        """
        return self.cached_data

    def invalidate_catalogue_data(self):
        """Discard the previous catalogue data before reading a newly selected path."""
        self.cached_data = None
        self._catalogue_reload_pending = True
        self.signal_on_catalogue_invalidated.emit()

    def update(self) -> bool:
        """
        Triggers an asynchronous update of the dashboard data by retrieving snapshots.

        Returns:
            bool: Whether a new dashboard update was started.
        """
        if self.operation_active:
            logger.info("Ignoring dashboard update request because an operation is already running.")
            self.signal_on_update_already_running.emit()
            return False

        self.operation_active = True
        try:
            # Executable monitoring remains implemented but is intentionally inactive.
            self.task_snap.prepare()
            self._active_task = self.task_snap
            tasks = [self.task_snap]
            self.runner.clear()
            op = Operation(tasks, self.operation_info)
            self.runner.add(op)
            self.runner.start()
            return True

        except Exception as e:
            self._active_task = None
            self.operation_active = False
            self.signal_on_update_complete.emit()
            logger.error(f"Error launching update: {e}")
            self.__report_update_error(e)
            return False

    def __report_update_error(self, error: object):
        """Notify the UI that the latest refresh failed and cached data may be stale."""
        self.signal_on_heavy_operation_error.emit(
            tr("Update error"),
            tr(
                "Dashboard refresh failed. The displayed data may be outdated. Error: {error}",
                error=str(error),
            ),
        )

    def on_runner_started(self):
        """
        Slot called when the main update runner starts execution. Emits relevant signals to UI.
        """
        logger.info("Dashboard update started.")
        self.signal_on_update_started.emit()
        self.signal_on_update_text.emit(tr("Updating dashboard data..."))
        self.signal_on_update_detail_text.emit("")
        self.signal_on_update_progress.emit(0)

    def on_runner_stopped(self):
        """
        Slot called when the main update runner stops execution prematurely.
        """
        logger.info("Dashboard update stopped.")
        # runner_stop is only a request; runner_finish confirms the tasks have exited.

    def on_runner_finished(self, stats: RunnerStatistics):
        """
        Slot called when the main update runner finishes execution. Analyzes results and updates cached data.

        Args:
            stats (RunnerStatistics): The statistics and results from the completed operation.
        """
        error_to_report: object | None = None
        try:
            logger.info("Dashboard update completed.")
            if stats.has_ops_failed():
                error_to_report = stats.get_first_error()
                logger.error(f"Error during dashboard update: {error_to_report}")
                return

            if getattr(stats, "cancelled_operations", 0):
                return

            logger.debug("Dashboard update successfully completed, fetching data...")
            op = stats.operations[0]
            snapshots = op.get_task_result_by_id(self.task_snap.id)
            data = SnappyData(
                snapshots=snapshots,
                monitored_software=[],
                home_statistics=self.task_snap.home_statistics,
                backup_count=self.task_snap.backup_count,
                backups=self.task_snap.backups,
            )
            self.cached_data = data
            self._catalogue_reload_pending = False
            self.signal_on_updated_data_available.emit(data)
        except Exception as error:
            error_to_report = error
            logger.error(f"Error processing dashboard update: {error}")
        finally:
            self._active_task = None
            self.operation_active = False
            self.signal_on_update_complete.emit()
            if error_to_report is not None:
                self.__report_update_error(error_to_report)
