"""Feature controllers exposed to QML next to the core Backend."""

import json
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from . import files, fixes, notes, package_factory, reports, sampling, schema, search, structure, timespan
from .backend import SIMPLE_SEARCH_COLUMNS, Backend
from .sip import localname

_ERRORS = (structure.StructureError, files.FileOperationError, notes.NoteError, timespan.DateFormatError,
           package_factory.PackageCreationError, OSError)


def _keys(values) -> list[int]:
    return [int(v) for v in values or [] if int(v)]


class _Controller(QObject):
    def __init__(self, backend: Backend, parent=None):
        super().__init__(parent or backend)
        self.backend = backend

    def _run(self, title: str, action, *, writable: bool = True):
        """Runs action(pkg) and reports domain errors to the user; returns the action's result or None."""
        pkg = self.backend.require_writable() if writable else self.backend.package
        if pkg is None:
            return None
        try:
            return action(pkg)
        except _ERRORS as exc:
            self.backend.message.emit(title, str(exc))
            return None

    def _elements(self, keys) -> list:
        pkg = self.backend.package
        return [el for el in (pkg.element(k) for k in _keys(keys)) if el is not None] if pkg else []


class StructureController(_Controller):
    """Ordnungssystem-Navigator: create, move, delete, assign, renumber, mass assignment and mass edit."""

    clipboardChanged = Signal()

    def __init__(self, backend: Backend, parent=None):
        super().__init__(backend, parent)
        self._cut: list[int] = []

    @Slot(int, result="QVariantList")
    def allowedChildren(self, key: int) -> list:
        pkg = self.backend.package
        el = pkg.element(key) if pkg else None
        if el is None or pkg.read_only:
            return []
        kind = pkg.kind(el)
        result = []
        for tag, parents in structure.CONTAINERS.items():
            if kind not in parents:
                continue
            if tag == "ordnungssystemposition" and pkg.children(el, "dossier"):
                continue
            if tag == "dossier" and kind == "ordnungssystemposition" and pkg.children(el, "ordnungssystemposition"):
                continue
            result.append(tag)
        return result

    @Slot(int, str, int, result=int)
    def addObjects(self, parent_key: int, tag: str, count: int) -> int:
        parent = self._elements([parent_key])
        if not parent:
            return 0
        created = self._run("Neues Objekt", lambda pkg: structure.add_objects(pkg, parent[0], tag, count))
        if created:
            label = schema.KIND_LABELS.get(tag, tag)
            self.backend.after_change(f"{len(created)} × {label} erstellt", self.backend.package.key(created[0]))
            self.backend.reveal(self.backend.package.key(created[0]))
            return self.backend.package.key(created[0])
        return 0

    @Slot("QVariantList")
    def deleteObjects(self, keys) -> None:
        elements = [el for el in self._elements(keys) if localname(el) in structure.CONTAINERS]
        if not elements:
            return
        count = self._run("Löschen", lambda pkg: structure.delete(pkg, elements))
        if count:
            self.backend.after_change(f"{count} Objekt(e) gelöscht")

    @Slot(int, int)
    def unassignFile(self, owner_key: int, file_key: int) -> None:
        owner, file_el = self._elements([owner_key]), self._elements([file_key])
        if owner and file_el and self._run("Zuweisung löschen", lambda pkg: structure.unassign(pkg, owner[0], file_el[0])):
            self.backend.after_change("Dateizuweisung gelöscht", owner_key)

    @Slot("QVariantList")
    def cut(self, keys) -> None:
        self._cut = [k for k in _keys(keys) if localname(self.backend.package.element(k)) in structure.CONTAINERS]
        self.clipboardChanged.emit()
        self.backend.set_status(f"{len(self._cut)} Objekt(e) zum Verschieben ausgeschnitten")

    @Property(int, notify=clipboardChanged)
    def cutCount(self) -> int:
        return len(self._cut)

    @Slot(int)
    def paste(self, target_key: int) -> None:
        target = self._elements([target_key])
        moving = self._elements(self._cut)
        if not target or not moving:
            return

        def move_all(pkg):
            for el in moving:
                structure.move(pkg, el, target[0])
            return len(moving)

        if self._run("Verschieben", move_all):
            self._cut = []
            self.clipboardChanged.emit()
            self.backend.after_change(f"{len(moving)} Objekt(e) verschoben", target_key)

    @Slot(int, int)
    def moveRelative(self, key: int, offset: int) -> None:
        el = self._elements([key])
        if el and self._run("Verschieben", lambda pkg: structure.move_relative(pkg, el[0], offset)):
            self.backend.after_change("Reihenfolge geändert", key)
            self.backend.reveal(key)

    @Slot("QVariantList", int, result=int)
    def assignFiles(self, file_keys, target_key: int) -> int:
        target = self._elements([target_key])
        file_els = [f for f in self._elements(file_keys) if localname(f) == "datei"]
        if not target or not file_els:
            self.backend.message.emit("Dateien zuweisen", "Wählen Sie im Paket-Navigator Dateien und im "
                                      "Ordnungssystem-Navigator ein Dossier oder Dokument aus.")
            return 0
        count = self._run("Dateien zuweisen", lambda pkg: structure.assign_files(pkg, target[0], file_els))
        if count:
            self.backend.after_change(f"{count} Datei(en) zugewiesen", target_key)
        return count or 0

    @Slot(int, int)
    def documentForFile(self, owner_key: int, file_key: int) -> None:
        owner, file_el = self._elements([owner_key]), self._elements([file_key])
        if owner and file_el and self._run("Neues Dokument", lambda pkg: structure.document_for_file(pkg, owner[0], file_el[0])) is not None:
            self.backend.after_change("Dokument für Datei erstellt", owner_key)

    @Slot(int)
    def documentsForFiles(self, key: int) -> None:
        el = self._elements([key])
        count = self._run("Neue Dokumente", lambda pkg: structure.documents_for_files(pkg, el[0])) if el else 0
        if count:
            self.backend.after_change(f"{count} Dokument(e) für Dateien erstellt", key)

    @Slot(str)
    def renumber(self, scheme: str) -> None:
        count = self._run("Ordnungssystem nummerieren", lambda pkg: structure.renumber(pkg, scheme))
        if count:
            self.backend.after_change(f"Ordnungssystem neu nummeriert ({count} Positionen)")

    @Slot(int)
    def accumulateTimeSpans(self, key: int) -> None:
        el = self._elements([key])
        result = self._run("Zeiträume kumulieren", lambda pkg: structure.accumulate_time_spans(pkg, el[0])) if el else None
        if result and any(result):
            self.backend.after_change("Zeiträume kumuliert", key, rebuild=False)
        elif result is not None:
            self.backend.message.emit("Zeiträume kumulieren", "Unterhalb des Dossiers gibt es keine konkreten Zeitangaben.")

    @Slot("QVariantList", int, int, int, bool, bool)
    def massAssign(self, folder_keys, target_key: int, osp_levels: int, dossier_levels: int,
                   create_documents: bool, include_top: bool) -> None:
        folders = [f for f in self._elements(folder_keys) if localname(f) == "ordner"]
        target = self._elements([target_key])
        if not folders or not target:
            self.backend.message.emit("Massenzuweisung", "Wählen Sie im Paket-Navigator Ordner und im "
                                      "Ordnungssystem-Navigator das Ordnungssystem, eine OSP oder ein Dossier aus.")
            return
        result = self._run("Massenzuweisung", lambda pkg: structure.mass_assign(
            pkg, folders, target[0], osp_levels, dossier_levels, create_documents, include_top))
        if result is None:
            return
        created, unassigned = result
        self.backend.after_change(f"Massenzuweisung: {created} Objekt(e) erstellt", target_key)
        if unassigned:
            self.backend.message.emit("Massenzuweisung", f"{unassigned} Datei(en) wurden nicht zugewiesen, weil sie "
                                      "auf einer Stufe ohne Dossier liegen. Erhöhen Sie die Anzahl Dossier Stufen "
                                      "oder weisen Sie die Dateien einzeln zu.")

    @Slot(int, result="QVariantList")
    def massEditKinds(self, key: int) -> list:
        el = self._elements([key])
        pkg = self.backend.package
        return [{"kind": k, "label": schema.KIND_LABELS[k]} for k in structure.mass_edit_kinds(pkg, el[0])] if el else []

    @Slot(str, result="QVariantList")
    def massEditFields(self, kind: str) -> list:
        return structure.mass_edit_fields(kind)

    @Slot(int, str, str, str, str)
    def massEdit(self, key: int, kind: str, tag: str, value: str, end: str) -> None:
        el = self._elements([key])
        count = self._run("Massenmutation", lambda pkg: structure.mass_edit(pkg, el[0], kind, tag, value, end)) if el else None
        if count:
            action = "gelöscht" if not value.strip() else "gesetzt"
            self.backend.after_change(f"Massenmutation: {schema.label_for(tag)} bei {count} Objekt(en) {action}", key)


