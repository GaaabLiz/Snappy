from dataclasses import dataclass, field

from pylizlib.core.os.snap import Snapshot, SnapshotBackupInfo, SnapshotCatalogueStatistics
from pylizlib.qtfw.domain.sw import SoftwareData


@dataclass
class SnappySnapshotData:
    """Snapshot list and catalogue statistics from one dashboard refresh."""

    snapshot_list: list[Snapshot]
    home_statistics: SnapshotCatalogueStatistics | None = None
    backup_count: int | None = None


# @dataclass
# class SnappySettingsData:
#     starred_dirs: list[Path] = None
#     starred_files: list[Path] = None
#     starred_exes: list[Path] = None
#     tags: list[str] = None
#     custom_snap_data: list[str] = None


@dataclass
class SnappyData:
    """
    Data class representing the overall application data model.
    
    This class holds the state for monitored software, monitored services, 
    and all tracked snapshot data.
    """
    monitored_software: list[SoftwareData] = None
    monitored_services: list[SoftwareData] = None
    snapshots: list[Snapshot] = field(default_factory=list)
    home_statistics: SnapshotCatalogueStatistics | None = None
    backup_count: int | None = None
    backups: list[SnapshotBackupInfo] | None = None
