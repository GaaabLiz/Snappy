from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from pylizlib.core.data.unit import get_normalized_gb_mb_str
from pylizlib.core.os.snap import Snapshot, SnapshotCatalogueStatistics, SnapshotSortKey
from pylizlib.core.os.snap.sorting import sort_snapshots

from snappy.application.app import app_settings, AppSettings
from snappy.application.i18n import tr


class SnapshotTableModel(QAbstractTableModel):
    """
    A table model for displaying Snapshot data in a QTableView.
    """

    def __init__(self, parent=None):
        """
        Initializes the SnapshotTableModel.

        Args:
            parent: The parent QObject, optional.
        """
        super().__init__(parent)
        self._snapshots: list[Snapshot] = []
        self._headers = []
        self.update_headers()

    def update_headers(self):
        """
        Updates the headers based on application settings.
        Dynamically appends any custom snapshot data keys to the header list.
        """
        headers = [tr("Name"), tr("Description")]
        snap_custom_data = app_settings.get(AppSettings.snap_custom_data)
        for i in snap_custom_data:
            headers.append(i)
        headers.append(tr("Size"))
        headers.append(tr("Date/Time"))
        headers.append(tr("Tags"))
        headers.append(tr("Author"))
        self._headers = headers
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(self._headers) - 1)

    def rowCount(self, parent=QModelIndex()) -> int:
        """
        Returns the number of rows in the table model.

        Args:
            parent (QModelIndex, optional): The parent model index. Defaults to QModelIndex().

        Returns:
            int: The number of rows.
        """
        if parent.isValid():
            return 0
        return len(self._snapshots)

    def columnCount(self, parent=QModelIndex()) -> int:
        """
        Returns the number of columns in the table model.

        Args:
            parent (QModelIndex, optional): The parent model index. Defaults to QModelIndex().

        Returns:
            int: The number of columns.
        """
        if parent.isValid():
            return 0
        return len(self._headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """
        Retrieves the data for a specific index and role.

        Args:
            index (QModelIndex): The index of the item.
            role (Qt.ItemDataRole, optional): The role for which data is requested. Defaults to Qt.ItemDataRole.DisplayRole.

        Returns:
            Any: The data at the specified index and role, or None if not applicable.
        """
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None

        try:
            snapshot = self._snapshots[index.row()]
            snap_custom_data_keys = app_settings.get(AppSettings.snap_custom_data)
            table_data = snapshot.get_for_table_array(snap_custom_data_keys)
            
            tags = table_data.pop()
            date = table_data.pop()
            
            author = snapshot.author
            size = f"{snapshot.get_assoc_dir_mb_size:.2f} MB"
            
            table_data.append(size)
            table_data.append(date)
            table_data.append(tags)
            table_data.append(author)
            
            return str(table_data[index.column()])
        except (IndexError, KeyError):
            return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """
        Retrieves the header data for a specific section and orientation.

        Args:
            section (int): The section index (column or row number).
            orientation (Qt.Orientation): The orientation of the header.
            role (Qt.ItemDataRole, optional): The role for which data is requested. Defaults to Qt.ItemDataRole.DisplayRole.

        Returns:
            Any: The header data, or None if not applicable.
        """
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            try:
                return self._headers[section]
            except IndexError:
                return None
        return None

    def set_snapshots(self, snapshots: list[Snapshot]):
        """
        Resets the model with a new list of snapshots.

        Args:
            snapshots (list[Snapshot]): The list of snapshots to display.
        """
        self.beginResetModel()
        self._snapshots = snapshots if snapshots is not None else []
        self.endResetModel()

    def get_snapshot(self, row: int) -> Snapshot | None:
        """
        Returns the snapshot at a given row.

        Args:
            row (int): The row index.

        Returns:
            Snapshot | None: The snapshot at the given row, or None if the row is invalid.
        """
        try:
            return self._snapshots[row]
        except IndexError:
            return None


class CatalogueModel:
    """
    Manages the data and business logic for the snapshot catalogue.
    """

    def __init__(self):
        """
        Initializes the CatalogueModel and its underlying table model.
        """
        self._all_snapshots: list[Snapshot] = []
        self._filtered_snapshots: list[Snapshot] = []
        self._is_filtered = False
        self._filter_text = ""
        self._sort_key = SnapshotSortKey.NAME
        self._sort_reverse = False
        self._statistics: SnapshotCatalogueStatistics | None = None
        self.table_model = SnapshotTableModel()

    def set_snapshots(self, snapshots: list[Snapshot] | None, statistics: SnapshotCatalogueStatistics | None = None):
        """
        Sets the master list of snapshots and updates the table view.

        Args:
            snapshots (list[Snapshot] | None): The snapshots to manage, or None to clear the list.
            statistics (SnapshotCatalogueStatistics | None): Totals for the whole catalogue.
        """
        self._statistics = statistics
        self._all_snapshots = snapshots if snapshots is not None else []
        self._all_snapshots = sort_snapshots(
            self._all_snapshots, self._sort_key, reverse=self._sort_reverse
        )
        self.filter(self._filter_text)

    def get_snapshot_at(self, row: int) -> Snapshot | None:
        """
        Gets the snapshot at a specific row of the current view (filtered or not).

        Args:
            row (int): The row index.

        Returns:
            Snapshot | None: The requested snapshot, or None if the row is invalid.
        """
        return self.table_model.get_snapshot(row)

    def sort(self, sort_key: SnapshotSortKey, reverse: bool = False):
        """
        Sorts the master list of snapshots and updates the view.

        Args:
            sort_key (SnapshotSortKey): The key by which to sort the snapshots.
            reverse (bool, optional): Whether to reverse the sort order. Defaults to False.
        """
        self._sort_key = sort_key
        self._sort_reverse = reverse
        self._all_snapshots = sort_snapshots(self._all_snapshots, sort_key, reverse=reverse)
        self.filter(self._filter_text)

    def filter(self, text: str):
        """
        Filters snapshots based on a text query and updates the view.

        Args:
            text (str): The search query to filter snapshots by.
        """
        text = text.lower().strip()
        self._filter_text = text
        if not text:
            self._is_filtered = False
            self._filtered_snapshots = []
            self.table_model.set_snapshots(self._all_snapshots)
        else:
            self._is_filtered = True
            self._filtered_snapshots = [
                config for config in self._all_snapshots
                if (text in config.name.lower() or
                    text in config.desc.lower() or
                    any(text in tag.lower() for tag in config.tags) or
                    (config.data and any(text in str(value).lower() for value in config.data.values())))
            ]
            self.table_model.set_snapshots(self._filtered_snapshots)

    def count(self) -> int:
        """Return the total number of snapshots in the catalogue."""
        if self._statistics is not None:
            return self._statistics.snapshot_count
        return len(self._all_snapshots)

    def get_mb_size(self) -> str:
        """Format the total captured size of the catalogue when available."""
        if self._statistics is None:
            return "—"
        return get_normalized_gb_mb_str(self._statistics.total_size_bytes)
