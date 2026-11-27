from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFileDialog, QVBoxLayout
from pylizlib.qtfw.widgets.card import MasterListSettingCard
from qfluentwidgets import PushSettingCard, FluentIcon, PushButton, SwitchSettingCard, OptionsSettingCard, ToolTipFilter, ToolTipPosition

from snappy.application.app import app, app_settings, AppSettings
from snappy.view.util.frame import SnappyQFrame
from snappy.view.util.setting import ComboSettingCard, SettingGroupManager
from snappy.application.i18n import tr


class WidgetSettings(SnappyQFrame):
    """
    The main settings view of the application.
    Displays various configuration options grouped by categories such as Snapshots, Backups,
    Favorites, Application, and Information.
    Emits signals when the user interacts with actionable settings (e.g., changing paths).
    """

    signal_open_dir_request = Signal()
    signal_close_and_clear_request = Signal()
    signal_open_about_dialog_request = Signal()
    signal_request_update = Signal()
    signal_ask_catalogue_path = Signal()
    signal_open_tags_dialog = Signal()
    signal_clear_backups_request = Signal()
    signal_ask_backup_path = Signal()
    signal_language_changed = Signal()
    signal_theme_changed = Signal()

    def __init__(self, parent=None):
        """
        Initializes the WidgetSettings view.

        Args:
            parent (QWidget, optional): The parent widget. Defaults to None.
        """
        super().__init__(
            name=tr("Settings"), 
            parent=parent, 
            subtitle=tr("Configure the application preferences and default behaviors.")
        )
        self.layout = self.get_scroll_layout()
        self.install_label_title()

        # Aggiungo i widgets
        self.__add_groups(self.get_scroll_layout())

        # Installo lo scroll nel layout principale
        self.install_scroll_on(self.master_layout)



    def update_catalogue_path(self, path: str):
        """
        Updates the displayed catalogue path on the UI.
        
        Args:
            path (str): The new catalogue path.
        """
        self.card_general_catalogue.setContent(path)

    def update_backup_path(self, path: str):
        """
        Updates the displayed backup path on the UI.
        
        Args:
            path (str): The new backup path.
        """
        self.card_backup_path.setContent(path)

    def __install_tooltip(self, widget, text):
        """
        Installs a tooltip with a specified delay and position on a given widget.

        Args:
            widget (QWidget): The widget to apply the tooltip to.
            text (str): The text content of the tooltip.
        """
        widget.setToolTip(text)
        widget.installEventFilter(ToolTipFilter(widget, 2500, ToolTipPosition.TOP))

    def __add_groups(self, layout: QVBoxLayout):
        """
        Adds all setting groups to the main layout.

        Args:
            layout (QVBoxLayout): The target layout where setting groups will be appended.
        """
        self.__add_group_snapshot(layout)
        self.__add_group_backups(layout)
        self.__add_group_search(layout)
        self.__add_group_favorites(layout)
        self.__add_group_app(layout)
        self.__add_group_info(layout)

    def __add_group_snapshot(self, layout: QVBoxLayout):
        """
        Builds and adds the 'Snapshots' setting group to the layout.
        This includes catalogue path, configuration tags, custom variables, and cleanup settings.

        Args:
            layout (QVBoxLayout): The layout to append the group to.
        """

        # Percorso catalogo generale
        setting_catalogue = AppSettings.catalogue_path
        self.card_general_catalogue = PushSettingCard(
            text=tr("Choose directory"),
            icon=FluentIcon.BOOK_SHELF,
            title=tr("Catalogue path"),
            content=app_settings.get(setting_catalogue)
        )

        # Tag configurazioni
        setting_tags = AppSettings.config_tags
        self.card_fav_tags = MasterListSettingCard(
            config_item=setting_tags,
            item_type=MasterListSettingCard.Type.TEXT,
            card_title=tr("Configuration tags"),
            card_icon=FluentIcon.TAG,
            main_btn=PushButton(tr("Add tag"), self),
            card_content=tr("Add one or more tags to assign to configurations"),
            parent=self if setting_tags.enabled else None,
            dialog_title=tr("Add tag"),
            dialog_content=tr("Enter the tag name"),
            dialog_button_yes=tr("Add"),
            dialog_button_no=tr("Cancel"),
            dialog_error=tr("The tag cannot be empty or already existing"),
            deletion_title=tr("Confirm deletion"),
            deletion_content=tr("Are you sure you want to delete this tag?")
        )

        # custom data snapshots
        setting_custom_data = AppSettings.snap_custom_data
        self.card_snap_custom_data = MasterListSettingCard(
            config_item=setting_custom_data,
            item_type=MasterListSettingCard.Type.TEXT,
            card_title=tr("Snapshots - Custom data"),
            card_icon=FluentIcon.QUICK_NOTE,
            main_btn=PushButton(tr("Add variable"), self),
            card_content=tr("Add one or more custom variables to assign to snapshots"),
            parent=self if setting_custom_data.enabled else None,
            dialog_title=tr("Add variable"),
            dialog_content=tr("Enter the variable name"),
            dialog_button_yes=tr("Add"),
            dialog_button_no=tr("Cancel"),
            dialog_error=tr("The variable cannot be empty or already existing"),
            deletion_title=tr("Confirm deletion"),
            deletion_content=tr("Are you sure you want to delete this variable?")
        )

        # Cancellazione cartelle allegate prima dell'installazione
        setting_clear_snap_attached_folders_before_install = AppSettings.clear_snap_attached_folders_before_install
        self.card_clear_snap_attached_folders_before_install = SwitchSettingCard(
            icon=FluentIcon.BASKETBALL,
            title=tr("Clear attached folders before installation"),
            content=tr("Before installing a configuration, clear the local attached folders (on this PC)"),
            configItem=setting_clear_snap_attached_folders_before_install
        )

        self.__install_tooltip(self.card_general_catalogue, tr("Select the main catalogue directory for configurations"))
        self.__install_tooltip(self.card_fav_tags, tr("Manage the tags available for your configurations"))
        self.__install_tooltip(self.card_snap_custom_data, tr("Define custom variables to be used within snapshots"))
        self.__install_tooltip(self.card_clear_snap_attached_folders_before_install, tr("Automatically clean up local folders attached to a snapshot before installing it"))

        grp_manager = SettingGroupManager(tr("Snapshots"), self)
        grp_manager.add_widget(setting_catalogue, self.card_general_catalogue, self.signal_ask_catalogue_path)
        grp_manager.add_widget(setting_tags, self.card_fav_tags, None)
        grp_manager.add_widget(setting_custom_data, self.card_snap_custom_data, None)
        grp_manager.add_widget(setting_clear_snap_attached_folders_before_install, self.card_clear_snap_attached_folders_before_install, None)
        setting_permissions = AppSettings.install_with_everyone_full_control
        self.card_install_with_everyone_full_control = SwitchSettingCard(
            icon=FluentIcon.SETTING,
            title=tr("Grant Everyone full control"),
            content=tr("On Windows, grant Everyone full control of installed folders and their contents."),
            configItem=setting_permissions,
        )
        grp_manager.add_widget(setting_permissions, self.card_install_with_everyone_full_control, None)
        self.card_copy_strategy = ComboSettingCard(
            AppSettings.copy_strategy, FluentIcon.COPY, tr("Copy strategy"),
            tr("Verified copies retry when the source changes during copying."),
            {"standard": tr("Standard"), "verified": tr("Verified")}.__getitem__,
        )
        self.card_copy_metadata = ComboSettingCard(
            AppSettings.copy_metadata_mode, FluentIcon.COPY, tr("Metadata to preserve"),
            tr("Extended mode also preserves additional filesystem metadata where supported."),
            {"basic": tr("Basic"), "extended": tr("Extended")}.__getitem__,
        )
        self.card_allow_legacy_snapshots = SwitchSettingCard(
            icon=FluentIcon.FOLDER, title=tr("Allow legacy snapshots"),
            content=tr("Allow installation of older snapshots that lack an integrity manifest."),
            configItem=AppSettings.allow_legacy_snapshots,
        )
        grp_manager.add_widget(None, self.card_copy_strategy, None)
        grp_manager.add_widget(None, self.card_copy_metadata, None)
        grp_manager.add_widget(AppSettings.allow_legacy_snapshots, self.card_allow_legacy_snapshots, None)
        grp_manager.install_group_on(layout)


    def __add_group_backups(self, layout: QVBoxLayout):
        """
        Builds and adds the 'Backups' setting group to the layout.
        This includes the backup path, toggles for various automatic backups, and a clear backups action.

        Args:
            layout (QVBoxLayout): The layout to append the group to.
        """

        # Percorso backup
        setting_backup_path = AppSettings.backup_path
        self.card_backup_path = PushSettingCard(
            text=tr("Choose directory"),
            icon=FluentIcon.SAVE,
            title=tr("Backup path"),
            content=app_settings.get(setting_backup_path)
        )

        # Backup pre-installazione
        setting_backup_before_install = AppSettings.backup_before_install
        self.card_backup_before_install = SwitchSettingCard(
            icon=FluentIcon.SAVE,
            title=tr("Enable pre-installation backup"),
            content=tr("Backup local folders (on this PC) contained in the configuration before installing it"),
            configItem=setting_backup_before_install
        )

        # Backup pre-modifica
        setting_backup_before_edit = AppSettings.backup_before_edit
        self.card_backup_before_edit = SwitchSettingCard(
            icon=FluentIcon.SAVE,
            title=tr("Enable pre-edit backup"),
            content=tr("Backup local folders (on this PC) contained in the configuration before editing them"),
            configItem=setting_backup_before_edit
        )

        # Backup pre-eliminazione
        setting_backup_before_delete = AppSettings.backup_before_delete
        self.card_backup_before_delete = SwitchSettingCard(
            icon=FluentIcon.SAVE,
            title=tr("Enable pre-deletion backup"),
            content=tr("Backup local folders (on this PC) contained in the configuration before deleting them"),
            configItem=setting_backup_before_delete
        )

        # Cancella backups
        self.card_clear_backups = PushSettingCard(
            text=tr("Clear backups"),
            icon=FluentIcon.DELETE,
            title=tr("Clear Backups of {name}", name=app.name),
            content=tr("This operation will delete all backup files created by the application.")
        )

        self.__install_tooltip(self.card_backup_path, tr("Choose the directory where your backups will be saved"))
        self.__install_tooltip(self.card_backup_before_install, tr("Enable or disable automatic backup before installing a configuration"))
        self.__install_tooltip(self.card_backup_before_edit, tr("Enable or disable automatic backup before editing a configuration"))
        self.__install_tooltip(self.card_backup_before_delete, tr("Enable or disable automatic backup before deleting a configuration"))
        self.__install_tooltip(self.card_clear_backups, tr("Permanently delete all application backups to free up space"))

        grp_manager = SettingGroupManager(tr("Backups"), self)
        grp_manager.add_widget(setting_backup_path, self.card_backup_path, self.signal_ask_backup_path)
        self.card_archive_temp = PushSettingCard(
            text=tr("Choose directory"), icon=FluentIcon.FOLDER, title=tr("Temporary archive directory"),
            content=app_settings.get(AppSettings.archive_temp_directory) or tr("Automatic location"),
        )
        self.reset_archive_temp = PushButton(tr("Use automatic location"), self.card_archive_temp)
        self.card_archive_temp.hBoxLayout.insertWidget(self.card_archive_temp.hBoxLayout.count() - 1, self.reset_archive_temp)
        self.card_archive_temp.hBoxLayout.insertSpacing(self.card_archive_temp.hBoxLayout.count() - 1, 16)
        self.reset_archive_temp.setEnabled(bool(app_settings.get(AppSettings.archive_temp_directory)))
        self.reset_archive_temp.clicked.connect(lambda: app_settings.set(AppSettings.archive_temp_directory, ""))
        self.card_archive_temp.clicked.connect(self.__choose_archive_temp_directory)
        AppSettings.archive_temp_directory.valueChanged.connect(self.__show_archive_temp_directory)

        self.card_archive_size = ComboSettingCard(
            AppSettings.max_archive_gib, FluentIcon.SAVE, tr("Maximum expanded archive size"),
            tr("Maximum total uncompressed size in a snapshot archive."), lambda value: f"{value} GiB",
        )
        self.card_archive_entries = ComboSettingCard(
            AppSettings.max_archive_entries, FluentIcon.SAVE, tr("Maximum archive entries"),
            tr("Maximum number of files, folders and metadata entries in a snapshot archive."),
            lambda value: f"{value:,}",
        )
        grp_manager.add_widget(AppSettings.archive_temp_directory, self.card_archive_temp, None)
        grp_manager.add_widget(None, self.card_archive_size, None)
        grp_manager.add_widget(None, self.card_archive_entries, None)
        grp_manager.add_widget(setting_backup_before_install, self.card_backup_before_install, None)
        grp_manager.add_widget(setting_backup_before_edit, self.card_backup_before_edit, None)
        grp_manager.add_widget(setting_backup_before_delete, self.card_backup_before_delete, None)
        grp_manager.add_widget(None, self.card_clear_backups, self.signal_clear_backups_request)
        grp_manager.install_group_on(layout)

    def __choose_archive_temp_directory(self):
        current = app_settings.get(AppSettings.archive_temp_directory)
        directory = QFileDialog.getExistingDirectory(self, tr("Select the temporary archive directory"), current)
        if directory:
            app_settings.set(AppSettings.archive_temp_directory, directory)

    def __show_archive_temp_directory(self, directory: str):
        self.card_archive_temp.setContent(directory or tr("Automatic location"))
        self.reset_archive_temp.setEnabled(bool(directory))

    def __add_group_search(self, layout: QVBoxLayout):
        group = SettingGroupManager(tr("Search settings"), self)
        self.card_search_max_results = ComboSettingCard(
            AppSettings.search_max_results, FluentIcon.SEARCH, tr("Maximum results per snapshot"),
            tr("Maximum number of matches displayed for each snapshot."), lambda value: f"{value:,}",
        )
        self.card_search_regex_timeout = ComboSettingCard(
            AppSettings.search_regex_timeout, FluentIcon.SEARCH, tr("Regex timeout"),
            tr("Time allowed for each regular-expression match operation."), lambda value: f"{value:g} s",
        )
        group.add_widget(None, self.card_search_max_results, None)
        group.add_widget(None, self.card_search_regex_timeout, None)
        group.install_group_on(layout)

    def __add_group_favorites(self, layout: QVBoxLayout):
        """
        Builds and adds the 'Favorites' setting group to the layout.
        This allows users to manage their starred folders and files.

        Args:
            layout (QVBoxLayout): The layout to append the group to.
        """

        # Cartelle preferite
        setting_fav_dirs = AppSettings.starred_dirs
        self.card_fav_dirs = MasterListSettingCard(
            config_item=setting_fav_dirs,
            item_type=MasterListSettingCard.Type.FOLDER,
            card_title=tr("Starred folders"),
            card_icon=FluentIcon.FOLDER,
            main_btn=PushButton(tr("Add folder"), self),
            card_content=tr("Add one or more starred folders"),
            parent=self if setting_fav_dirs.enabled else None,
            dialog_title=tr("Select folder"),
        )

        # File preferite
        setting_fav_files = AppSettings.starred_files
        self.card_fav_files = MasterListSettingCard(
            config_item=setting_fav_files,
            item_type=MasterListSettingCard.Type.FILE,
            card_title=tr("Starred files"),
            card_icon=FluentIcon.DOCUMENT,
            main_btn=PushButton(tr("Add file"), self),
            card_content=tr("Add one or more starred files"),
            parent=self if setting_fav_files.enabled else None,
            dialog_title=tr("Select file"),
            dialog_file_filter=tr("All Files (*.*)")
        )

        # Eseguibili e servizi sono disabilitati nell'interfaccia.
        # setting_fav_exe = AppSettings.starred_exes
        # self.card_fav_exes = MasterListSettingCard(
        #     config_item=setting_fav_exe,
        #     item_type=MasterListSettingCard.Type.FILE,
        #     card_title=tr("Starred executables"),
        #     card_icon=FluentIcon.APPLICATION,
        #     main_btn=PushButton(tr("Choose an executable"), self),
        #     card_content=tr("Add one or more starred executables to monitor on the home screen"),
        #     parent=self if setting_fav_exe.enabled else None,
        #     dialog_title=tr("Select executable"),
        #     dialog_file_filter=tr("Executable Files (*.exe);;All Files (*.*)"),
        # )
        # setting_fav_services = AppSettings.starred_services
        # self.card_fav_services = MasterListSettingCard(
        #     config_item=setting_fav_services,
        #     item_type=MasterListSettingCard.Type.TEXT,
        #     card_title=tr("Starred services"),
        #     card_icon=FluentIcon.SETTING,
        #     main_btn=PushButton(tr("Add service"), self),
        #     card_content=tr("Add one or more Windows services to monitor on the home screen"),
        #     parent=self if setting_fav_services.enabled else None,
        #     dialog_title=tr("Add service"),
        #     dialog_content=tr("Enter the Windows service name (e.g. Spooler)"),
        #     dialog_button_yes=tr("Add"),
        #     dialog_button_no=tr("Cancel"),
        #     dialog_error=tr("The service name cannot be empty or already existing"),
        #     deletion_title=tr("Confirm deletion"),
        #     deletion_content=tr("Are you sure you want to delete this service?"),
        # )

        self.__install_tooltip(self.card_fav_dirs, tr("Manage your favorite folders for quick access"))
        self.__install_tooltip(self.card_fav_files, tr("Manage your favorite files for quick access"))
        # self.__install_tooltip(self.card_fav_exes, tr("Manage your favorite executables to monitor their status"))
        # self.__install_tooltip(self.card_fav_services, tr("Manage the Windows services you want to monitor"))

        grp_manager = SettingGroupManager(tr("Favorites"), self)
        grp_manager.add_widget(setting_fav_dirs, self.card_fav_dirs, None)
        grp_manager.add_widget(setting_fav_files, self.card_fav_files, None)
        # grp_manager.add_widget(setting_fav_exe, self.card_fav_exes, None)
        # grp_manager.add_widget(setting_fav_services, self.card_fav_services, None)
        grp_manager.install_group_on(layout)


    def __add_group_app(self, layout: QVBoxLayout):
        """
        Builds and adds the 'Application' setting group to the layout.
        This includes UI themes, language selection, and an action to open the working folder.

        Args:
            layout (QVBoxLayout): The layout to append the group to.
        """

        # Directory di lavoro
        self.card_working_folder = PushSettingCard(
            text=tr("Open Folder"),
            icon=FluentIcon.FOLDER,
            title=tr("Working folder of {name}", name=app.name),
            content=app.path.__str__()
        )

        # Tema applicazione
        self.card_theme = OptionsSettingCard(
            AppSettings.themeMode,
            icon=FluentIcon.BRUSH,
            title=tr("Application theme"),
            content=tr("Select the application theme"),
            texts=[tr(mode.value) for mode in AppSettings.themeMode.options],
        )
        self.card_theme.optionChanged.connect(lambda: self.signal_theme_changed.emit())

        # Lingua applicazione
        self.card_language = OptionsSettingCard(
            AppSettings.language,
            icon=FluentIcon.LANGUAGE,
            title=tr("Language"),
            content=tr("Select the application language"),
            texts=[tr("English"), tr("Italian")],
        )
        self.card_language.optionChanged.connect(lambda: self.signal_language_changed.emit())

        self.__install_tooltip(self.card_working_folder, tr("Open the current working folder of the application"))
        self.__install_tooltip(self.card_theme, tr("Change the visual appearance of the application"))
        self.__install_tooltip(self.card_language, tr("Change the display language of the application"))

        grp_manager = SettingGroupManager(tr("Application"), self)
        grp_manager.add_widget(None, self.card_working_folder, self.signal_open_dir_request)
        grp_manager.add_widget(None, self.card_theme, None)
        grp_manager.add_widget(None, self.card_language, None)
        grp_manager.install_group_on(layout)

    def __add_group_info(self, layout: QVBoxLayout):
        """
        Builds and adds the 'Information' setting group to the layout.
        This includes a card that triggers the application's About dialog.

        Args:
            layout (QVBoxLayout): The layout to append the group to.
        """

        # Informazioni applicazione
        self.card_info_app = PushSettingCard(
            text=tr("Information"),
            icon=FluentIcon.APPLICATION,
            title=tr("About {name}", name=app.name),
            content=app.version
        )

        self.__install_tooltip(self.card_info_app, tr("View information about the application version"))

        grp_manager = SettingGroupManager(tr("Information"), self)
        grp_manager.add_widget(None, self.card_info_app, self.signal_open_about_dialog_request)
        grp_manager.install_group_on(layout)
