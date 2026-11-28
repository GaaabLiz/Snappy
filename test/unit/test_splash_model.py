import sys
import types

import pytest

def _import_splash_module(monkeypatch):
    app_module = types.ModuleType("snappy.application.app")
    
    class FakeAppSettingsKeys:
        catalogue_path = "catalogue_path"
        
    class FakeAppSettings:
        def __init__(self):
            self.settings = {"catalogue_path": "/fake/path"}
        def get(self, key):
            return self.settings.get(key)
        def set(self, key, value):
            self.settings[key] = value
            
    app_module.app_settings = FakeAppSettings()
    app_module.AppSettings = FakeAppSettingsKeys
    app_module.DEFAULT_SETTING_CATALOGUE_PATH = "/default/path"
    
    monkeypatch.setitem(sys.modules, "snappy.application.app", app_module)
    sys.modules.pop("snappy.model.splash", None)
    import snappy.model.splash as splash_module
    return splash_module

def test_splash_model_check_catalogue_path_exists(monkeypatch, tmp_path):
    splash_module = _import_splash_module(monkeypatch)
    model = splash_module.SplashModel()
    
    # Set to a valid temp path
    splash_module.app_settings.set("catalogue_path", str(tmp_path))
    assert model.check_catalogue_path() is True

def test_splash_model_check_catalogue_path_not_exists(monkeypatch, tmp_path):
    splash_module = _import_splash_module(monkeypatch)
    model = splash_module.SplashModel()
    
    # Set to an invalid path
    invalid_path = tmp_path / "not_exists"
    splash_module.app_settings.set("catalogue_path", str(invalid_path))
    assert model.check_catalogue_path() is False

def test_splash_model_get_catalogue_path_str(monkeypatch):
    splash_module = _import_splash_module(monkeypatch)
    model = splash_module.SplashModel()
    
    splash_module.app_settings.set("catalogue_path", "/foo/bar")
    assert model.get_catalogue_path_str() == "/foo/bar"

def test_splash_model_set_default_catalogue_path(monkeypatch, tmp_path):
    splash_module = _import_splash_module(monkeypatch)
    model = splash_module.SplashModel()
    default = tmp_path / "Catalogue"
    monkeypatch.setattr(splash_module, "DEFAULT_SETTING_CATALOGUE_PATH", str(default))
    
    model.set_default_catalogue_path()
    assert default.is_dir()
    assert splash_module.app_settings.get("catalogue_path") == str(default)


def test_first_launch_creates_the_default_catalogue(monkeypatch, tmp_path):
    splash_module = _import_splash_module(monkeypatch)
    default = tmp_path / "Catalogue"
    monkeypatch.setattr(splash_module, "DEFAULT_SETTING_CATALOGUE_PATH", str(default))
    splash_module.app_settings.set("catalogue_path", str(default))

    assert splash_module.SplashModel().check_catalogue_path()
    assert default.is_dir()


@pytest.mark.parametrize("configured_path", ["", "  ", "catalogue"])
def test_non_absolute_catalogue_path_is_rejected(monkeypatch, tmp_path, configured_path):
    splash_module = _import_splash_module(monkeypatch)
    (tmp_path / "catalogue").mkdir()
    monkeypatch.chdir(tmp_path)
    splash_module.app_settings.set("catalogue_path", configured_path)

    assert splash_module.SplashModel().check_catalogue_path() is False
