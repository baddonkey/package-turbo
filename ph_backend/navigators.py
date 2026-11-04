"""Tree models for the three navigators: classification system, dossiers and package (file system)."""

from pathlib import PurePosixPath

from PySide6.QtCore import QByteArray, QModelIndex, QPersistentModelIndex, Qt, Signal, Slot
from PySide6.QtGui import QStandardItem, QStandardItemModel

from . import notes, timespan
from .sip import SipPackage

KEY_ROLE = Qt.ItemDataRole.UserRole + 1
KIND_ROLE = Qt.ItemDataRole.UserRole + 2
FLAG_ROLE = Qt.ItemDataRole.UserRole + 3
# Mirrors DisplayRole; QML button delegates already own a 'display' property.
LABEL_ROLE = Qt.ItemDataRole.UserRole + 4
OWNER_ROLE = Qt.ItemDataRole.UserRole + 5
NOTE_ROLE = Qt.ItemDataRole.UserRole + 6

CLASSIFICATION_FILTERS = ("all", "main_groups", "positions", "positions_with_dossiers", "empty_dossiers")
PACKAGE_FILTERS = ("all", "unassigned")
_CONTENT_KINDS = ("subdossier", "dokument", "vorgang", "aktivitaet", "mappe")


class NavigatorModel(QStandardItemModel):
    rebuilt = Signal()

    def __init__(self, headers: list[str], parent=None):
        super().__init__(parent)
        self._headers = headers
        self._items: dict[int, QStandardItem] = {}
        self._note_keys: set[int] = set()
        self.setHorizontalHeaderLabels(headers)

    def roleNames(self):
        roles = super().roleNames()
        roles[KEY_ROLE] = QByteArray(b"elementKey")
        roles[KIND_ROLE] = QByteArray(b"kind")
        roles[FLAG_ROLE] = QByteArray(b"flag")
        roles[LABEL_ROLE] = QByteArray(b"label")
        roles[OWNER_ROLE] = QByteArray(b"ownerKey")
        roles[NOTE_ROLE] = QByteArray(b"hasNote")
        return roles

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == LABEL_ROLE:
            role = Qt.ItemDataRole.DisplayRole
        return super().data(index, role)

    def reset(self, pkg: SipPackage | None = None) -> None:
        self.clear()
        self._items.clear()
        self._note_keys = notes.owners_with_notes(pkg) if pkg is not None else set()
        self.setHorizontalHeaderLabels(self._headers)

    def make_item(self, text: str, key: int, kind: str, flag: str = "", owner: int = 0) -> QStandardItem:
        item = QStandardItem(text)
        item.setEditable(False)
        item.setData(key, KEY_ROLE)
        item.setData(kind, KIND_ROLE)
        item.setData(flag, FLAG_ROLE)
        item.setData(owner, OWNER_ROLE)
        item.setData(key in self._note_keys, NOTE_ROLE)
        self._items.setdefault(key, item)
        return item

    def make_row(self, first: QStandardItem, extra: list[str]) -> list[QStandardItem]:
        row = [first]
        for text in extra:
            cell = QStandardItem(text)
            cell.setEditable(False)
            for role in (KEY_ROLE, KIND_ROLE, OWNER_ROLE):
                cell.setData(first.data(role), role)
            cell.setData(False, NOTE_ROLE)
            row.append(cell)
        return row

    @Slot(int, result=QModelIndex)
    def indexOfKey(self, key: int) -> QModelIndex:
        item = self._items.get(int(key))
        return self.indexFromItem(item) if item is not None else QModelIndex()

    @Slot(QModelIndex, result=int)
    def keyAt(self, index) -> int:
        if isinstance(index, QPersistentModelIndex):
            index = QModelIndex(index)
        return int(index.data(KEY_ROLE) or 0) if index.isValid() else 0

    @Slot(QModelIndex, result=int)
    def ownerAt(self, index) -> int:
        if isinstance(index, QPersistentModelIndex):
            index = QModelIndex(index)
        return int(index.data(OWNER_ROLE) or 0) if index.isValid() else 0

    @Slot(QModelIndex, result=str)
    def kindAt(self, index) -> str:
        if isinstance(index, QPersistentModelIndex):
            index = QModelIndex(index)
        return str(index.data(KIND_ROLE) or "") if index.isValid() else ""

    @Slot(result=int)
    def itemCount(self) -> int:
        return len(self._items)

    @Slot("QVariantList", result=str)
    def rowsToTsv(self, indexes) -> str:
        """Selected rows (all columns) as tab separated text for the clipboard."""
        lines = ["\t".join(self._headers)]
        for index in indexes:
            if isinstance(index, QPersistentModelIndex):
                index = QModelIndex(index)
            if not index.isValid():
                continue
            cells = [str(self.index(index.row(), c, index.parent()).data() or "") for c in range(self.columnCount())]
            lines.append("\t".join(cells))
        return "\n".join(lines)

    def update_label(self, key: int, text: str) -> None:
        item = self._items.get(key)
        if item is not None and item.text() != text:
            item.setText(text)
            index = self.indexFromItem(item)
            self.dataChanged.emit(index, index, [LABEL_ROLE])


def _has_files(pkg: SipPackage, el) -> bool:
    if pkg.children(el, "dateiRef"):
        return True
    return any(_has_files(pkg, c) for c in pkg.children(el) if pkg.kind(c) in ("subdossier", "dokument", "mappe"))


def _contains_dossiers(pkg: SipPackage, position) -> bool:
    return bool(pkg.children(position, "dossier")) or any(
        _contains_dossiers(pkg, p) for p in pkg.children(position, "ordnungssystemposition")
    )


