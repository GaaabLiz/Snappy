"""Exclusive ownership of critical work, shared by the dashboard's models.

Admission and completion run on the UI thread. A lease can span several runners
(for example an installation followed by a refresh) without briefly unlocking UI.
"""

from PySide6.QtCore import QObject, Signal


class OperationLease:
    def __init__(self, state: "OperationState", owner: object):
        self._state = state
        self.owner = owner

    def release(self):
        self._state.release(self)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.release()


class OperationState(QObject):
    active_changed = Signal(bool)
    rejected = Signal()

    def __init__(self):
        super().__init__()
        self._lease: OperationLease | None = None

    @property
    def operation_active(self) -> bool:
        return self._lease is not None

    def is_owned_by(self, owner: object) -> bool:
        return self._lease is not None and self._lease.owner is owner

    def try_acquire(self, owner: object) -> OperationLease | None:
        if self.operation_active:
            self.rejected.emit()
            return None
        lease = OperationLease(self, owner)
        self._lease = lease
        self.active_changed.emit(True)
        return lease

    def release(self, lease: OperationLease):
        # Duplicate or late completion signals cannot release a newer operation.
        if self._lease is lease:
            self._lease = None
            self.active_changed.emit(False)