class FileController(_Controller):
    """Paket-Navigator file operations, normalization and Validierungshilfe fix-ups."""

    def _folder(self, key: int):
        el = self._elements([key])
        return el[0] if el and localname(el[0]) == "ordner" else None

    @Slot(int, "QVariantList", result="QVariantList")
    def importConflicts(self, folder_key: int, urls) -> list:
        pkg, folder = self.backend.package, self._folder(folder_key)
        if pkg is None or folder is None:
            return []
        names = {pkg.text(c, "name") for c in pkg.children(folder) if localname(c) in ("ordner", "datei")}
        return [Path(QUrl(u).toLocalFile()).name for u in urls if Path(QUrl(u).toLocalFile()).name in names]

    @Slot(int, "QVariantList", bool, bool)
    def importUrls(self, folder_key: int, urls, merge: bool, overwrite: bool) -> None:
        folder = self._folder(folder_key)
        if folder is None:
            self.backend.message.emit("Importieren", "Wählen Sie im Paket-Navigator einen Ordner in content aus.")
            return
        paths = [Path(QUrl(u).toLocalFile()) for u in urls if QUrl(u).isLocalFile()]
        stats = self._run("Importieren", lambda pkg: files.import_paths(pkg, folder, paths, merge, overwrite))
        if stats:
            self.backend.after_change(f"Importiert: {stats['files']} Datei(en), {stats['folders']} Ordner, "
                                      f"{stats['replaced']} ersetzt, {stats['skipped']} übersprungen",
                                      folder_key, file_system=True)

    @Slot(int, str)
    def newFolder(self, parent_key: int, name: str) -> None:
        parent = self._folder(parent_key)
        created = self._run("Neuer Ordner", lambda pkg: files.create_folder(pkg, parent, name.strip())) if parent is not None else None
        if created is not None:
            self.backend.after_change(f"Ordner {name} erstellt", self.backend.package.key(created), file_system=True)

    @Slot(int, str)
    def rename(self, key: int, name: str) -> None:
        el = self._elements([key])
        if el and self._run("Umbenennen", lambda pkg: files.rename(pkg, el[0], name.strip()) or True):
            self.backend.after_change(f"Umbenannt in {name}", key, file_system=True)

    @Slot("QVariantList")
    def deleteEntries(self, keys) -> None:
        elements = [el for el in self._elements(keys) if localname(el) in ("ordner", "datei")]
        count = self._run("Löschen", lambda pkg: files.delete_entries(pkg, elements)) if elements else None
        if count:
            self.backend.after_change(f"{count} Ordner/Datei(en) gelöscht", file_system=True)

    @Slot(int, QUrl)
    def replaceFile(self, key: int, url: QUrl) -> None:
        el = self._elements([key])
        if el and self._run("Datei ersetzen", lambda pkg: files.replace_file(pkg, el[0], Path(url.toLocalFile())) or True):
            self.backend.after_change("Datei ersetzt", key, file_system=True)
            self.backend.message.emit("Datei ersetzen", "Die Datei wurde erfolgreich ersetzt und die Prüfsumme angepasst.")

    @Slot(QUrl, result="QVariantList")
    def replacementCandidates(self, url: QUrl) -> list:
        result = self._run("Dateien ersetzen", lambda pkg: files.replacement_candidates(pkg, Path(url.toLocalFile())))
        pkg = self.backend.package
        return [pkg.relpath(el).as_posix() for el, _ in result or []]

    @Slot(QUrl)
    def replaceFiles(self, url: QUrl) -> None:
        def run(pkg):
            return files.replace_files(pkg, files.replacement_candidates(pkg, Path(url.toLocalFile())))

        names = self._run("Dateien ersetzen", run)
        if names:
            self.backend.after_change(f"{len(names)} Datei(en) ersetzt", file_system=True)
            self.backend.message.emit("Dateien ersetzen", "Folgende Dateien wurden ersetzt:\n" + "\n".join(names))
        elif names is not None:
            self.backend.message.emit("Dateien ersetzen", "Es wurden keine gleichnamigen Dateien gefunden.")

    @Slot(str)
    def normalize(self, which: str) -> None:
        action = {"names": files.normalize_names, "paths": files.shorten_paths, "undo": files.denormalize}.get(which)
        if action is None:
            return
        if self.backend.dirty:
            self.backend.message.emit("Normalisierung", "Bitte speichern Sie das Paket vor der Normalisierung.")
            return
        count = self._run("Normalisierung", action)
        if count is not None:
            self.backend.after_change(f"Normalisierung: {count} Ordner/Datei(en) umbenannt", file_system=True)

    @Slot(int, result="QVariantList")
    def fixActions(self, row: int) -> list:
        issue = self.backend.validationTable.recordAt(row)
        if self.backend.readOnly:
            return []
        return [{"id": a, "label": fixes.LABELS[a], "confirm": a in fixes.CONFIRM_ACTIONS}
                for a in fixes.actions_for(issue)]

    @Slot(str, "QVariantList")
    def applyFix(self, action: str, rows) -> None:
        issues = [self.backend.validationTable.recordAt(int(r)) for r in rows]
        count = self._run(fixes.LABELS.get(action, "Korrektur"), lambda pkg: fixes.apply(pkg, action, issues))
        if count is not None:
            self.backend.resolve_issues([i for i in issues if action in fixes.actions_for(i)])
            self.backend.after_change(f"{fixes.LABELS[action]}: {count} Objekt(e)",
                                      file_system=action in fixes.FILE_SYSTEM_ACTIONS)


