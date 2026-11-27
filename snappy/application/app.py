import logging
import sys
from functools import partial
from pathlib import Path

from loguru import logger
from loguru_logging_intercept import setup_loguru_logging_intercept
from pylizlib.core.app.pylizapp import PylizApp
from pylizlib.core.os.snap import CopyMetadataMode, SequentialFileCopyStrategy, SnapshotSettings, VerifiedFileCopyStrategy
from pylizlib.core.os.snap.searcher import SnapshotSearchParams
from pylizlib.core.os.snap.storage.archive_limits import DEFAULT_MAX_ARCHIVE_ENTRIES, DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES
from pylizlib.core.os.windows.commands import PATH_DEFAULT_GIT_BASH
from pylizlib.qtfw.domain.setting import QtFwQConfigItem
from pylizlib.qtfw.model.qconfig import TextListValidator, ExecutableValidator
from qfluentwidgets import QConfig, BoolValidator, qconfig, OptionsValidator, OptionsConfigItem, ConfigValidator

from snappy.project import version, name, authors

# Application object
app = PylizApp(name, version, name, authors[0][0])

# Application directories
PATH_CATALOGUE = Path(app.get_path()).joinpath("Catalogue")
PATH_SCRIPTS = Path(app.get_path()).joinpath("Scripts")
PATH_TRASH = Path(app.get_path()).joinpath("Trash")
PATH_LOGS = Path(app.get_path()).joinpath("Logs")
PATH_TEMP = Path(app.get_path()).joinpath("Temp")
PATH_BACKUPS = Path(app.get_path()).joinpath("Backups")
PATH_JSON_SETTING_FILE = Path(app.get_path()).joinpath("Settings.json")

# VALORI DI DEFAULT DELLE IMPOSTAZIONI
DEFAULT_SETTING_CATALOGUE_PATH = PATH_CATALOGUE.__str__()
DEFAULT_SETTING_STARRED_DIRS = []
DEFAULT_SETTING_STARRED_FILES = []
DEFAULT_SETTING_STARRED_EXES = []
DEFAULT_SETTING_STARRED_SERVICES = []
DEFAULT_SETTING_CONFIGURATION_TAGS = []
DEFAULT_SETTING_SNAPSHOTS_CUSTOM_DATA = []
DEFAULT_SETTING_PATH_GIT_BASH = PATH_DEFAULT_GIT_BASH.__str__()
DEFAULT_SETTING_CONFIG_BACKUP_BEFORE_INSTALL = True
DEFAULT_SETTING_CONFIG_BACKUP_BEFORE_EDIT = False
DEFAULT_SETTING_CONFIG_BACKUP_BEFORE_DELETE = True
DEFAULT_SETTING_CLEAR_SNAP_ATTACHED_FOLDERS_BEFORE_INSTALL = True
DEFAULT_SETTING_LANGUAGE = "en"
EXIT_CODE_RESTART = 1000

# DEFINIZIONE DEI GRUPPI DI IMPOSTAZIONI
SETTING_GROUP_CONFIGS = "Configurazioni"
SETTING_GROUP_SCRIPTS = "Scripts"
SETTING_GROUP_FAVORITES = "Preferiti"
SETTING_GROUP_BACKUPS = "Backups"
SETTING_GROUP_APP = "App"
SETTING_GROUP_SEARCH = "Search"
BYTES_PER_GIB = 1024**3
COPY_STRATEGIES = {
    "standard": SequentialFileCopyStrategy,
    "verified": VerifiedFileCopyStrategy,
}

# GESTIONE RISORSE
RESOURCE_ID_LOGO = ':/resources/logo2.png'

# GESTIONE LOGS
logger.remove()
if sys.stdout:
    logger.add(sys.stdout,level="DEBUG",format="{time:HH:mm:ss} | {level} | {message}", colorize=True)
logger.add(
    Path(PATH_LOGS).joinpath("{time:YYYY-MM-DD}.log").__str__(),
    level="DEBUG", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}",
    rotation="00:00", retention="30 days", compression=None
)
setup_loguru_logging_intercept(level=logging.DEBUG, modules=("PylizLib",))
logger.info("{} Application Started. Version: {}", app.name, app.version)


