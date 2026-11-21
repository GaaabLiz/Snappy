import sys
import types

def test_history_controller(monkeypatch):
    # Mock view
    view_mod = types.ModuleType("snappy.view.history")
    class FakeActionHistoryView:
        def __init__(self):
            self.rows = []
            self.opened = types.SimpleNamespace(connect=lambda reload: setattr(self, "open_page", reload))
        def update_rows(self, rows):
            self.rows = rows
    view_mod.ActionHistoryView = FakeActionHistoryView
    monkeypatch.setitem(sys.modules, "snappy.view.history", view_mod)
    
    # Mock list_actions
    app_history_mod = types.ModuleType("snappy.model.history")
    app_history_mod.init_action_history_db = lambda: True
    app_history_mod.list_actions = lambda: ["action1", "action2"]
    monkeypatch.setitem(sys.modules, "snappy.model.history", app_history_mod)
    
    # Import
    sys.modules.pop("snappy.controller.history", None)
    import snappy.controller.history as c
    
    controller = c.ActionHistoryController()
    if hasattr(controller, "view") and "qtbot" in locals() and hasattr(qtbot, "addWidget"):
        qtbot.addWidget(controller.view)
    controller.view.open_page()
    
    assert controller.view.rows == ["action1", "action2"]
    monkeypatch.setattr(c, "list_actions", lambda: ["new action", "action1", "action2"])
    controller.view.open_page()
    assert controller.view.rows[0] == "new action"