class NoteController(_Controller):
    """Notizen (14.1)."""

    @Slot(int, result=bool)
    def canHaveNotes(self, key: int) -> bool:
        el = self._elements([key])
        return bool(el) and notes.can_have_notes(self.backend.package, el[0])

    @Slot("QVariantList", str)
    def addNote(self, keys, text: str) -> None:
        elements = self._elements(keys)

        def add(pkg):
            return [notes.add_note(pkg, el, text) for el in elements]

        if elements and self._run("Neue Notiz", add):
            self.backend.after_change(f"Notiz zu {len(elements)} Objekt(en) erfasst", self.backend.package.key(elements[0]))

    @Slot(int, str)
    def editNote(self, note_key: int, text: str) -> None:
        note = self._elements([note_key])
        if note and self._run("Notiz bearbeiten", lambda pkg: notes.edit_note(pkg, note[0], text) or True):
            self.backend.after_change("Notiz bearbeitet", rebuild=False)

    @Slot("QVariantList")
    def deleteNotes(self, note_keys) -> None:
        elements = [n for n in self._elements(note_keys) if notes.is_note(n)]

        def delete(pkg):
            for note in elements:
                notes.delete_note(pkg, note)
            return len(elements)

        if elements and self._run("Notiz löschen", delete):
            self.backend.after_change(f"{len(elements)} Notiz(en) gelöscht")


