"""Metadata editor: exposes the tabs, sections and fields of the selected object to QML."""

from PySide6.QtCore import Property, QObject, Signal, Slot

from . import notes, schema, statistics, timespan, xsd_info
from .sip import SipPackage, localname

_TAB_FOR_KIND = {
    "paket": "ueberblick",
    "ablieferung": "ueberblick",
    "provenienz": "ueberblick",
    "inhaltsverzeichnis": "ueberblick",
    "subdossier": "dossier",
}


def tab_for_kind(kind: str) -> str:
    return _TAB_FOR_KIND.get(kind, kind)


def _format_additional(items: list[tuple[str, str]]) -> str:
    return "; ".join(f"{n}={v}" for n, v in items)


class MetadataEditor(QObject):
    contentChanged = Signal()
    currentTabChanged = Signal()
    validationSummaryChanged = Signal()
    statisticsChanged = Signal()
    # key, kind label, object name, field label, old value, new value
    fieldEdited = Signal(int, str, str, str, str, str)
    inputError = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pkg: SipPackage | None = None
        self._selected: dict[str, int] = {}
        self._tab = "ueberblick"
        self._validation_summary: list[dict] = []
        self._issues: dict[tuple[int, str], str] = {}

    def set_package(self, pkg: SipPackage | None) -> None:
        self._pkg = pkg
        self._selected = {}
        self._tab = "ueberblick"
        self._validation_summary = []
        self._issues = {}
        self.currentTabChanged.emit()
        self.refresh()
        self.validationSummaryChanged.emit()

    def set_validation(self, summary: list[dict], issues: list[dict]) -> None:
        self._validation_summary = summary
        self._issues = {}
        for issue in issues:
            key = (issue.get("key", 0), issue.get("fieldTag", ""))
            if key[0] and key[1]:
                self._issues.setdefault(key, issue["description"])
        self.validationSummaryChanged.emit()
        self.contentChanged.emit()

    def refresh(self) -> None:
        self.contentChanged.emit()
        self.statisticsChanged.emit()

    def forget_missing(self) -> None:
        """Drops selections of objects that were removed from the tree."""
        pkg = self._pkg
        if pkg is None:
            return
        for tab, key in list(self._selected.items()):
            el = pkg.element(key)
            if el is None or el.getroottree().getroot() is not pkg.root:
                del self._selected[tab]

    # ---------------------------------------------------------------- properties

    @Property(bool, notify=contentChanged)
    def hasPackage(self) -> bool:
        return self._pkg is not None

    @Property(bool, notify=contentChanged)
    def readOnly(self) -> bool:
        return self._pkg is None or self._pkg.read_only

    @Property("QVariantList", constant=True)
    def tabs(self) -> list:
        return [{"id": tab_id, "label": label, "help": schema.KIND_HELP.get(tab_id, "")}
                for tab_id, label in schema.EDITOR_TABS]

    @Property(str, notify=currentTabChanged)
    def currentTab(self) -> str:
        return self._tab

    @Property(int, notify=contentChanged)
    def currentKey(self) -> int:
        return self._selected.get(self._tab, 0)

    @Property("QVariantMap", notify=contentChanged)
    def header(self) -> dict:
        pkg = self._pkg
        if pkg is None:
            return {}
        forms = {pkg.text(d, "erscheinungsform") for d in pkg.iter_kind("dokument")} - {""}
        appearance = "keine Angabe" if not forms else forms.pop() if len(forms) == 1 else "gemischt"
        return {
            "deliveryType": pkg.delivery_type,
            "creator": pkg.text(pkg.provenance, "aktenbildnerName"),
            "deliveryNumber": pkg.text(pkg.delivery, "ablieferungsnummer"),
            "appearance": appearance,
            "packageName": pkg.name,
        }

    @Property("QVariantList", notify=contentChanged)
    def sections(self) -> list:
        pkg = self._pkg
        if pkg is None:
            return []
        if self._tab == "ueberblick":
            elements = [pkg.delivery, pkg.provenance, pkg.root]
        elif self._tab in ("statistik", "validierung"):
            return []
        else:
            el = pkg.element(self._selected.get(self._tab, 0))
            elements = [el] if el is not None else []
        return [self._section(el) for el in elements if el is not None]

    @Property("QVariantList", notify=contentChanged)
    def breadcrumb(self) -> list:
        pkg = self._pkg
        if pkg is None or self._tab in ("ueberblick", "statistik", "validierung"):
            return []
        el = pkg.element(self._selected.get(self._tab, 0))
        if el is None:
            return []
        chain = pkg.ancestors(el) + [el]
        return [{"key": pkg.key(a), "label": pkg.display_name(a), "kind": pkg.kind(a)} for a in chain]

    @Property("QVariantMap", notify=statisticsChanged)
    def statistics(self) -> dict:
        return statistics.overview(self._pkg) if self._pkg is not None else {}

    @Property("QVariantList", notify=statisticsChanged)
    def protectionPeriods(self) -> list:
        return statistics.protection_periods(self._pkg) if self._pkg is not None else []

    @Property("QVariantMap", notify=statisticsChanged)
    def timeSpanChart(self) -> dict:
        return statistics.time_span_comparison(self._pkg) if self._pkg is not None else {"bars": []}

    @Property("QVariantList", notify=validationSummaryChanged)
    def validationSummary(self) -> list:
        return self._validation_summary

    # ---------------------------------------------------------------- slots

    @Slot(str)
    def showTab(self, tab: str) -> None:
        if tab != self._tab:
            self._tab = tab
            self.currentTabChanged.emit()
            self.contentChanged.emit()

    @Slot(int)
    def showElement(self, key: int) -> None:
        pkg = self._pkg
        el = pkg.element(key) if pkg else None
        if el is None:
            return
        kind = pkg.kind(el)
        tab = tab_for_kind(kind)
        if tab not in dict(schema.EDITOR_TABS):
            return
        if tab != "ueberblick":
            self._selected[tab] = key
            # Selecting an object also makes its ancestors the current objects of their tabs.
            for ancestor in pkg.ancestors(el):
                ancestor_tab = tab_for_kind(pkg.kind(ancestor))
                if ancestor_tab not in ("ueberblick", tab):
                    self._selected[ancestor_tab] = pkg.key(ancestor)
        self._tab = tab
        self.currentTabChanged.emit()
        self.contentChanged.emit()

    def _editable_element(self, key: int):
        pkg = self._pkg
        el = pkg.element(key) if pkg else None
        if el is None or pkg.read_only or pkg.kind(el) in schema.READ_ONLY_KINDS:
            return None
        return el

    @Slot(int, str, str)
    def setField(self, key: int, tag: str, value: str) -> None:
        el = self._editable_element(key)
        if el is None:
            return
        pkg = self._pkg
        old = pkg.text(el, tag)
        if old == value.strip():
            return
        pkg.set_text(el, tag, value, required=self._is_required(el, tag))
        self._emit_edit(el, tag, old, value.strip())

    @Slot(int, str, str, str)
    def setTimeSpan(self, key: int, tag: str, start: str, end: str) -> None:
        el = self._editable_element(key)
        if el is None:
            return
        pkg = self._pkg
        old = timespan.format_span(*pkg.time_span_display(el, tag))
        try:
            pkg.set_time_span(el, tag, start, end)
        except timespan.DateFormatError as exc:
            self.inputError.emit(str(exc))
            self.contentChanged.emit()
            return
        new = timespan.format_span(*pkg.time_span_display(el, tag))
        if old != new:
            self._emit_edit(el, tag, old, new)

    @Slot(int, str, str)
    def setTimePoint(self, key: int, tag: str, text: str) -> None:
        el = self._editable_element(key)
        if el is None:
            return
        pkg = self._pkg
        old = pkg.time_point_display(el, tag)
        try:
            pkg.set_time_point(el, tag, text)
        except timespan.DateFormatError as exc:
            self.inputError.emit(str(exc))
            self.contentChanged.emit()
            return
        new = pkg.time_point_display(el, tag)
        if old != new:
            self._emit_edit(el, tag, old, new)

    @Slot(int, "QVariantList")
    def setAdditionalData(self, key: int, items) -> None:
        """items: list of {name, value}; replaces all Merkmale of the object."""
        el = self._editable_element(key)
        if el is None:
            return
        pkg = self._pkg
        old = _format_additional(pkg.additional_data(el))
        pkg.set_additional_data(el, [(str(i.get("name", "")), str(i.get("value", ""))) for i in items])
        new = _format_additional(pkg.additional_data(el))
        if old != new:
            self._emit_edit(el, "zusatzDaten", old, new)

    # ---------------------------------------------------------------- internals

    def _emit_edit(self, el, tag: str, old: str, new: str) -> None:
        pkg = self._pkg
        self.fieldEdited.emit(pkg.key(el), schema.KIND_LABELS.get(pkg.kind(el), pkg.kind(el)),
                              pkg.display_name(el), schema.label_for(tag), old, new)

    def _schema(self):
        return xsd_info.for_package(self._pkg)

    def _is_required(self, el, tag: str) -> bool:
        definition = next((d for d in schema.field_defs(self._pkg.kind(el)) if d.tag == tag), None)
        if definition is not None and definition.required:
            return True
        info = self._schema()
        return info.is_required(xsd_info.type_name(self._pkg, el, info), tag)

    def _field(self, el, definition: schema.FieldDef, type_name: str, editable: bool) -> dict:
        pkg = self._pkg
        info = self._schema()
        choices = info.choices(type_name, definition.tag) if definition.type in (schema.TEXT, schema.READONLY) else []
        field = {
            "tag": definition.tag,
            "label": definition.label,
            "type": "choice" if choices and definition.type == schema.TEXT else definition.type,
            "choices": [""] + choices if choices and not info.is_required(type_name, definition.tag) else choices,
            "required": definition.required or info.is_required(type_name, definition.tag),
            "editable": editable and definition.type != schema.READONLY,
            "help": schema.help_for(definition.tag),
            "error": self._issues.get((pkg.key(el), definition.tag), ""),
            "value": "",
            "start": "",
            "end": "",
        }
        if definition.type == schema.TIME_SPAN:
            field["start"], field["end"] = pkg.time_span_display(el, definition.tag)
            field["value"] = timespan.format_span(field["start"], field["end"])
        elif definition.type == schema.TIME_POINT:
            field["value"] = pkg.time_point_display(el, definition.tag)
        else:
            field["value"] = pkg.text(el, definition.tag)
        return field

    def _section(self, el) -> dict:
        pkg = self._pkg
        kind = pkg.kind(el)
        info = self._schema()
        type_name = xsd_info.type_name(pkg, el, info)
        editable = not pkg.read_only and kind not in schema.READ_ONLY_KINDS
        allowed = {e.name for e in info.elements(type_name)}
        definitions = [d for d in schema.field_defs(kind) if not allowed or d.tag in allowed
                       or pkg.child(el, d.tag) is not None]
        known = {d.tag for d in definitions}
        primary = [self._field(el, d, type_name, editable) for d in definitions if d.primary]
        more = [self._field(el, d, type_name, editable) for d in definitions if not d.primary]
        for c in pkg.children(el):
            tag = localname(c)
            if tag in known or tag in schema.STRUCTURAL_TAGS or len(c):
                continue
            known.add(tag)
            more.append(self._field(el, schema.FieldDef(tag, schema.label_for(tag)), type_name, editable))
        if kind == "datei":
            rel = pkg.relpath(el)
            primary.append({"tag": "", "label": "Pfad", "type": schema.READONLY, "required": False, "editable": False,
                            "help": "", "error": "", "choices": [], "value": rel.as_posix() if rel else "",
                            "start": "", "end": ""})
        return {
            "key": pkg.key(el),
            "kind": kind,
            "title": schema.KIND_LABELS.get(kind, kind),
            "name": pkg.display_name(el),
            "noteCount": len(notes.notes_of(pkg, el)),
            "canHaveNotes": notes.can_have_notes(pkg, el),
            "canHaveAdditionalData": "zusatzDaten" in allowed,
            "additionalData": [{"name": n, "value": v} for n, v in pkg.additional_data(el)],
            "readOnly": not editable,
            "primary": primary,
            "more": more,
        }
