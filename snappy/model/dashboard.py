from collections.abc import Callable
from pathlib import Path

from loguru import logger
from pylizlib.core.os.snap import SnapshotCatalogue
from pylizlib.qt.handler.operation_core import GenericTask, Operation
from pylizlib.qt.handler.operation_domain import OperationInfo
from pylizlib.qt.handler.operation_runner import OperationRunner, RunnerStatistics
from PySide6.QtCore import QObject, Signal

from snappy.application.app import AppSettings, app_settings, snap_settings
from snappy.application.i18n import tr
from snappy.domain.data import SnappyData
from snappy.model.operation import OperationLease, OperationState
from snappy.model.snappy_update import TaskGetMonitoredSoftware, TaskGetSnapshots


class DashboardModel(QObject):
    """Owns the catalogue and the shared admission gate for all critical work."""

    signal_on_update_started = Signal()
    signal_on_update_complete = Signal()
    signal_on_update_already_running = Signal()
    signal_on_operation_active_changed = Signal(bool)
    signal_on_update_progress = Signal(int)
    signal_on_update_text = Signal(str)
    signal_on_update_detail_text = Signal(str)
    signal_on_updated_data_available = Signal(SnappyData)
    signal_on_heavy_operation_success = Signal(str, str)
    signal_on_heavy_operation_error = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.operations = OperationState()
        self.operations.active_changed.connect(self._on_active_changed)
        self.operations.rejected.connect(self.signal_on_update_already_running.emit)
        self.cached_data: SnappyData | None = None
        self.snap_catalogue = SnapshotCatalogue(
            path_catalogue=Path(app_settings.get(AppSettings.catalogue_path)),
            settings=snap_settings,
        )
        self.task_monitored_soft = TaskGetMonitoredSoftware()
        self.task_snap = TaskGetSnapshots(self.snap_catalogue)
        self.operation_info = OperationInfo(
            name=tr("Dashboard Update"),
            description=tr("Dashboard data update"),
            delay_each_task=0.1,
        )
        self.runner = OperationRunner(abort_all_on_error=True)
        self._update_lease: OperationLease | None = None
        self._heavy_runners = []
        self.runner.runner_start.connect(self.on_runner_started)
        self.runner.runner_stop.connect(self.on_runner_stopped)
        self.runner.runner_finish.connect(self.on_runner_finished)
        self._connect_progress(self.runner)

    @property
    def operation_active(self) -> bool:
        """True until all critical work, including any follow-up refresh, ends."""
        return self.operations.operation_active

    def _on_active_changed(self, active: bool):
        self.signal_on_operation_active_changed.emit(active)
        if not active and not self.operation_active:
            self.signal_on_update_complete.emit()

    def _connect_progress(self, runner):
        runner.runner_update_progress.connect(self.signal_on_update_progress.emit)
        runner.task_update_message.connect(
            lambda task_name, msg: self.signal_on_update_detail_text.emit(msg)
        )

    def _report_error(self, error):
        logger.error(f"Critical operation failed: {error}")
        self.signal_on_heavy_operation_error.emit(
            tr("Error"), tr("An error occurred: {error}", error=str(error))
        )

    def run_heavy_operation(
        self,
        op_name: str,
        op_desc: str,
        func: Callable,
        success_msg_title: str = "",
        success_msg: str = "",
        update_dashboard: bool = True,
        on_success: Callable[[object], None] | None = None,
    ) -> bool:
        """Start exclusive background work; retain ownership through its refresh.

        on_success receives the task result on the UI thread with ownership held.
        """
        lease = self.operations.try_acquire(self)
        if lease is None:
            return False
        runner = None
        try:
            task = GenericTask(op_name, func)
            op = Operation([task], OperationInfo(name=op_name, description=op_desc))
            runner = OperationRunner(abort_all_on_error=True)
            self._heavy_runners.append(runner)

            def on_finish(stats: RunnerStatistics):
                if runner not in self._heavy_runners:
                    return
                self._heavy_runners.remove(runner)
                refreshing = False
                try:
                    if stats.has_ops_failed():
                        self._report_error(stats.get_first_error())
                        return
                    if getattr(stats, "cancelled_operations", 0):
                        return
                    if on_success:
                        on_success(task.result)
                    if success_msg_title and success_msg:
                        self.signal_on_heavy_operation_success.emit(success_msg_title, success_msg)
                    if update_dashboard:
                        refreshing = self._start_update(lease)
                except Exception as error:
                    self._report_error(error)
                finally:
                    if not refreshing:
                        lease.release()

            runner.runner_finish.connect(on_finish)
            self._connect_progress(runner)
            runner.add(op)
            self.signal_on_update_started.emit()
            self.signal_on_update_text.emit(op_desc)
            self.signal_on_update_detail_text.emit("")
            self.signal_on_update_progress.emit(0)
            runner.start()
            return True
        except Exception as error:
            if runner in self._heavy_runners:
                self._heavy_runners.remove(runner)
            try:
                self._report_error(error)
            finally:
                lease.release()
            return False

    def get_cached_data(self) -> SnappyData | None:
        return self.cached_data

    def update(self, *, before_update: Callable | None = None) -> bool:
        """Acquire ownership before preparing data or changing the catalogue path."""
        lease = self.operations.try_acquire(self)
        if lease is None:
            return False
        try:
            if before_update:
                before_update()
            return self._start_update(lease)
        except Exception as error:
            try:
                self._report_error(error)
            finally:
                lease.release()
            return False

    def _start_update(self, lease: OperationLease) -> bool:
        """Continue an admitted operation without releasing its lease."""
        self._update_lease = lease
        try:
            self.runner.clear()
            self.runner.add(
                Operation([self.task_monitored_soft, self.task_snap], self.operation_info)
            )
            self.runner.start()
            return True
        except Exception as error:
            self._update_lease = None
            try:
                self._report_error(error)
            finally:
                lease.release()
            return False

    def on_runner_started(self):
        logger.info("Dashboard update started.")
        self.signal_on_update_started.emit()
        self.signal_on_update_text.emit(tr("Updating dashboard data..."))
        self.signal_on_update_detail_text.emit("")
        self.signal_on_update_progress.emit(0)

    def on_runner_stopped(self):
        # runner_stop acknowledges cancellation; running tasks may still use disk.
        logger.info("Dashboard update stopped.")

    def on_runner_finished(self, stats: RunnerStatistics):
        lease, self._update_lease = self._update_lease, None
        logger.info("Dashboard update completed.")
        try:
            if stats.has_ops_failed():
                self._report_error(stats.get_first_error())
                return
            if getattr(stats, "cancelled_operations", 0):
                return
            op = stats.operations[0]
            data = SnappyData(
                snapshots=op.get_task_result_by_id(self.task_snap.id),
                monitored_software=op.get_task_result_by_id(self.task_monitored_soft.id),
            )
            data.home_statistics = getattr(self.task_snap, "home_statistics", None)
            self.cached_data = data
            self.signal_on_updated_data_available.emit(data)
        except Exception as error:
            self._report_error(error)
        finally:
            if lease is not None:
                lease.release()
