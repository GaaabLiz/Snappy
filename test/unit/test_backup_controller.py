import sys
import types
from pathlib import Path

def test_backup_controller(monkeypatch):
    import snappy.application.i18n
    monkeypatch.setattr(snappy.application.i18n, "tr", lambda x, **kw: x.format(**kw) if kw else x)
    
    # Mock action history
    import snappy.model.history as hist_mod
    actions = []
    def fake_log(c, t, d): actions.append((c, t, d))
    monkeypatch.setattr(hist_mod, "log_action", fake_log)
    
    msgs = []
    
    # Mock app_settings
    app_mod = types.ModuleType("snappy.application.app")
    class ASK: backup_path = "b"
    class AS:
        def get(self, k): return "/backup/path"
    app_mod.AppSettings = ASK
    app_mod.app_settings = AS()
    monkeypatch.setitem(sys.modules, "snappy.application.app", app_mod)
    
    # Mock View & Signals
    view_mod = types.ModuleType("snappy.view.backup")
    class FakeSignal:
        def __init__(self): self.c = None
        def connect(self, f): self.c = f
        def emit(self, *args): self.c(*args) if self.c else None
    class FakeView:
        def __init__(self, _model=None):
            self.signal_open_requested = FakeSignal()
            self.signal_restore_requested = FakeSignal()
            self.signal_delete_requested = FakeSignal()
            self.reloaded = False
        def reload_data(self):
            self.reloaded = True
    view_mod.BackupView = FakeView
    monkeypatch.setitem(sys.modules, "snappy.view.backup", view_mod)
    
    model_mod = types.ModuleType("snappy.model.backup")
    class FakeModel:
        def set_backups(self, backups): self.backups = backups
        def get_all_backups(self, p): return []
    model_mod.BackupModel = FakeModel
    monkeypatch.setitem(sys.modules, "snappy.model.backup", model_mod)

    dashboard_mod = types.ModuleType("snappy.model.dashboard")
    dashboard_mod.DashboardModel = type("DashboardModel", (), {})
    monkeypatch.setitem(sys.modules, "snappy.model.dashboard", dashboard_mod)
    
    # Fake catalogue
    class FakeCat:
        def __init__(self):
            self.restore_calls = []
            self.delete_calls = []

        def restore_backup(self, p):
            self.restore_calls.append(p)
            if "error" in str(p): raise Exception("fail restore")
        def delete_backup(self, p):
            self.delete_calls.append(p)
            if "error" in str(p): raise Exception("fail delete")

    class FakeTask:
        def update_task_message(self, message):
            pass

        def update_task_progress(self, progress):
            pass

    class FakeDash:
        def __init__(self, catalogue):
            self.snap_catalogue = catalogue
            self.operation_active = False
            self.pending = []
            self.refreshes = 0
            self.rejected = 0

        def run_heavy_operation(self, name, description, action, **options):
            if self.operation_active:
                self.rejected += 1
                return False
            self.operation_active = True
            self.pending.append((name, description, action, options))
            return True

        def finish_next(self):
            name, description, action, options = self.pending.pop(0)
            try:
                action(FakeTask())
            except Exception as error:
                msgs.append(options["error_msg_template"].format(error=str(error)))
            else:
                if options["update_dashboard"]:
                    self.refreshes += 1
            finally:
                self.operation_active = False
            return name, description, options
            
    # Mock QDesktopServices
    opened = []
    class FakeQDS:
        @classmethod
        def openUrl(cls, u): opened.append(u.toLocalFile())
    
    # Mock MessageBox
    class FakeMessageBox:
        res = True
        def __init__(self, t, d, parent=None): pass
        def exec_(self): return self.res

    # Import Controller
    sys.modules.pop("snappy.controller.backup", None)
    from snappy.controller.backup import BackupController
    from pylizlib.core.os.snap.domain import SnapshotBackupInfo
    
    monkeypatch.setattr("snappy.controller.backup.QDesktopServices", FakeQDS)
    monkeypatch.setattr("snappy.controller.backup.MessageBox", FakeMessageBox)
    
    cat = FakeCat()
    dash = FakeDash(cat)
    ctrl = BackupController(dash)
    
    # update_data
    ctrl.update_data([])
    assert ctrl.model.backups == []
    assert ctrl.view.reloaded
    
    # test __handle_open
    b1 = SnapshotBackupInfo(file_name="f1", path=Path("/a/b/f1"), snapshot_id=None, backup_type=None, created_at=None, prefix="", is_export=False)
    ctrl.view.signal_open_requested.emit(b1)
    assert opened == ["/a/b"]
    assert actions[-1][1] == hist_mod.ActionType.BACKUP_OPENED_IN_FINDER
    
    # test __handle_restore
    ctrl.view.signal_restore_requested.emit(b1)
    assert cat.restore_calls == []
    name, _, options = dash.finish_next()
    assert name == "Restore backup"
    assert options["update_dashboard"] is True
    assert cat.restore_calls == [b1.path]
    assert actions[-1][1] == hist_mod.ActionType.BACKUP_RESTORED
    
    # test __handle_delete
    ctrl.view.signal_delete_requested.emit(b1)
    assert cat.delete_calls == []
    name, _, options = dash.finish_next()
    assert name == "Delete backup"
    assert options["update_dashboard"] is True
    assert cat.delete_calls == [b1.path]
    assert actions[-1][1] == hist_mod.ActionType.BACKUP_DELETED
    assert dash.refreshes == 2
    
    # test MessageBox cancel
    FakeMessageBox.res = False
    ctrl.view.signal_restore_requested.emit(b1)
    ctrl.view.signal_delete_requested.emit(b1)
    assert dash.pending == []
    
    dash.operation_active = True
    FakeMessageBox.res = True
    ctrl.view.signal_restore_requested.emit(b1)
    ctrl.view.signal_delete_requested.emit(b1)
    assert dash.rejected == 2
    assert dash.pending == []
    dash.operation_active = False

    # test exceptions
    FakeMessageBox.res = True
    b_err = SnapshotBackupInfo(file_name="error", path=Path("/a/b/error"), snapshot_id=None, backup_type=None, created_at=None, prefix="", is_export=False)
    ctrl.view.signal_restore_requested.emit(b_err)
    dash.finish_next()
    assert "fail restore" in msgs[-1]
    
    ctrl.view.signal_delete_requested.emit(b_err)
    dash.finish_next()
    assert "fail delete" in msgs[-1]
    assert not dash.operation_active
    
    # open exception
    def fake_openUrl_err(u): raise Exception("open error")
    FakeQDS.openUrl = fake_openUrl_err
    ctrl.view.signal_open_requested.emit(b_err)
    # just asserts it doesn't crash

