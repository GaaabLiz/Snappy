from snappy.application import app

def test_network_folder_validator():
    validator = app.NetworkFolderValidator()
    assert validator.validate("some string") is True
    assert validator.validate(123) is False
    assert validator.validate(None) is False
    
    assert validator.correct("test") == "test"
    assert validator.correct(123) == "123"
    assert validator.correct(None) == ""


def test_unavailable_backup_path_preserves_other_saved_preferences(tmp_path):
    import json

    from qfluentwidgets import QConfig

    unavailable = tmp_path / "backup"
    unavailable.touch()
    catalogue_path = (tmp_path / "my-catalogue").as_posix()
    config_file = tmp_path / "Settings.json"
    config_file.write_text(json.dumps({
        "Backups": {"Backup Path": unavailable.as_posix(), "Backup Before Install": False},
        "Configurazioni": {"Catalogue Path": catalogue_path},
        "App": {"Language": "it"},
    }), encoding="utf-8")
    items = (
        app.AppSettings.backup_path, app.AppSettings.backup_before_install,
        app.AppSettings.catalogue_path, app.AppSettings.language,
    )
    previous = [item.value for item in items]
    try:
        reader = QConfig()
        reader.load(config_file, app.AppSettings())
        assert [item.value for item in items] == [unavailable.as_posix(), False, catalogue_path, "it"]
        reader.save()
        assert json.loads(config_file.read_text(encoding="utf-8"))["App"]["Language"] == "it"
        future_folder = tmp_path / "future"
        assert app.AppSettings.backup_path.validator.correct(future_folder) == future_folder.as_posix()
        assert not future_folder.exists()
    finally:
        for item, value in zip(items, previous):
            item.value = value


def test_sync_snap_settings_immediate(qtbot):
    from snappy.application.app import AppSettings, snap_settings
    from snappy.controller.setting import SettingController
    import qfluentwidgets
    
    # Initialize the controller so it attaches the signals
    class DummyModel:
        def update(self): pass
    ctrl = SettingController(DummyModel())
    qtbot.addWidget(ctrl.view)
    
    # Inizialmente impostiamo un valore noto
    qfluentwidgets.qconfig.set(AppSettings.backup_before_install, False)
    assert snap_settings.backup_pre_install is False
    
    # Modifichiamo il setting tramite l'interfaccia qconfig (simulando l'UI)
    qfluentwidgets.qconfig.set(AppSettings.backup_before_install, True)
    
    # Verifichiamo che il valore sia stato sincronizzato istantaneamente senza refresh
    assert snap_settings.backup_pre_install is True


def test_everyone_full_control_switch_is_visible_and_updates_settings(qtbot):
    import sys

    from PySide6.QtCore import Qt

    from snappy.application.app import AppSettings, app_settings, snap_settings
    from snappy.view.setting import WidgetSettings

    option = AppSettings.install_with_everyone_full_control
    assert option.defaultValue is (sys.platform == "win32")
    original = app_settings.get(option)
    try:
        app_settings.set(option, False)
        view = WidgetSettings()
        qtbot.addWidget(view)
        view.show()
        card = view.card_install_with_everyone_full_control
        assert card.isVisible()
        assert not card.isChecked()

        qtbot.mouseClick(card.switchButton.indicator, Qt.MouseButton.LeftButton)
        assert app_settings.get(option) is True
        assert snap_settings.install_with_everyone_full_control is True

        qtbot.mouseClick(card.switchButton.indicator, Qt.MouseButton.LeftButton)
        assert app_settings.get(option) is False
        assert snap_settings.install_with_everyone_full_control is False
    finally:
        app_settings.set(option, original)