# TODO: MOve to lib
class NetworkFolderValidator(ConfigValidator):
    """
    Validator that does not check if the folder exists, preventing automatic fallback for network drives.
    
    This is useful for configuration items that point to network paths which might not 
    be immediately available when the application starts.
    """
    def validate(self, value):
        """
        Validate that the provided value is a string.
        
        Args:
            value: The value to validate.
            
        Returns:
            bool: True if the value is a string, False otherwise.
        """
        return isinstance(value, str)

    def correct(self, value):
        """
        Correct the value by converting it to a string.
        
        Args:
            value: The input value.
            
        Returns:
            str: The corrected string value or an empty string if None.
        """
        return str(value) if value else ""


class BackupFolderValidator(NetworkFolderValidator):
    """Normalize a backup path without opening or creating the directory."""

    def correct(self, value):
        if not isinstance(value, (str, Path)) or not value:
            return PATH_BACKUPS.as_posix()
        return Path(value).absolute().as_posix()


# DEFINITION OF APPLICATION SETTINGS
class AppSettings(QConfig):
    """
    Configuration class for the application settings.
    
    This class defines all the customizable settings for the application using 
    qfluentwidgets configuration items. It covers configurations, scripts, 
    favorites, backups, and general app settings.
    """
    config_tags = QtFwQConfigItem(True, SETTING_GROUP_CONFIGS, "Tag configurazioni", DEFAULT_SETTING_CONFIGURATION_TAGS, TextListValidator())
    catalogue_path = QtFwQConfigItem(True, SETTING_GROUP_CONFIGS, "Catalogue Path", DEFAULT_SETTING_CATALOGUE_PATH, NetworkFolderValidator())
    backup_before_install = QtFwQConfigItem(True, SETTING_GROUP_BACKUPS, "Backup Before Install", DEFAULT_SETTING_CONFIG_BACKUP_BEFORE_INSTALL, BoolValidator())
    backup_before_edit = QtFwQConfigItem(True, SETTING_GROUP_BACKUPS, "Backup Before Edit", DEFAULT_SETTING_CONFIG_BACKUP_BEFORE_EDIT, BoolValidator())
    backup_before_delete = QtFwQConfigItem(True, SETTING_GROUP_BACKUPS, "Backup Before Delete", DEFAULT_SETTING_CONFIG_BACKUP_BEFORE_DELETE, BoolValidator())
    backup_path = QtFwQConfigItem(True, SETTING_GROUP_BACKUPS, "Backup Path", PATH_BACKUPS.as_posix(), BackupFolderValidator())
    snap_custom_data = QtFwQConfigItem(True, SETTING_GROUP_CONFIGS, "Snapshots custom data", DEFAULT_SETTING_SNAPSHOTS_CUSTOM_DATA, TextListValidator())
    git_bash_path = QtFwQConfigItem(True, SETTING_GROUP_SCRIPTS, "Git Bash path", DEFAULT_SETTING_PATH_GIT_BASH, ExecutableValidator())
    starred_dirs = QtFwQConfigItem(True, SETTING_GROUP_FAVORITES,"Cartelle preferite", DEFAULT_SETTING_STARRED_DIRS, TextListValidator())
    starred_files = QtFwQConfigItem(True, SETTING_GROUP_FAVORITES,"File preferiti", DEFAULT_SETTING_STARRED_FILES, TextListValidator())
    # Eseguibili e servizi non sono impostazioni attive né vengono serializzati.
    # starred_exes = QtFwQConfigItem(True, SETTING_GROUP_FAVORITES, "Eseguibili Preferiti", DEFAULT_SETTING_STARRED_EXES, TextListValidator())
    # starred_services = QtFwQConfigItem(True, SETTING_GROUP_FAVORITES, "Servizi Preferiti", DEFAULT_SETTING_STARRED_SERVICES, TextListValidator())
    debug_test_mode = QtFwQConfigItem(False, SETTING_GROUP_APP, "DebugTestMode", False, BoolValidator())
    clear_snap_attached_folders_before_install = QtFwQConfigItem(True, SETTING_GROUP_CONFIGS, "Clear snap attached folders before install", DEFAULT_SETTING_CLEAR_SNAP_ATTACHED_FOLDERS_BEFORE_INSTALL, BoolValidator())
    install_with_everyone_full_control = QtFwQConfigItem(True, SETTING_GROUP_CONFIGS, "Grant Everyone full control", sys.platform == "win32", BoolValidator())
    verify_backup_before_removal = QtFwQConfigItem(True, SETTING_GROUP_CONFIGS, "Verify backup before removal", False, BoolValidator())
    allow_legacy_snapshots = QtFwQConfigItem(True, SETTING_GROUP_CONFIGS, "Allow legacy snapshots", True, BoolValidator())
    copy_strategy = OptionsConfigItem(SETTING_GROUP_CONFIGS, "Copy strategy", "standard", OptionsValidator(list(COPY_STRATEGIES)))
    copy_metadata_mode = OptionsConfigItem(SETTING_GROUP_CONFIGS, "Copy metadata mode", CopyMetadataMode.BASIC.value,
                                           OptionsValidator([mode.value for mode in CopyMetadataMode]))
    archive_temp_directory = QtFwQConfigItem(True, SETTING_GROUP_BACKUPS, "Archive temporary directory", "", NetworkFolderValidator())
    max_archive_gib = OptionsConfigItem(SETTING_GROUP_BACKUPS, "Maximum expanded archive GiB", DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES // BYTES_PER_GIB,
                                        OptionsValidator([25, 50, 100, 250, 500]))
    max_archive_entries = OptionsConfigItem(SETTING_GROUP_BACKUPS, "Maximum archive entries", DEFAULT_MAX_ARCHIVE_ENTRIES,
                                            OptionsValidator([100_000, 500_000, 1_000_000, 2_000_000]))
    search_max_results = OptionsConfigItem(SETTING_GROUP_SEARCH, "Maximum results per snapshot", SnapshotSearchParams.max_results,
                                           OptionsValidator([100, 500, 1_000, 2_500, 5_000, 10_000]))
    search_regex_timeout = OptionsConfigItem(SETTING_GROUP_SEARCH, "Regex timeout seconds", SnapshotSearchParams.regex_timeout_seconds,
                                            OptionsValidator([0.05, 0.1, 0.25, 0.5, 1.0, 2.0]))
    language = OptionsConfigItem(SETTING_GROUP_APP, "Language", DEFAULT_SETTING_LANGUAGE, OptionsValidator(["en", "it"]))



