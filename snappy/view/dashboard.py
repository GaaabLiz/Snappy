import sys


from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QShortcut, QKeySequence, QIcon
from PySide6.QtWidgets import QApplication
from pylizlib.qt.domain.view import UiWidgetMode
from qfluentwidgets import FluentWindow, Theme, setTheme, setThemeColor, qconfig
from qframelesswindow.utils import getSystemAccentColor

from snappy.application.app import app, RESOURCE_ID_LOGO

from snappy.application.resources import resources_rc

class DashboardView(FluentWindow):
    """
    Main dashboard view for the Snappy application.
    Inherits from FluentWindow to provide a fluent design interface.
    """

    f5_pressed = Signal()

    def __init__(self):
        """
        Initialize the dashboard view, setting up the window properties and shortcuts.
        """
        super().__init__()
        self.__init_window()
        self.__init_shortcuts()
        qconfig.themeChanged.connect(self._apply_theme)
        QApplication.styleHints().colorSchemeChanged.connect(self._on_system_theme_changed)

    def __init_window(self):
        """
        Set up the window's dimensions, icon, title, and theme settings based on system preferences.
        """
        self.resize(1100, 700)
        self.setWindowIcon(QIcon(RESOURCE_ID_LOGO))
        self.setWindowTitle(app.name)
        if sys.platform in ["win32", "darwin"]:
            setThemeColor(getSystemAccentColor(), save=False)

    @Slot(object)
    def _apply_theme(self, theme: Theme):
        setTheme(theme, save=False)

    @Slot(Qt.ColorScheme)
    def _on_system_theme_changed(self, scheme: Qt.ColorScheme):
        if qconfig.get(qconfig.themeMode) != Theme.AUTO:
            return

        # Update the resolved palette while retaining the saved Auto preference.
        qconfig.theme = {Qt.ColorScheme.Light: Theme.LIGHT, Qt.ColorScheme.Dark: Theme.DARK}.get(scheme, Theme.AUTO)
        self._apply_theme(Theme.AUTO)

    def __init_shortcuts(self):
        """
        Initialize keyboard shortcuts for the dashboard, such as F5 for refreshing.
        """
        shortcut = QShortcut(QKeySequence("F5"), self)
        shortcut.activated.connect(self.f5_pressed.emit)

    def set_state(self, state: UiWidgetMode):
        """
        Update the UI state of the dashboard widgets.

        :param state: The new UI state mode to apply.
        :type state: UiWidgetMode
        """
        self.widget_catalogue.set_state(state)