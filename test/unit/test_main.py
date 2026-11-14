import types

def test_main(monkeypatch):
    # Mock settings
    import snappy.application.app
    class ASK: language = "lang"
    class AS:
        def get(self, k): return "it"
    monkeypatch.setattr(snappy.application.app, "AppSettings", ASK)
    monkeypatch.setattr(snappy.application.app, "app_settings", AS())
    
    # Mock i18n
    import snappy.application.i18n
    langs = []
    monkeypatch.setattr(snappy.application.i18n, "set_language", lambda l: langs.append(l))
    
    # Mock PySide6
    import PySide6.QtWidgets
    class FakeApp:
        def __init__(self, argv): self.argv = argv
        def installTranslator(self, t): pass
        def exec(self): return 42
        @classmethod
        def instance(cls): return cls
        @classmethod
        def processEvents(cls, *args, **kwargs): pass
    monkeypatch.setattr(PySide6.QtWidgets, "QApplication", FakeApp)
    
    import PySide6.QtCore
    class FakeLocale:
        Language = types.SimpleNamespace(Italian=1, English=2)
        Country = types.SimpleNamespace(Italy=1)
        def __init__(self, l, c=None): pass
    monkeypatch.setattr(PySide6.QtCore, "QLocale", FakeLocale)
    
    # Mock FluentTranslator
    import qfluentwidgets
    class FakeTranslator:
        def __init__(self, l): pass
    monkeypatch.setattr(qfluentwidgets, "FluentTranslator", FakeTranslator)
    
    # Mock Controllers
    import snappy.controller.splash
    import snappy.controller.dashboard
    class FakeSplash:
        started = False
        def start(self): FakeSplash.started = True
    class FakeDash:
        started = False
        def start(self): FakeDash.started = True
    monkeypatch.setattr(snappy.controller.splash, "SplashController", FakeSplash)
    monkeypatch.setattr(snappy.controller.dashboard, "DashboardController", FakeDash)
    
    from snappy.main import main
    ret = main()
    assert ret == 42
    assert langs == ["it"]
    assert FakeSplash.started
    assert FakeDash.started
    
    # Test English logic
    class AS_EN:
        def get(self, k): return "en"
    monkeypatch.setattr("snappy.main.app_settings", AS_EN())
    langs.clear()
    ret = main()
    assert ret == 42
    assert langs == ["en"]
