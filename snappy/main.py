import sys

from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator, InfoBar, InfoBarPosition

from snappy.application.app import app_settings, AppSettings
from snappy.application.i18n import set_language, tr
from snappy.controller.dashboard import DashboardController
from snappy.controller.splash import SplashController
from snappy.model.history import init_action_history_db

def main():
    """
    The main entry point for the Snappy application.
    
    This function initializes the application settings, sets the language,
    initializes the action history database, and configures the main Qt 
    application instance with necessary translators. Finally, it starts 
    the splash and dashboard controllers and begins the Qt event loop.
    
    Returns:
        int: The exit code of the Qt application.
    """
    # Initialize language from settings
    lang = app_settings.get(AppSettings.language)
    set_language(lang)
    
    history_initialized = init_action_history_db()

    qt_app = QApplication(sys.argv)

    # Install FluentTranslator for built-in component translations
    locale = QLocale(QLocale.Language.Italian, QLocale.Country.Italy) if lang == "it" else QLocale(QLocale.Language.English)
    translator = FluentTranslator(locale)
    qt_app.installTranslator(translator)

    splash_controller = SplashController()
    splash_controller.start()

    dashboard = DashboardController()
    dashboard.start()
    if not history_initialized:
        InfoBar.warning(
            title=tr("History unavailable"),
            content=tr("The history database could not be initialized. Existing history may be unavailable and new actions may not be recorded."),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP_RIGHT,
            duration=8000,
            parent=dashboard.view,
        )
    return qt_app.exec()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())