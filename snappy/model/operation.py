"""Adapt library operation feedback to Snappy's Qt workers."""

from collections.abc import Callable
from threading import Event

from pylizlib.core.os.snap import (
    SnapshotOperationCancelled,
    SnapshotOperationPhase,
    SnapshotOperationUpdate,
    run_snapshot_operation,
)
from pylizlib.qt.handler.operation_core import GenericTask

from snappy.application.i18n import tr


_PHASE_TEXT = {
    SnapshotOperationPhase.WAITING_FOR_CATALOGUE: "Waiting for the catalogue...",
    SnapshotOperationPhase.CATALOGUE_UNAVAILABLE: "Catalogue unavailable",
    SnapshotOperationPhase.PREPARING: "Preparing...",
    SnapshotOperationPhase.CHECKING_JOURNAL: "Checking the transaction journal...",
    SnapshotOperationPhase.RECOVERING: "Recovering an interrupted operation...",
    SnapshotOperationPhase.READING: "Reading the catalogue...",
    SnapshotOperationPhase.VALIDATING: "Validating...",
    SnapshotOperationPhase.COPYING: "Copying files...",
    SnapshotOperationPhase.BACKING_UP: "Creating backup...",
    SnapshotOperationPhase.EXTRACTING: "Extracting archive...",
    SnapshotOperationPhase.VERIFYING: "Verifying files...",
    SnapshotOperationPhase.SEARCHING: "Searching...",
    SnapshotOperationPhase.PUBLISHING: "Applying changes...",
    SnapshotOperationPhase.ROLLING_BACK: "Reverting changes...",
    SnapshotOperationPhase.FINALIZING: "Finalizing...",
    SnapshotOperationPhase.COMPLETED: "Operation completed",
    SnapshotOperationPhase.CANCELLED: "Operation cancelled",
    SnapshotOperationPhase.FAILED: "Operation failed",
}


def operation_status(update: SnapshotOperationUpdate) -> str:
    """Return the localized label for a library operation phase."""
    return tr(_PHASE_TEXT[update.phase])


class CatalogueTask(GenericTask):
    """Run a catalogue action with feedback and a cancellable wait."""

    def __init__(
        self,
        name: str,
        action: Callable,
        on_update: Callable[[SnapshotOperationUpdate], None] | None = None,
    ):
        super().__init__(name, action)
        self.on_update = on_update
        self._cancel_requested = Event()

    def prepare(self):
        """Reset the request before this worker is scheduled again."""
        self._cancel_requested.clear()
        self.is_cancelled = False

    def request_cancellation(self):
        """Ask the library to cancel the wait at its next safe point."""
        self._cancel_requested.set()

    def execute(self):
        try:
            return run_snapshot_operation(
                super().execute,
                on_update=self.on_update,
                is_cancelled=self._cancel_requested.is_set,
            )
        except SnapshotOperationCancelled:
            self.cancel()