class SearchController(_Controller):
    """Einfache / erweiterte Suche (13) and Stichprobe (14.2)."""

    @Slot(str, result=int)
    def simpleSearch(self, text: str) -> int:
        table = self.backend.searchTable
        try:
            results = self._run("Suche", lambda pkg: search.simple_search(pkg, text, self.backend.maxSearchHits),
                                writable=False)
        except search.TooManyHits as exc:
            self.backend.message.emit("Zu viele Treffer", str(exc))
            return -1
        if results is None:
            return 0
        if not results:
            return 0
        table.set_columns(SIMPLE_SEARCH_COLUMNS)
        table.set_records(results)
        self.backend.set_status(f"Suche: {len(results)} Objekte")
        return len(results)

    @Property("QVariantList", constant=True)
    def kinds(self) -> list:
        return [{"kind": k, "label": schema.KIND_LABELS.get(k, k)} for k in search.SEARCHABLE_KINDS + ("subdossier",)]

    @Slot(str, result="QVariantList")
    def fields(self, kind: str) -> list:
        return search.searchable_fields(kind)

    @Slot("QVariantList", result=int)
    def advancedSearch(self, criteria) -> int:
        parsed = [search.Criterion(str(c.get("kind", "")), str(c.get("tag", "")), str(c.get("value", "")),
                                   bool(c.get("empty", False))) for c in criteria]
        parsed = [c for c in parsed if c.kind and c.tag]
        if not parsed or any(not c.empty and not c.value.strip() for c in parsed):
            self.backend.message.emit("Suchanfrage nicht vollständig",
                                      "Pro Suchkriterium müssen Objekt, Metadatum und Wert (oder Leerfeld) angegeben werden.")
            return -1
        try:
            results = self._run("Erweiterte Suche", lambda pkg: search.advanced_search(pkg, parsed, self.backend.maxSearchHits),
                                writable=False)
        except search.TooManyHits as exc:
            self.backend.message.emit("Zu viele Treffer", str(exc))
            return -1
        if not results:
            return 0
        columns = [("object", "Objekt"), ("objectName", "Objektname")]
        columns += [(f"value{i}", schema.label_for(c.tag)) for i, c in enumerate(parsed)]
        self.backend.searchTable.set_columns(columns)
        self.backend.searchTable.set_records(results)
        self.backend.set_status(f"Erweiterte Suche: {len(results)} Objekte")
        return len(results)

    @Slot()
    def drawSample(self) -> None:
        rows = self._run("Stichprobe", lambda pkg: sampling.draw_sample(pkg, self.backend.sampleMode,
                                                                        self.backend.sampleSize), writable=False)
        if rows is not None:
            self.backend.sampleTable.set_records(rows)
            self.backend.set_status(f"Stichprobe: {len(rows)} Dossiers")