def test_snapshot_preferences_update_the_library_settings(qtbot, monkeypatch, tmp_path):
    from pylizlib.core.os.snap import CopyMetadataMode, ExtendedMetadataCopyStrategy, VerifiedFileCopyStrategy

    from snappy.application.app import AppSettings, app_settings, snap_settings
    from snappy.view.setting import WidgetSettings

    items = (
        AppSettings.copy_strategy, AppSettings.copy_metadata_mode, AppSettings.allow_legacy_snapshots,
        AppSettings.max_archive_gib, AppSettings.max_archive_entries, AppSettings.archive_temp_directory,
        AppSettings.search_max_results, AppSettings.search_regex_timeout,
        AppSettings.verify_backup_before_removal,
    )
    previous = [app_settings.get(item) for item in items]
    try:
        assert AppSettings.copy_strategy.defaultValue == "standard"
        assert AppSettings.copy_metadata_mode.defaultValue == "basic"
        assert AppSettings.allow_legacy_snapshots.defaultValue is True
        assert AppSettings.verify_backup_before_removal.defaultValue is False

        view = WidgetSettings()
        qtbot.addWidget(view)

        for card, value in (
            (view.card_copy_strategy, "verified"),
            (view.card_copy_metadata, "extended"),
            (view.card_archive_size, 250),
            (view.card_archive_entries, 500_000),
            (view.card_search_max_results, 2500),
            (view.card_search_regex_timeout, 0.5),
        ):
            card.combo_box.setCurrentIndex(card.combo_box.findData(value))

        assert snap_settings.copy_metadata_mode is CopyMetadataMode.EXTENDED
        assert isinstance(snap_settings.copy_strategy, ExtendedMetadataCopyStrategy)
        assert isinstance(snap_settings.copy_strategy.delegate, VerifiedFileCopyStrategy)
        assert snap_settings.max_archive_uncompressed_bytes == 250 * 1024**3
        assert snap_settings.max_archive_entries == 500_000
        assert app_settings.get(AppSettings.search_max_results) == 2500
        assert app_settings.get(AppSettings.search_regex_timeout) == 0.5

        view.card_allow_legacy_snapshots.setChecked(False)
        assert snap_settings.allow_unverified_legacy_snapshots is False

        view.card_verify_backup_before_removal.setChecked(True)
        assert app_settings.get(AppSettings.verify_backup_before_removal) is True
        view.card_verify_backup_before_removal.setChecked(False)
        assert app_settings.get(AppSettings.verify_backup_before_removal) is False

        monkeypatch.setattr("snappy.view.setting.QFileDialog.getExistingDirectory", lambda *_: str(tmp_path))
        view.card_archive_temp.clicked.emit()
        assert snap_settings.archive_temp_directory == tmp_path
        view.reset_archive_temp.click()
        assert snap_settings.archive_temp_directory is None
    finally:
        for item, value in zip(items, previous):
            app_settings.set(item, value)


def test_auto_theme_updates_the_session_without_saving_a_fixed_theme():
    from PySide6.QtCore import Qt
    from qfluentwidgets import Theme, qconfig

    from snappy.view.dashboard import DashboardView

    from types import SimpleNamespace

    view = SimpleNamespace(_apply_theme=lambda theme: DashboardView._apply_theme(None, theme))
    original = qconfig.get(qconfig.themeMode)
    try:
        qconfig.set(qconfig.themeMode, Theme.AUTO, save=False)
        DashboardView._on_system_theme_changed(view, Qt.ColorScheme.Dark)
        assert qconfig.theme == Theme.DARK
        assert qconfig.get(qconfig.themeMode) == Theme.AUTO

        qconfig.set(qconfig.themeMode, Theme.LIGHT, save=False)
        DashboardView._on_system_theme_changed(view, Qt.ColorScheme.Dark)
        assert qconfig.theme == Theme.LIGHT
    finally:
        qconfig.set(qconfig.themeMode, original, save=False)


def test_backup_path_change_is_rolled_back_if_settings_cannot_be_saved(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock

    import pytest

    from snappy.application.app import AppSettings, app_settings, snap_settings
    from snappy.model.setting import SettingModel

    option = AppSettings.backup_path
    previous_value = app_settings.get(option)
    previous_path = snap_settings.backup_path
    new_folder = tmp_path / "backups"
    new_folder.mkdir()
    dashboard = SimpleNamespace(operation_active=False, update=Mock())
    model = SettingModel(dashboard)
    updates = []
    model.backup_path_updated.connect(updates.append)

    def fail_save():
        assert app_settings.get(option) == str(new_folder)
        assert snap_settings.backup_path == previous_path
        raise OSError("Settings.json is not writable")

    monkeypatch.setattr(app_settings, "save", fail_save)
    with pytest.raises(OSError, match="Settings.json is not writable"):
        model.set_backup_path(str(new_folder))

    assert app_settings.get(option) == previous_value
    assert snap_settings.backup_path == previous_path
    assert updates == []
    dashboard.update.assert_not_called()


def test_catalogue_setting_rejects_relative_paths_and_keeps_offline_absolute_paths(tmp_path):
    from snappy.application.app import AppSettings

    validator = AppSettings.catalogue_path.validator
    offline = tmp_path / "offline"
    assert validator.correct("catalogue") == ""
    assert validator.correct(offline) == str(offline)
    assert not offline.exists()
