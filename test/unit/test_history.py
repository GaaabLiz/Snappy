import sqlite3
from unittest.mock import MagicMock, Mock

import pytest


def test_history(monkeypatch, tmp_path):
    db_path = tmp_path / "test_history.db"
    
    # Need to patch app before importing action_history because it's imported at module level
    import snappy.application.app
    monkeypatch.setattr(snappy.application.app.app, "get_path", lambda: str(tmp_path))
    
    import snappy.model.history as ah
    monkeypatch.setattr(ah, "PATH_ACTION_HISTORY_DB", db_path)
    
    ah.init_action_history_db()
    
    # enum
    ah.log_action(ah.ActionCategory.DASHBOARD, ah.ActionType.DASHBOARD_F5_PRESSED, "details")
    
    # str
    ah.log_action("CustomScreen", "CustomAction", "CustomDetails")
    
    actions = ah.list_actions()
    
    assert len(actions) == 2
    
    assert actions[0]["screen_key"] == "CustomScreen"
    assert actions[0]["action_key"] == "CustomAction"
    assert actions[0]["details"] == "CustomDetails"
    
    assert actions[1]["screen_key"] == "Dashboard"
    assert actions[1]["action_key"] == "dashboard.f5.pressed"
    assert actions[1]["details"] == "details"


@pytest.mark.parametrize("stage", ["connect", "execute", "commit", "exit", "directory"])
def test_log_action_storage_failure_is_logged_without_raising(monkeypatch, stage):
    import snappy.model.history as history

    connection = MagicMock()
    connection.__enter__.return_value = connection
    get_connection = Mock(return_value=connection)
    error = sqlite3.OperationalError("history unavailable")
    if stage == "directory":
        get_connection.side_effect = PermissionError("history directory is not writable")
    elif stage == "connect":
        get_connection.side_effect = error
    elif stage == "exit":
        connection.__exit__.side_effect = error
    else:
        getattr(connection, stage).side_effect = error
    monkeypatch.setattr(history, "_get_connection", get_connection)
    warning = Mock()
    monkeypatch.setattr(history.logger, "warning", warning)

    history.log_action(
        history.ActionCategory.CATALOGUE, history.ActionType.CATALOGUE_SNAPSHOT_INSTALLED, "Snapshot"
    )
    warning.assert_called_once()