def _contains_empty_dossier(pkg: SipPackage, el) -> bool:
    for dossier in pkg.children(el, "dossier"):
        if not _has_files(pkg, dossier) or _contains_empty_dossier(pkg, dossier):
            return True
    return any(_contains_empty_dossier(pkg, p) for p in pkg.children(el, "ordnungssystemposition"))


def _add_files(model: NavigatorModel, pkg: SipPackage, parent: QStandardItem, el) -> None:
    for file_el in pkg.referenced_files(el):
        parent.appendRow(model.make_item(pkg.display_name(file_el), pkg.key(file_el), "datei", owner=pkg.key(el)))


def _add_content(model: NavigatorModel, pkg: SipPackage, parent: QStandardItem, el, empty_only: bool) -> None:
    for c in pkg.children(el):
        kind = pkg.kind(c)
        if kind == "subdossier":
            if empty_only and _has_files(pkg, c) and not _contains_empty_dossier(pkg, c):
                continue
        elif kind not in _CONTENT_KINDS or empty_only:
            continue
        item = model.make_item(pkg.display_name(c), pkg.key(c), kind)
        parent.appendRow(item)
        _add_content(model, pkg, item, c, empty_only)
    if not empty_only:
        _add_files(model, pkg, parent, el)


def build_classification_tree(model: NavigatorModel, pkg: SipPackage | None, mode: str = "all") -> None:
    model.reset(pkg)
    if pkg is None or pkg.classification_system is None:
        model.rebuilt.emit()
        return
    system = pkg.classification_system
    root = model.make_item(pkg.display_name(system), pkg.key(system), "ordnungssystem")
    model.appendRow(root)
    empty_only = mode == "empty_dossiers"

    def add_folders(parent: QStandardItem, el) -> None:
        if mode in ("all",):
            for folder in pkg.children(el, "mappe"):
                item = model.make_item(pkg.display_name(folder), pkg.key(folder), "mappe")
                parent.appendRow(item)
                _add_content(model, pkg, item, folder, False)

    def add_position(parent: QStandardItem, position) -> None:
        if mode == "positions_with_dossiers" and not _contains_dossiers(pkg, position):
            return
        if empty_only and not _contains_empty_dossier(pkg, position):
            return
        item = model.make_item(pkg.display_name(position), pkg.key(position), "ordnungssystemposition")
        parent.appendRow(item)
        if mode == "main_groups":
            return
        for sub in pkg.children(position, "ordnungssystemposition"):
            add_position(item, sub)
        if mode in ("positions", "positions_with_dossiers"):
            return
        for dossier in pkg.children(position, "dossier"):
            if empty_only and _has_files(pkg, dossier) and not _contains_empty_dossier(pkg, dossier):
                continue
            d_item = model.make_item(pkg.display_name(dossier), pkg.key(dossier), "dossier")
            item.appendRow(d_item)
            _add_content(model, pkg, d_item, dossier, empty_only)
        add_folders(item, position)

    for position in pkg.children(system, "ordnungssystemposition"):
        add_position(root, position)
    add_folders(root, system)
    model.rebuilt.emit()


def _dossier_columns(pkg: SipPackage, el) -> list[str]:
    return [pkg.text(el, "aktenzeichen"), timespan.format_span(*pkg.time_span_display(el, "entstehungszeitraum")),
            pkg.text(el, "erscheinungsform")]


def build_dossier_tree(model: NavigatorModel, pkg: SipPackage | None) -> None:
    model.reset(pkg)
    if pkg is None:
        model.rebuilt.emit()
        return

    def add(parent, el, owner: int = 0) -> None:
        kind = pkg.kind(el)
        item = model.make_item(pkg.display_name(el), pkg.key(el), kind, owner=owner)
        row = model.make_row(item, _dossier_columns(pkg, el) if kind != "datei" else ["", "", ""])
        parent.appendRow(row)
        if kind == "datei":
            return
        for c in pkg.children(el):
            if pkg.kind(c) in _CONTENT_KINDS:
                add(item, c)
        for file_el in pkg.referenced_files(el):
            add(item, file_el, pkg.key(el))

    for dossier in pkg.iter_kind("dossier"):
        if pkg.kind(dossier) == "dossier":
            add(model, dossier)
    model.rebuilt.emit()


def build_package_tree(model: NavigatorModel, pkg: SipPackage | None, mode: str = "all") -> None:
    model.reset(pkg)
    if pkg is None or pkg.table_of_contents is None:
        model.rebuilt.emit()
        return
    referenced = pkg.referenced_ids()

    def unassigned(el) -> bool:
        rel = pkg.relpath(el)
        return el.get("id", "") not in referenced and rel is not None and rel.parts[:1] == ("content",)

    def contains_unassigned(folder) -> bool:
        return any(unassigned(f) for f in pkg.children(folder, "datei")) or any(
            contains_unassigned(o) for o in pkg.children(folder, "ordner")
        )

    toc = pkg.table_of_contents
    root = model.make_item(pkg.name if pkg.root_dir else "Paket", pkg.key(toc), "paket")
    model.appendRow(root)

    def add(parent: QStandardItem, el) -> None:
        for folder in pkg.children(el, "ordner"):
            if mode == "unassigned" and not contains_unassigned(folder):
                continue
            item = model.make_item(pkg.display_name(folder), pkg.key(folder), "ordner")
            parent.appendRow(item)
            add(item, folder)
        for file_el in pkg.children(el, "datei"):
            is_unassigned = unassigned(file_el)
            if mode == "unassigned" and not is_unassigned:
                continue
            in_content = (pkg.relpath(file_el) or PurePosixPath()).parts[:1] == ("content",)
            flag = ("unassigned" if is_unassigned else "assigned") if in_content else ""
            parent.appendRow(model.make_item(pkg.display_name(file_el), pkg.key(file_el), "datei", flag))

    add(root, toc)
    model.rebuilt.emit()
