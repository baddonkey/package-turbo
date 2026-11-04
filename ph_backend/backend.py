"""Core application controller: package lifecycle, models, validation and change tracking."""

import csv
from datetime import datetime

from PySide6.QtCore import Property, QObject, QSettings, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

from . import navigators, notes, sampling, schema, search, structure, validation
from .editor import MetadataEditor
from .navigators import NavigatorModel
from .sip import InvalidPackageError, SipPackage, localname
from .tables import RecordTableModel

MAX_RECENT = 3
# Checks that only scan the file system / metadata and are cheap enough to repeat after file operations.
FILE_SYSTEM_CHECKS = {"illegal_entries", "header_content", "wrong_file", "wrong_folder", "missing_file",
                      "missing_folder", "surplus_file", "surplus_folder", "file_format", "identical_files",
                      "positions_and_dossiers", "sip_name", "package_size"}


class ValidationWorker(QThread):
    progressChanged = Signal(int)

    def __init__(self, validator: validation.Validator, full: bool, parent=None):
        super().__init__(parent)
        self._validator = validator
        self._full = full
        self.result: list[dict] = []
        self.error = ""

    def run(self):
        try:
            self.result = self._validator.run(self._full, self.progressChanged.emit, self.isInterruptionRequested)
        except Exception as exc:  # surfaced to the user as a message instead of crashing the thread
            self.error = str(exc)


