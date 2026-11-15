from pathlib import Path

from loguru import logger
from pylizlib.core.os.snap import SnapshotCatalogue
from pylizlib.qt.handler.operation_core import Operation, GenericTask
from pylizlib.qt.handler.operation_domain import OperationInfo
from pylizlib.qt.handler.operation_runner import OperationRunner, RunnerStatistics
from PySide6.QtCore import QObject, Signal

from snappy.application.app import app_settings, AppSettings, snap_settings
from snappy.domain.data import SnappyData
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
    signal_on_updated_data_available = Signal(SnappyData)
    signal_on_heavy_operation_success = Signal(str, str)
    signal_on_heavy_operation_error = Signal(str, str)

    def __init__(self):
        """
        Initializes the DashboardModel, setting up internal tasks, signals, and catalogue handlers.
        """
        super().__init__()
        self.cached_data: SnappyData | None = None
        self.snap_catalogue = SnapshotCatalogue(
            path_catalogue=Path(app_settings.get(AppSettings.catalogue_path)),
            settings=snap_settings
        )
        self.task_monitored_soft = TaskGetMonitoredSoftware()
        self.task_snap = TaskGetSnapshots(self.snap_catalogue)
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
        self.runner.runner_update_progress.connect(self.signal_on_update_progress.emit)

        self.runner.task_update_message.connect(lambda task_name, msg: self.signal_on_update_detail_text.emit(msg))

        self._heavy_runners = []

    def run_heavy_operation(
        self,
        op_name: str,
        op_desc: str,
        func: callable,
        success_msg_title: str = "",
        success_msg: str = "",
        update_dashboard: bool = True,
        error_msg_title: str = "",
        error_msg_template: str = "",
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
        """
        if self.operation_active:
            self.signal_on_update_already_running.emit()
            return False

        task = GenericTask(op_name, func)
        op_info = OperationInfo(name=op_name, description=op_desc)
        op = Operation([task], op_info)

        runner = OperationRunner(abort_all_on_error=True)
        self._heavy_runners.append(runner)

        def on_finish(stats: RunnerStatistics):
            if runner in self._heavy_runners:
                self._heavy_runners.remove(runner)

            if stats.has_ops_failed():
                error = stats.get_first_error()
                logger.error(f"Error during {op_name}: {error}")
                error_title = error_msg_title or tr("Error")
                error_message = (
                    error_msg_template.format(error=str(error))
                    if error_msg_template
                    else tr("An error occurred: {error}", error=str(error))
                )
                self.signal_on_heavy_operation_error.emit(error_title, error_message)
                if update_dashboard:
                    self.operation_active = False
                    self.update()
                else:
                    self.operation_active = False
                    self.signal_on_update_complete.emit()
            else:
                if success_msg_title and success_msg:
                    self.signal_on_heavy_operation_success.emit(success_msg_title, success_msg)
                if update_dashboard:
                    # No signals or UI unlock between the operation and its refresh.
                    self.operation_active = False
                    self.update()
                else:
                    self.operation_active = False
                    self.signal_on_update_complete.emit()

        runner.runner_finish.connect(on_finish)
        runner.runner_update_progress.connect(self.signal_on_update_progress.emit)
        runner.task_update_message.connect(lambda task_name, msg: self.signal_on_update_detail_text.emit(msg))

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
            self.operation_active = False
            self.signal_on_update_complete.emit()
            return False


    def get_cached_data(self) -> SnappyData | None:
        """
        Retrieves the most recently cached dashboard data.

        Returns:
            SnappyData | None: The cached data, or None if no data has been fetched yet.
        """
        return self.cached_data

    def update(self) -> bool:
        """
        Triggers an asynchronous update of the dashboard data by retrieving snapshots and monitored software.

        Returns:
            bool: Whether a new dashboard update was started.
        """
        if self.operation_active:
            logger.info("Ignoring dashboard update request because an operation is already running.")
            self.signal_on_update_already_running.emit()
            return False

        self.operation_active = True
        try:
            tasks = [
                self.task_monitored_soft,
                self.task_snap,
            ]
            self.runner.clear()
            op = Operation(tasks, self.operation_info)
            self.runner.add(op)
            self.runner.start()
            return True

        except Exception as e:
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
                monitored_software=op.get_task_result_by_id(self.task_monitored_soft.id),
            )
            data.home_statistics = getattr(self.task_snap, "home_statistics", None)
            self.signal_on_updated_data_available.emit(data)
            self.cached_data = data
        except Exception as error:
            error_to_report = error
            logger.error(f"Error processing dashboard update: {error}")
        finally:
            self.operation_active = False
            self.signal_on_update_complete.emit()
            if error_to_report is not None:
                self.__report_update_error(error_to_report)
