from PySide6.QtCore import Qt
from qfluentwidgets import InfoBar, InfoBarPosition

from snappy.application.i18n import tr
from snappy.model.history import init_action_history_db, list_actions
from snappy.view.history import ActionHistoryView


class ActionHistoryController:
    """
    Controller responsible for managing the action history view.

    This controller coordinates the interaction between the underlying action history
    model and the user interface representation, allowing the user to view a log of
    actions performed within the application.
    """

    def __init__(self):
        """
        Initializes the ActionHistoryController.

        This sets up the associated view component which will display the history data.
        """
        self.view = ActionHistoryView()
        self._storage_initialized = None
        self._warning_shown = False
        self.view.opened.connect(self.reload)

    def initialize_storage(self) -> bool:
        """Initializes the history database and remembers whether it is available."""
        self._storage_initialized = init_action_history_db()
        return self._storage_initialized

    def reload(self):
        """
        Reloads the action history data and updates the view.

        This method fetches the latest list of actions from the model using `list_actions()`
        and populates the view's rows with the retrieved data.
        """
        rows = list_actions()
        self.view.update_rows(rows)
        if self._storage_initialized is False and not self._warning_shown:
            InfoBar.warning(
                title=tr("History unavailable"),
                content=tr("The history database could not be initialized. Existing history may be unavailable and new actions may not be recorded."),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP_RIGHT,
                duration=8000,
                parent=self.view.window(),
            )
            self._warning_shown = True
