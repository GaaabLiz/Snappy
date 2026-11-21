from datetime import datetime
from types import SimpleNamespace

from pylizlib.core.os.snap import SnapshotCatalogueStatistics, SnapshotFileInfo

from snappy.controller.home import HomeController
from snappy.domain.data import SnappySnapshotData


def test_home_displays_catalogue_statistics(qtbot, tmp_path):
    controller = HomeController()
    view = controller.view
    qtbot.addWidget(view)
    catalogue_path = tmp_path / "catalogue"
    stats = SnapshotCatalogueStatistics(
        catalogue_path=catalogue_path,
        snapshot_count=2,
        total_size_bytes=6 * 1024 * 1024,
        file_count=1234,
        directory_count=24,
        largest_file=SnapshotFileInfo("s1", "folder", "nested/large.dat", 4 * 1024 * 1024),
        oldest_snapshot_date=datetime(2026, 1, 2),
        newest_snapshot_date=datetime(2026, 2, 3),
        backup_count=None,
    )

    controller.update_data(SnappySnapshotData([], home_statistics=stats, backup_count=3))

    assert view.card_snap_count.valueLabel.text() == "2"
    assert view.card_total_size.valueLabel.text() == "6.00 MB"
    assert view.card_avg_size.valueLabel.text() == "3.00 MB"
    assert view.card_total_files.valueLabel.text() == "1.234"
    assert view.card_total_dirs.valueLabel.text() == "24"
    assert view.card_heaviest_file.valueLabel.text() == "4.00 MB"
    assert view.card_heaviest_file.subtitleLabel.text() == "large.dat"
    assert view.card_oldest_snap_date.valueLabel.text() == "2026-01-02"
    assert view.card_last_snap_date.valueLabel.text() == "2026-02-03"
    assert view.card_backup_count.valueLabel.text() == "3"
    assert view.card_catalogue_path.valueLabel.text() == str(catalogue_path)


def test_home_distinguishes_empty_and_unavailable_statistics(qtbot, monkeypatch, tmp_path):
    controller = HomeController()
    view = controller.view
    qtbot.addWidget(view)
    catalogue_path = tmp_path / "catalogue"
    stats = SnapshotCatalogueStatistics(
        catalogue_path=catalogue_path,
        snapshot_count=0,
        total_size_bytes=0,
        file_count=0,
        directory_count=0,
        largest_file=None,
        oldest_snapshot_date=None,
        newest_snapshot_date=None,
        backup_count=None,
    )

    controller.update_data(SnappySnapshotData([], home_statistics=stats, backup_count=0))
    assert view.card_total_files.valueLabel.text() == "0"
    assert view.card_snap_count.valueLabel.text() == "0"
    assert view.card_heaviest_file.valueLabel.text() == "—"
    assert view.card_last_snap_date.valueLabel.text() == "—"
    assert view.card_backup_count.valueLabel.text() == "0"

    monkeypatch.setattr("snappy.model.home.app_settings", SimpleNamespace(get=lambda _: str(catalogue_path)))
    controller.update_data(SnappySnapshotData([]))

    assert view.card_total_files.valueLabel.text() == "—"
    assert view.card_snap_count.valueLabel.text() == "—"
    assert view.card_total_size.valueLabel.text() == "—"
    assert view.card_backup_count.valueLabel.text() == "—"
    assert view.card_catalogue_path.valueLabel.text() == str(catalogue_path)