# CARICAMENTO IMPOSTAZIONI
app_settings = AppSettings()
qconfig.load(PATH_JSON_SETTING_FILE, app_settings)

def _optional_directory(value: str) -> Path | None:
    return Path(value) if value else None


def _archive_bytes(gib: int) -> int:
    return gib * BYTES_PER_GIB


def _copy_strategy(key: str):
    return COPY_STRATEGIES[key]()


_snapshot_preferences = {
    "install_with_everyone_full_control": (AppSettings.install_with_everyone_full_control, bool),
    "allow_unverified_legacy_snapshots": (AppSettings.allow_legacy_snapshots, bool),
    "copy_strategy": (AppSettings.copy_strategy, _copy_strategy),
    "copy_metadata_mode": (AppSettings.copy_metadata_mode, CopyMetadataMode),
    "archive_temp_directory": (AppSettings.archive_temp_directory, _optional_directory),
    "max_archive_uncompressed_bytes": (AppSettings.max_archive_gib, _archive_bytes),
    "max_archive_entries": (AppSettings.max_archive_entries, int),
}

snap_settings = SnapshotSettings(
    backup_path=Path(app_settings.get(AppSettings.backup_path)),
    backup_pre_install=app_settings.get(AppSettings.backup_before_install),
    backup_pre_delete=app_settings.get(AppSettings.backup_before_delete),
    backup_pre_modify=app_settings.get(AppSettings.backup_before_edit),
    snap_id_length=20,
    folder_id_length=6,
    **{name: convert(app_settings.get(item)) for name, (item, convert) in _snapshot_preferences.items()},
)


def _apply_snapshot_preference(name, convert, value):
    setattr(snap_settings, name, convert(value))


for name, (item, convert) in _snapshot_preferences.items():
    item.valueChanged.connect(partial(_apply_snapshot_preference, name, convert))