class Backend(QObject):
    packageChanged = Signal()
    dirtyChanged = Signal()
    busyChanged = Signal()
    progressChanged = Signal()
    statusChanged = Signal()
    recentChanged = Signal()
    filtersChanged = Signal()
    validationChanged = Signal()
    settingsChanged = Signal()
    message = Signal(str, str)
    packageOpened = Signal()
    revealElement = Signal(int)
    validityPrompt = Signal()

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._pkg: SipPackage | None = None
        self._dirty = False
        self._busy = False
        self._progress = 0
        self._status = "Bereit"
        self._worker: ValidationWorker | None = None
        self._full_issues: list[dict] = []
        self._had_full_run = False
        self._classification_filter = "all"
        self._package_filter = "all"
        self._validation_filter = ""

        self.classificationModel = NavigatorModel(["Ordnungssystem"], self)
        self.dossierModel = NavigatorModel(["Titel", "Aktenzeichen", "Entstehungszeitraum", "Erscheinungsform"], self)
        self.packageModel = NavigatorModel(["Paket"], self)
        self.editor = MetadataEditor(self)
        self.validationTable = RecordTableModel([
            ("severityLabel", "I"), ("object", "Objekt"), ("objectName", "Objektname"), ("check", "Prüfung"),
            ("description", "Beschreibung"), ("field", "Metadatum"), ("value", "Wert"),
        ], self)
        self.changesTable = RecordTableModel([
            ("time", "Zeit"), ("object", "Objekt"), ("objectName", "Objektname"), ("field", "Metadatum"),
            ("newValue", "Wert"), ("oldValue", "Gespeicherter Wert"),
        ], self)
        self.searchTable = RecordTableModel(SIMPLE_SEARCH_COLUMNS, self)
        self.notesTable = RecordTableModel([
            ("object", "Objekt"), ("objectName", "Objektname"), ("comment", "Kommentar"),
            ("created", "Erstellungsdatum"), ("author", "Erfasst durch"),
        ], self)
        self.sampleTable = RecordTableModel([
            ("object", "Objekt"), ("reference", "Aktenzeichen"), ("objectName", "Titel"),
        ], self)
        self.editor.fieldEdited.connect(self._on_field_edited)
        self.editor.inputError.connect(lambda text: self.message.emit("Ungültige Eingabe", text))

    # ---------------------------------------------------------------- access for controllers

    @property
    def package(self) -> SipPackage | None:
        return self._pkg

    def require_writable(self) -> SipPackage | None:
        if self._pkg is None:
            return None
        if self._pkg.read_only:
            self.message.emit("Schreibgeschützt", "Das Paket ist schreibgeschützt geöffnet.")
            return None
        return self._pkg

    def setting(self, key: str, default):
        value = self._settings.value(key, default)
        if isinstance(default, bool):
            return str(value).lower() == "true"
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        return value

    def set_setting(self, key: str, value) -> None:
        self._settings.setValue(key, ("true" if value else "false") if isinstance(value, bool) else value)
        self.settingsChanged.emit()

    # ---------------------------------------------------------------- properties

    @Property(bool, notify=packageChanged)
    def hasPackage(self) -> bool:
        return self._pkg is not None

    @Property(bool, notify=packageChanged)
    def hasSip(self) -> bool:
        return self._pkg is not None and self._pkg.root_dir is not None

    @Property(str, notify=packageChanged)
    def packageName(self) -> str:
        return self._pkg.name if self._pkg else ""

    @Property(bool, notify=packageChanged)
    def readOnly(self) -> bool:
        return self._pkg is not None and self._pkg.read_only

    @Property(bool, notify=dirtyChanged)
    def dirty(self) -> bool:
        return self._dirty

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(int, notify=progressChanged)
    def progress(self) -> int:
        return self._progress

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property("QVariantList", notify=recentChanged)
    def recentPackages(self) -> list:
        return self._recent()

    @Property(str, notify=filtersChanged)
    def classificationFilter(self) -> str:
        return self._classification_filter

    @Property(str, notify=filtersChanged)
    def packageFilter(self) -> str:
        return self._package_filter

    @Property(str, notify=filtersChanged)
    def validationFilter(self) -> str:
        return self._validation_filter

    @Property("QVariantList", constant=True)
    def checkNames(self) -> list:
        return validation.CHECK_NAMES

    @Property(int, notify=validationChanged)
    def errorCount(self) -> int:
        return sum(1 for r in self.validationTable.records() if r["severity"] == validation.ERROR)

    @Property(int, notify=validationChanged)
    def warningCount(self) -> int:
        return sum(1 for r in self.validationTable.records() if r["severity"] == validation.WARNING)

    @Property(int, notify=validationChanged)
    def visibleIssueCount(self) -> int:
        return self.validationTable.visibleCount()

    def _get_validate_sip_name(self) -> bool:
        return self.setting("validation/sipName", True)

    def _set_validate_sip_name(self, value: bool) -> None:
        self.set_setting("validation/sipName", bool(value))

    validateSipName = Property(bool, _get_validate_sip_name, _set_validate_sip_name, notify=settingsChanged)

    def _get_expand_threshold(self) -> int:
        return self.setting("navigators/expandThreshold", 15000)

    def _set_expand_threshold(self, value: int) -> None:
        self.set_setting("navigators/expandThreshold", int(value))

    expandThreshold = Property(int, _get_expand_threshold, _set_expand_threshold, notify=settingsChanged)

    def _get_max_hits(self) -> int:
        return self.setting("search/maxHits", search.DEFAULT_MAX_HITS)

    def _set_max_hits(self, value: int) -> None:
        self.set_setting("search/maxHits", int(value))

    maxSearchHits = Property(int, _get_max_hits, _set_max_hits, notify=settingsChanged)

    def _get_sample_mode(self) -> str:
        return str(self.setting("sample/mode", sampling.DEFAULT_MODE))

    def _set_sample_mode(self, value: str) -> None:
        self.set_setting("sample/mode", value if value in (sampling.ABSOLUTE, sampling.PERCENT) else sampling.ABSOLUTE)

    sampleMode = Property(str, _get_sample_mode, _set_sample_mode, notify=settingsChanged)

    def _get_sample_size(self) -> int:
        return self.setting("sample/size", sampling.DEFAULT_SIZE)

    def _set_sample_size(self, value: int) -> None:
        self.set_setting("sample/size", max(0, int(value)))

    sampleSize = Property(int, _get_sample_size, _set_sample_size, notify=settingsChanged)

    def _get_reporter(self) -> str:
        return str(self.setting("reports/reporter", notes.default_author()))

    def _set_reporter(self, value: str) -> None:
        self.set_setting("reports/reporter", value.strip())

    reporterName = Property(str, _get_reporter, _set_reporter, notify=settingsChanged)

    def _get_language(self) -> str:
        return str(self.setting("ui/language", "de"))

    def _set_language(self, value: str) -> None:
        self.set_setting("ui/language", value if value in ("de", "fr") else "de")

    language = Property(str, _get_language, _set_language, notify=settingsChanged)

    # ---------------------------------------------------------------- opening / closing

    @Slot(QUrl, bool)
    def openPackage(self, url: QUrl, read_only: bool = False) -> None:
        self._open(lambda: SipPackage.open_folder(url.toLocalFile(), read_only))

    @Slot(str)
    def openRecent(self, path: str) -> None:
        self._open(lambda: SipPackage.open_folder(path))

    @Slot(QUrl)
    def openMetadata(self, url: QUrl) -> None:
        self._open(lambda: SipPackage.open_metadata(url.toLocalFile()))

    def _open(self, loader) -> None:
        try:
            pkg = loader()
        except InvalidPackageError as exc:
            self.message.emit("Paket kann nicht geöffnet werden", str(exc))
            return
        self.set_package(pkg)
        self._set_status(f"Paket {pkg.name} geöffnet" + (" (schreibgeschützt)" if pkg.read_only else ""))
        self.packageOpened.emit()

    def set_package(self, pkg: SipPackage | None) -> None:
        self.cancelTask()
        self._pkg = pkg
        self._full_issues = []
        self._had_full_run = False
        self._set_dirty(False)
        self.changesTable.set_records([])
        self.searchTable.set_records([])
        self.sampleTable.set_records([])
        self.rebuild_navigators()
        self.editor.set_package(pkg)
        self._refresh_notes()
        self._run_continuous_validation()
        if pkg is not None and pkg.root_dir:
            self._remember(str(pkg.root_dir))
        self.packageChanged.emit()

    @Slot()
    def closePackage(self) -> None:
        if self._pkg is not None:
            self.set_package(None)
            self._set_status("Paket geschlossen")

    def rebuild_navigators(self) -> None:
        navigators.build_classification_tree(self.classificationModel, self._pkg, self._classification_filter)
        navigators.build_dossier_tree(self.dossierModel, self._pkg)
        navigators.build_package_tree(self.packageModel, self._pkg, self._package_filter)

    def _recent(self) -> list:
        value = self._settings.value("recentPackages", [])
        if isinstance(value, str):
            value = [value]
        return [v for v in (value or []) if v]

    def _remember(self, path: str) -> None:
        recent = [path] + [p for p in self._recent() if p != path]
        self._settings.setValue("recentPackages", recent[: MAX_RECENT + 1])
        self.recentChanged.emit()

    # ---------------------------------------------------------------- saving / export

    @Slot(result=bool)
    def save(self) -> bool:
        if self._pkg is None or self._pkg.read_only:
            return False
        try:
            self._pkg.save()
        except OSError as exc:
            self.message.emit("Speichern fehlgeschlagen", str(exc))
            return False
        self._set_dirty(False)
        # The view 'Änderungen' only lists changes since the last save.
        self.changesTable.set_records([])
        self._set_status("Paket gespeichert")
        return True

    @Slot(QUrl)
    def zipPackage(self, url: QUrl) -> None:
        if self._pkg is None:
            return
        try:
            self._pkg.zip_to(url.toLocalFile())
            self._set_status(f"Paket gezippt: {url.toLocalFile()}")
        except (OSError, InvalidPackageError) as exc:
            self.message.emit("Paket zippen fehlgeschlagen", str(exc))

    @Slot(QUrl)
    def exportMetadata(self, url: QUrl) -> None:
        if self._pkg is None:
            return
        try:
            self._pkg.export_metadata(url.toLocalFile())
            self._set_status(f"metadata.xml exportiert: {url.toLocalFile()}")
        except OSError as exc:
            self.message.emit("Export fehlgeschlagen", str(exc))

    def _table(self, which: str) -> RecordTableModel | None:
        return {"validation": self.validationTable, "changes": self.changesTable, "search": self.searchTable,
                "notes": self.notesTable, "sample": self.sampleTable}.get(which)

    @Slot(str, QUrl)
    def exportTable(self, which: str, url: QUrl) -> None:
        table = self._table(which)
        if table is None:
            return
        lines = [line.split("\t") for line in table.toTsv().split("\n")]
        try:
            # utf-8-sig and ';' so that Excel opens the file with umlauts and columns intact.
            with open(url.toLocalFile(), "w", newline="", encoding="utf-8-sig") as fh:
                csv.writer(fh, delimiter=";").writerows(lines)
            self._set_status(f"Tabelle exportiert: {url.toLocalFile()}")
        except OSError as exc:
            self.message.emit("Export fehlgeschlagen", str(exc))

    @Slot(str)
    def copyToClipboard(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    # ---------------------------------------------------------------- selection / navigation

    @Slot(int)
    def select(self, key: int) -> None:
        if key:
            self.editor.showElement(key)

    @Slot(int)
    def reveal(self, key: int) -> None:
        if key:
            self.editor.showElement(key)
            self.revealElement.emit(key)

    @Slot(int)
    def openFile(self, key: int) -> None:
        pkg = self._pkg
        el = pkg.element(key) if pkg else None
        if el is None or localname(el) != "datei":
            return
        path = pkg.fs_path(el)
        if path is None or not path.is_file():
            self.message.emit("Datei zeigen", "Die Datei ist im Dateisystem nicht vorhanden.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    @Slot(str)
    def setClassificationFilter(self, mode: str) -> None:
        self._classification_filter = mode if mode in navigators.CLASSIFICATION_FILTERS else "all"
        navigators.build_classification_tree(self.classificationModel, self._pkg, self._classification_filter)
        self.filtersChanged.emit()

    @Slot(str)
    def setPackageFilter(self, mode: str) -> None:
        self._package_filter = mode if mode in navigators.PACKAGE_FILTERS else "all"
        navigators.build_package_tree(self.packageModel, self._pkg, self._package_filter)
        self.filtersChanged.emit()

    @Slot(str)
    def setValidationFilter(self, check_name: str) -> None:
        self._validation_filter = check_name
        self.validationTable.set_filter((lambda r: r["check"] == check_name) if check_name else None)
        self.filtersChanged.emit()
        self.validationChanged.emit()

    # ---------------------------------------------------------------- validation

    @Slot(bool)
    def validate(self, full: bool) -> None:
        if self._pkg is None or self._busy:
            return
        validator = validation.Validator(self._pkg, self.validateSipName)
        self._worker = ValidationWorker(validator, full, self)
        self._worker.progressChanged.connect(self._on_progress)
        self._worker.finished.connect(lambda: self._on_validation_finished(full))
        self._progress = 0
        self.progressChanged.emit()
        self._set_busy(True)
        self._set_status("Paket wird validiert ...")
        self._worker.start()

    @Slot()
    def cancelTask(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._set_status("Abbrechen ...")
            self._worker.requestInterruption()
            self._worker.wait()

    def _on_progress(self, value: int) -> None:
        self._progress = value
        self.progressChanged.emit()

    def _on_validation_finished(self, full: bool) -> None:
        worker, self._worker = self._worker, None
        self._set_busy(False)
        if worker is None:
            return
        worker.deleteLater()
        if worker.error:
            self.message.emit("Validierung fehlgeschlagen", worker.error)
            return
        if worker.isInterruptionRequested():
            self._set_status("Validierung abgebrochen")
            return
        if full:
            full_only = {c.id for c in validation.CHECKS if c.full_only}
            self._full_issues = [i for i in worker.result if i["checkId"] in full_only]
            self._had_full_run = True
        self._publish_issues(worker.result if full else self._merge(worker.result))
        self._set_status(f"Validierung abgeschlossen: {self.errorCount} Fehler, {self.warningCount} Warnungen")
        remaining = {i["checkId"] for i in self.validationTable.records() if i["severity"] == validation.ERROR}
        if full and remaining == {"validity_failed"}:
            self.validityPrompt.emit()

    def _merge(self, continuous: list[dict]) -> list[dict]:
        issues = [i for i in continuous + self._full_issues if i["checkId"] != "validity_failed"]
        if self._had_full_run:
            validator = validation.Validator(self._pkg)
            validator.issues = issues
            validator.add_validity_summary()
        return issues

    def _run_continuous_validation(self) -> None:
        if self._pkg is None:
            self._publish_issues([])
            return
        issues = validation.Validator(self._pkg, self.validateSipName).run(full=False)
        self._publish_issues(self._merge(issues))

    def _refresh_file_system_checks(self) -> None:
        """Repeats the cheap file system checks after file operations and drops stale results."""
        pkg = self._pkg
        if pkg is None:
            return
        attached = [i for i in self._full_issues if i["checkId"] not in FILE_SYSTEM_CHECKS
                    and (not i["key"] or self._is_attached(pkg.element(i["key"])))]
        if self._had_full_run:
            validator = validation.Validator(pkg, self.validateSipName)
            for check in validation.CHECKS:
                if check.id in FILE_SYSTEM_CHECKS:
                    getattr(validator, "_check_" + check.id)()
            attached += validator.issues
        self._full_issues = attached

    def _is_attached(self, el) -> bool:
        return el is not None and el.getroottree().getroot() is self._pkg.root

    def resolve_issues(self, issues: list[dict]) -> None:
        """Removes issues handled by a fix-up from the cached results of the last full validation."""
        done = {(i.get("checkId"), i.get("key"), i.get("path")) for i in issues}
        self._full_issues = [i for i in self._full_issues if (i["checkId"], i["key"], i["path"]) not in done]

    def _publish_issues(self, issues: list[dict]) -> None:
        self.validationTable.set_records(issues)
        self.editor.set_validation(validation.summarize(issues), issues)
        self.validationChanged.emit()

    @Slot(int, result=bool)
    def isChecksumIssue(self, row: int) -> bool:
        return self.validationTable.recordAt(row).get("checkId") == "checksum"

    # ---------------------------------------------------------------- change tracking

    def after_change(self, description: str, key: int = 0, file_system: bool = False, rebuild: bool = True) -> None:
        """Common bookkeeping after structural edits; file system changes are saved immediately."""
        pkg = self._pkg
        if pkg is None:
            return
        pkg.invalidate_file_index()
        if description:
            el = pkg.element(key) if key else None
            self._record_change(key, schema.KIND_LABELS.get(pkg.kind(el), "") if el is not None else "Paket",
                                pkg.display_name(el) if el is not None and self._is_attached(el) else "",
                                "Struktur", "", description)
        if file_system:
            try:
                pkg.save()
                self._set_dirty(False)
            except OSError as exc:
                self.message.emit("Speichern fehlgeschlagen", str(exc))
                self._set_dirty(True)
            self._refresh_file_system_checks()
        else:
            self._set_dirty(True)
        self._full_issues = [i for i in self._full_issues if not i["key"] or self._is_attached(pkg.element(i["key"]))]
        if rebuild:
            self.rebuild_navigators()
        self.editor.forget_missing()
        self.editor.refresh()
        self._refresh_notes()
        self._run_continuous_validation()
        self._set_status(description or self._status)

    def _on_field_edited(self, key: int, kind: str, name: str, field: str, old: str, new: str) -> None:
        self._record_change(key, kind, name, field, old, new)
        pkg = self._pkg
        el = pkg.element(key)
        if el is not None:
            label = pkg.display_name(el)
            for model in (self.classificationModel, self.dossierModel, self.packageModel):
                model.update_label(key, label)
        self._set_dirty(True)
        self._run_continuous_validation()
        self.editor.refresh()

    def _record_change(self, key: int, kind: str, name: str, field: str, old: str, new: str) -> None:
        self.changesTable.append({
            "time": datetime.now().strftime("%d.%m.%Y %H:%M:%S"), "object": kind, "objectName": name,
            "field": field, "oldValue": old, "newValue": new, "key": key,
        })

    def _refresh_notes(self) -> None:
        self.notesTable.set_records(notes.all_notes(self._pkg) if self._pkg is not None else [])

    # ---------------------------------------------------------------- editing helpers

    @Slot()
    def accumulateTimeSpans(self) -> None:
        """Extras > Zeiträume auf Ablieferung kumulieren."""
        pkg = self.require_writable()
        if pkg is None:
            return
        start, end = structure.accumulate_time_spans(pkg, pkg.delivery)
        if not start and not end:
            self.message.emit("Zeiträume kumulieren", "Es sind keine Zeitraumangaben auf Stufe Dossier vorhanden.")
            return
        self.after_change("Zeiträume auf Ablieferung kumuliert", pkg.key(pkg.delivery), rebuild=False)

    # ---------------------------------------------------------------- state helpers

    def _set_dirty(self, value: bool) -> None:
        if self._dirty != value:
            self._dirty = value
            self.dirtyChanged.emit()

    def _set_busy(self, value: bool) -> None:
        if self._busy != value:
            self._busy = value
            self.busyChanged.emit()

    def _set_status(self, text: str) -> None:
        self._status = text
        self.statusChanged.emit()

    def set_status(self, text: str) -> None:
        self._set_status(text)

    def shutdown(self) -> None:
        self.cancelTask()


SIMPLE_SEARCH_COLUMNS = [("object", "Objekt"), ("objectName", "Objektname"), ("field", "Metadatum"), ("value", "Wert")]
