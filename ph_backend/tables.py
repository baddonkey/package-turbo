"""Generic row/column table model used by the action views and the dossier navigator export."""

from PySide6.QtCore import Property, QAbstractTableModel, QByteArray, QModelIndex, Qt, Signal, Slot

ROW_KEY_ROLE = Qt.ItemDataRole.UserRole + 1
SEVERITY_ROLE = Qt.ItemDataRole.UserRole + 2


class RecordTableModel(QAbstractTableModel):
    countChanged = Signal()
    columnsChanged = Signal()
    sortChanged = Signal()

    def __init__(self, columns: list[tuple[str, str]], parent=None):
        """columns: (record field, header label)."""
        super().__init__(parent)
        self._columns = list(columns)
        self._all: list[dict] = []
        self._rows: list[dict] = []
        self._filter = None
        self._sort_keys: list[tuple[int, bool]] = []
        self._hidden: set[int] = set()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._columns)

    def roleNames(self):
        roles = super().roleNames()
        roles[ROW_KEY_ROLE] = QByteArray(b"rowKey")
        roles[SEVERITY_ROLE] = QByteArray(b"severity")
        return roles

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        record = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return str(record.get(self._columns[index.column()][0], ""))
        if role == ROW_KEY_ROLE:
            return int(record.get("key", 0) or 0)
        if role == SEVERITY_ROLE:
            return record.get("severity", "")
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self._columns[section][1] if 0 <= section < len(self._columns) else None
        return None

    # ---------------------------------------------------------------- content

    def set_columns(self, columns: list[tuple[str, str]]) -> None:
        self.beginResetModel()
        self._columns = list(columns)
        self._sort_keys = []
        self._hidden = set()
        self.endResetModel()
        self.columnsChanged.emit()
        self.sortChanged.emit()

    def set_records(self, records: list[dict]) -> None:
        self.beginResetModel()
        self._all = list(records)
        self._apply_filter()
        self.endResetModel()
        self.countChanged.emit()

    def append(self, record: dict) -> None:
        self._all.append(record)
        if self._filter is None or self._filter(record):
            self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
            self._rows.append(record)
            self.endInsertRows()
        self.countChanged.emit()

    def set_filter(self, predicate) -> None:
        self.beginResetModel()
        self._filter = predicate
        self._apply_filter()
        self.endResetModel()
        self.countChanged.emit()

    def _apply_filter(self) -> None:
        self._rows = [r for r in self._all if self._filter is None or self._filter(r)]
        self._apply_sort()

    def records(self) -> list[dict]:
        return list(self._all)

    def visible_records(self) -> list[dict]:
        return list(self._rows)

    @Slot(int, result="QVariantMap")
    def recordAt(self, row: int) -> dict:
        return dict(self._rows[row]) if 0 <= row < len(self._rows) else {}

    @Slot(int, result=int)
    def rowOfKey(self, key: int) -> int:
        return next((i for i, r in enumerate(self._rows) if r.get("key") == key), -1)

    @Slot(result=int)
    def totalCount(self) -> int:
        return len(self._all)

    total = Property(int, totalCount, notify=countChanged)

    @Slot(result=int)
    def visibleCount(self) -> int:
        return len(self._rows)

    # ---------------------------------------------------------------- export

    def _visible_columns(self):
        return [(f, label) for i, (f, label) in enumerate(self._columns) if i not in self._hidden]

    @Slot(result=str)
    def toTsv(self) -> str:
        return self.rowsToTsv(list(range(len(self._rows))))

    @Slot("QVariantList", result=str)
    def rowsToTsv(self, rows) -> str:
        columns = self._visible_columns()
        lines = ["\t".join(label for _, label in columns)]
        for row in sorted(int(r) for r in rows):
            if 0 <= row < len(self._rows):
                record = self._rows[row]
                lines.append("\t".join(str(record.get(f, "")).replace("\t", " ").replace("\n", " ")
                                       for f, _ in columns))
        return "\n".join(lines)

    # ---------------------------------------------------------------- columns

    @Slot(result="QVariantList")
    def columnLabels(self) -> list:
        return [label for _, label in self._columns]

    @Slot(int, result=bool)
    def isColumnVisible(self, column: int) -> bool:
        return column not in self._hidden

    @Slot(int, bool)
    def setColumnVisible(self, column: int, visible: bool) -> None:
        if visible:
            self._hidden.discard(column)
        elif len(self._hidden) < len(self._columns) - 1:
            self._hidden.add(column)
        self.columnsChanged.emit()

    # ---------------------------------------------------------------- sorting (chapter 17)

    def _apply_sort(self) -> None:
        for column, descending in reversed(self._sort_keys):
            if column < len(self._columns):
                field = self._columns[column][0]
                self._rows.sort(key=lambda r: _sort_value(r.get(field, "")), reverse=descending)

    def _resort(self) -> None:
        self.layoutAboutToBeChanged.emit()
        self._apply_sort()
        self.layoutChanged.emit()
        self.sortChanged.emit()

    @Slot(int, str)
    def sortClick(self, column: int, modifier: str) -> None:
        """Click toggles/adds a sort column, 'alt' removes it, 'ctrl'/'shift' lower/raise its priority."""
        position = next((i for i, (c, _) in enumerate(self._sort_keys) if c == column), -1)
        if modifier == "alt":
            if position >= 0:
                self._sort_keys.pop(position)
        elif modifier in ("ctrl", "shift") and position >= 0:
            target = position + (1 if modifier == "ctrl" else -1)
            if 0 <= target < len(self._sort_keys):
                keys = self._sort_keys
                keys[position], keys[target] = keys[target], keys[position]
        elif position >= 0:
            c, descending = self._sort_keys[position]
            self._sort_keys[position] = (c, not descending)
        else:
            self._sort_keys.append((column, False))
        self._resort()

    @Slot(int, result=str)
    def sortIndicator(self, column: int) -> str:
        for priority, (c, descending) in enumerate(self._sort_keys, start=1):
            if c == column:
                arrow = "\u25BC" if descending else "\u25B2"
                return f"{arrow}{priority if len(self._sort_keys) > 1 else ''}"
        return ""

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        self._sort_keys = [(column, order == Qt.SortOrder.DescendingOrder)]
        self._resort()


def _sort_value(value):
    text = str(value)
    return (0, float(text), "") if text.replace(".", "", 1).isdigit() else (1, 0.0, text.lower())