class PackageController(_Controller):
    """New package wizard, reports, help and perspectives."""

    perspectivesChanged = Signal()

    def __init__(self, backend: Backend, manual_paths: list[Path], parent=None):
        super().__init__(backend, parent)
        self._manual_paths = manual_paths

    @Property(str, constant=True)
    def xsdVersion(self) -> str:
        return package_factory.XSD_VERSION_LABEL

    @Slot(str, str, result=str)
    def suggestedName(self, office: str, reference: str) -> str:
        return package_factory.suggested_name(office, reference)

    @Slot(str, result=str)
    def nameError(self, name: str) -> str:
        try:
            package_factory.check_name(name, self.backend.validateSipName)
            return ""
        except package_factory.PackageCreationError as exc:
            return str(exc)

    @Slot(QUrl, str, str, str, str, str, QUrl, result=bool)
    def createPackage(self, folder: QUrl, name: str, office: str, delivery_type: str, creator: str,
                      system_name: str, csv_url: QUrl) -> bool:
        csv_path = csv_url.toLocalFile() if csv_url.isValid() and csv_url.isLocalFile() else None
        try:
            pkg = package_factory.create_package(folder.toLocalFile(), name.strip(), office, delivery_type, creator,
                                                 system_name, csv_path, self.backend.validateSipName)
        except _ERRORS as exc:
            self.backend.message.emit("Neues Paket erstellen", str(exc))
            return False
        self.backend.set_package(pkg)
        self.backend.set_status(f"Paket {pkg.name} erstellt")
        return True

    @Property("QVariantList", constant=True)
    def reportTypes(self) -> list:
        return [{"id": k, "label": v} for k, v in reports.REPORTS.items()]

    @Slot(str, QUrl)
    def createReport(self, report: str, url: QUrl) -> None:
        target = self._run("Bericht erstellen", lambda pkg: reports.write_pdf(pkg, report, url.toLocalFile(),
                                                                                self.backend.reporterName),
                           writable=False)
        if target is not None:
            self.backend.set_status(f"Bericht erstellt: {target}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    @Slot()
    def openUserManual(self) -> None:
        for path in self._manual_paths:
            if path.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
                return
        self.backend.message.emit("Benutzerdokumentation", "Die Benutzerdokumentation wurde nicht gefunden.")

    # ---------------------------------------------------------------- perspectives (16)

    def _perspectives(self) -> dict:
        try:
            return json.loads(str(self.backend.setting("ui/perspectives", "{}")))
        except json.JSONDecodeError:
            return {}

    @Property("QVariantList", notify=perspectivesChanged)
    def perspectives(self) -> list:
        return sorted(self._perspectives())

    @Slot(str, "QVariantMap")
    def savePerspective(self, name: str, state: dict) -> None:
        data = self._perspectives()
        data[name.strip() or "Standard"] = {k: float(v) for k, v in state.items()}
        self.backend.set_setting("ui/perspectives", json.dumps(data))
        self.perspectivesChanged.emit()

    @Slot(str, result="QVariantMap")
    def perspective(self, name: str) -> dict:
        return self._perspectives().get(name, {})

    @Slot(str)
    def deletePerspective(self, name: str) -> None:
        data = self._perspectives()
        data.pop(name, None)
        self.backend.set_setting("ui/perspectives", json.dumps(data))
        self.perspectivesChanged.emit()

    @Slot(str, result=str)
    def fieldHelp(self, tag: str) -> str:
        return schema.help_for(tag)
