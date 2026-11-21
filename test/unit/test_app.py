from snappy.application import app

def test_network_folder_validator():
    validator = app.NetworkFolderValidator()
    assert validator.validate("some string") is True
    assert validator.validate(123) is False
    assert validator.validate(None) is False
    
    assert validator.correct("test") == "test"
    assert validator.correct(123) == "123"
    assert validator.correct(None) == ""

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
    )
    previous = [app_settings.get(item) for item in items]
    try:
        assert AppSettings.copy_strategy.defaultValue == "standard"
        assert AppSettings.copy_metadata_mode.defaultValue == "basic"
        assert AppSettings.allow_legacy_snapshots.defaultValue is True

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

        monkeypatch.setattr("snappy.view.setting.QFileDialog.getExistingDirectory", lambda *_: str(tmp_path))
        view.card_archive_temp.clicked.emit()
        assert snap_settings.archive_temp_directory == tmp_path
        view.reset_archive_temp.click()
        assert snap_settings.archive_temp_directory is None
    finally:
        for item, value in zip(items, previous):
            app_settings.set(item, value)
