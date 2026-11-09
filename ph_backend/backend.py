"""Core application controller: package lifecycle, models, validation and change tracking."""

import csv
import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from datetime import datetime, timezone

from lxml import etree
from PySide6.QtCore import Property, QObject, QSettings, QThread, QUrl, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

from . import navigators, notes, sampling, schema, search, structure, validation
from .editor import MetadataEditor
from .navigators import NavigatorModel
from .sip import InvalidPackageError, SipPackage, localname
from .tables import RecordTableModel
from .audit import AuditError, AuditJournal
from .workspace import MetadataWorkspace, companion_directory, metadata_changes
from .file_workspace import (FileWorkspace, UnchangedOperation, file_changes, has_file_draft,
                             manifest, recover_file_commit, remove_staging_tree)
from .undo import UndoHistory
from .retention import RetentionManager
from .processing import (TaskCancelled, TaskControl, copy_tree, critical_section, digest_file,
                         processing_context, read_bytes, run_background)
from .qt_processing import io_task

MAX_RECENT = 3
# Checks that only scan the file system / metadata and are cheap enough to repeat after file operations.
FILE_SYSTEM_CHECKS = {"illegal_entries", "header_content", "wrong_file", "wrong_folder", "missing_file",
                      "missing_folder", "surplus_file", "surplus_folder", "file_format", "identical_files",
                      "positions_and_dossiers", "sip_name", "package_size", "folder_level"}
DROID_FORMAT_CHECK = "droid_format"
_AUDIT_ENTITY_KINDS = {"dossier", "subdossier", "mappe", "dokument", "archivischerVorgang",
                       "archivischeNotiz", "ordnungssystemposition"}


def _deleted_objects(detail: dict) -> list[dict]:
    xml_changes = detail.get("xmlChanges", []) + detail.get("changes", [])
    by_path = {change.get("path"): change for change in xml_changes
               if isinstance(change, dict) and isinstance(change.get("path"), str)}
    deleted = {}
    for change in by_path.values():
        path = change["path"]
        identifier = change.get("oldValue")
        if (not path.endswith("/@id") or not identifier or change.get("newValue") is not None):
            continue
        object_path = path[:-4]
        kind = object_path.rsplit("/", 1)[-1].split("[", 1)[0]
        if kind not in _AUDIT_ENTITY_KINDS:
            continue
        label = next((by_path.get(object_path + "/" + field + "/text()", {}).get("oldValue")
                      for field in ("titel", "name", "nummer")
                      if by_path.get(object_path + "/" + field + "/text()", {}).get("oldValue")), kind)
        deleted["metadata:" + str(identifier)] = {
            "kind": kind, "identifier": str(identifier), "label": str(label), "path": object_path,
        }

    file_changes = detail.get("fileChanges", [])
    if detail.get("scope") == "package-files":
        file_changes = file_changes + detail.get("changes", [])
    for change in file_changes:
        if not isinstance(change, dict) or not isinstance(change.get("before"), dict) or change.get("after") is not None:
            continue
        state = change["before"]
        if state.get("type") not in ("file", "directory"):
            continue
        path = change.get("path", "")
        deleted["filesystem:" + path] = {"kind": state["type"], "label": path.rsplit("/", 1)[-1], "path": path}
    return [deleted[key] for key in sorted(deleted, key=lambda key: (key.startswith("filesystem:"), key))]


def _history_change_summary(detail: dict) -> list[dict]:
    summary = []
    xml_changes = detail.get("xmlChanges", [])
    if detail.get("scope") != "package-files":
        xml_changes = xml_changes + detail.get("changes", [])
    for change in xml_changes:
        if not isinstance(change, dict) or not isinstance(change.get("path"), str):
            continue
        path = change["path"]
        if "oldValue" not in change and "newValue" not in change:
            continue
        field = path.rsplit("/", 1)[-1]
        if field == "text()":
            field = path.rsplit("/", 2)[-2]
        elif field.startswith("@"):
            field = field[1:]
        summary.append({"path": path, "field": field,
                        "before": change.get("oldValue"), "after": change.get("newValue")})

    if ("oldValue" in detail or "newValue" in detail) and (detail.get("path") or detail.get("field")):
        summary.append({"path": detail.get("path", ""), "field": detail.get("field", ""),
                        "before": detail.get("oldValue"), "after": detail.get("newValue")})

    file_changes = detail.get("fileChanges", [])
    if detail.get("scope") == "package-files":
        file_changes = file_changes + detail.get("changes", [])
    for change in file_changes:
        if not isinstance(change, dict) or not isinstance(change.get("path"), str):
            continue
        summary.append({"path": change["path"], "field": "Dateiinhalt",
                        "before": change.get("before"), "after": change.get("after")})
    return summary


def _write_export_file(path: Path, data: bytes, exclusive: bool = False) -> None:
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive and path.exists():
            raise FileExistsError(path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _build_audit_bundle(root: Path, journal_path: Path, destination: Path,
                        redact_values: bool, mets_version: str,
                        operator: str, software_version: str) -> dict:
    root = Path(root).resolve()
    journal_path = Path(journal_path)
    destination = Path(destination).resolve()
    companion = root.with_name(root.name + ".package-turbo").resolve()
    if not destination.is_dir():
        raise AuditError("Choose an existing export directory.")
    if (destination == root or destination.is_relative_to(root)
            or destination == companion or destination.is_relative_to(companion)):
        raise AuditError("The export directory cannot be inside the SIP or its companion.")
    if not journal_path.is_file():
        raise AuditError("The preservation journal does not exist.")
    export_directory = destination / f"{root.name}.package-turbo-export"
    if export_directory.exists():
        raise AuditError(f"Export directory already exists: {export_directory}")

    archive_name = root.name + ".zip"
    premis_name = root.name + ".premis.xml"
    mets_name = root.name + ".mets.xml"
    original_manifest = manifest(root)
    temporary_root = Path(tempfile.mkdtemp(prefix=".package-turbo-export-", dir=destination))
    try:
        snapshot = temporary_root / root.name
        copy_tree(root, snapshot)
        if manifest(snapshot) != original_manifest or manifest(root) != original_manifest:
            raise AuditError("The SIP changed while the export snapshot was being created.")

        archive = temporary_root / archive_name
        SipPackage.open_folder(snapshot, read_only=True).zip_to(archive)
        archive_digest = digest_file(archive, "sha256")

        journal = AuditJournal(journal_path)
        checkpoint = journal.verify()
        metadata_xml = (snapshot / "header" / "metadata.xml").read_bytes()
        premis_data = journal.premis_xml(redact_values=redact_values, metadata_xml=metadata_xml,
                                         sip_manifest=original_manifest)
        mets_data = journal.mets_xml(archive_name, archive_digest, premis_filename=premis_name,
                                     version=mets_version, redact_values=redact_values,
                                     metadata_xml=metadata_xml, sip_manifest=original_manifest)
        if journal.verify() != checkpoint:
            raise AuditError("The preservation journal changed during export.")

        output = temporary_root / "output"
        output.mkdir()
        os.replace(archive, output / archive_name)
        _write_export_file(output / premis_name, premis_data, exclusive=True)
        _write_export_file(output / mets_name, mets_data, exclusive=True)
        with critical_section(check_cancel=False):
            if export_directory.exists():
                raise AuditError(f"Export directory already exists: {export_directory}")
            os.rename(output, export_directory)
            audit_error = ""
            try:
                journal.append("preservation export", agent_identifier=operator,
                               software_version=software_version,
                               detail={"scope": "sip-companion-export", "format": "SIP ZIP + PREMIS 3.0 + METS",
                                       "metsVersion": mets_version, "redacted": redact_values,
                                       "sipSha256": archive_digest, "sourceSequence": checkpoint.sequence,
                                       "sourceDigest": checkpoint.digest})
            except (AuditError, OSError) as exc:
                audit_error = str(exc)
        return {"directory": export_directory, "auditError": audit_error}
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


class ValidationWorker(QThread):
    progressChanged = Signal(int)
    bytesChanged = Signal(str, "qlonglong", "qlonglong")

    def __init__(self, validator: validation.Validator, full: bool, parent=None):
        super().__init__(parent)
        pkg = validator.pkg
        self._snapshot_xml = etree.tostring(pkg.tree, encoding="UTF-8", xml_declaration=True)
        self._metadata_path = pkg.metadata_path
        self._root_dir = pkg.root_dir
        self._file_root = pkg.file_root
        self._validate_sip_name = validator.validate_sip_name
        self._identify_formats = validator.identify_formats
        self._validator = None
        self.control = TaskControl(self.bytesChanged.emit)
        self.cancelled = False
        self._full = full
        self.result: list[dict] = []
        self.error = ""

    def run(self):
        try:
            with processing_context(self.control):
                parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
                tree = etree.ElementTree(etree.fromstring(self._snapshot_xml, parser))
                pkg = SipPackage(self._metadata_path, tree, self._root_dir, read_only=True)
                pkg.file_root = self._file_root
                self._validator = validation.Validator(
                    pkg, self._validate_sip_name, identify_formats=self._identify_formats)
                self.result = self._validator.run(self._full, self.progressChanged.emit, self.isInterruptionRequested)
                self.cancelled = self.control.cancel_requested or self.isInterruptionRequested()
                for issue in self.result:
                    element = pkg.element(issue["key"]) if issue["key"] else None
                    issue["_snapshotPath"] = pkg.tree.getpath(element) if element is not None else ""
        except TaskCancelled:
            self.cancelled = True
            self.requestInterruption()
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
    historyChanged = Signal()
    auditOperatorRequired = Signal()
    undoChanged = Signal()
    taskStateChanged = Signal()
    retentionChanged = Signal()

    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self._settings = settings
        app = QGuiApplication.instance()
        self._style_hints = app.styleHints() if app is not None else None
        if self._style_hints is not None:
            self._style_hints.colorSchemeChanged.connect(lambda _scheme: self.settingsChanged.emit())
        self._pkg: SipPackage | None = None
        self._dirty = False
        self._busy = False
        self._io_active = False
        self._io_waiting = False
        self._task_control = None
        self._io_completed = self._io_total = 0
        self._progress = 0
        self._status = "Bereit"
        self._worker: ValidationWorker | None = None
        self._validation_operator = ""
        self._full_issues: list[dict] = []
        self._had_full_run = False
        self._classification_filter = "all"
        self._package_filter = "all"
        self._validation_filter = ""
        self._history_search = ""
        self._history_event_filter = ""
        self._history_outcome_filter = ""
        self._workspace: MetadataWorkspace | None = None
        self._file_workspace: FileWorkspace | None = None
        self._undo_history: UndoHistory | None = None
        self._undo_pending = None
        self._undo_identifier = ""
        self._retention_manager = None
        self._retention_preview = None
        self._pending_audit: list[dict] = []
        self._software_version = QGuiApplication.applicationVersion() or "development"
        self._opened_metadata: bytes | None = None

        self.classificationModel = NavigatorModel(["Ordnungssystem"], self)
        self.dossierModel = NavigatorModel(["Titel", "Aktenzeichen", "Entstehungszeitraum", "Erscheinungsform"], self)
        self.packageModel = NavigatorModel(["Paket"], self)
        self.editor = MetadataEditor(self)
        self.editor.edit_guard = self._edit_allowed
        self.editor.edit_operation = self.apply_editor_operation
        self.validationTable = RecordTableModel([
            ("severityLabel", "I"), ("object", "Objekt"), ("objectName", "Objektname"), ("check", "Prüfung"),
            ("description", "Beschreibung"), ("field", "Metadatum"), ("value", "Wert"),
        ], self)
        self.changesTable = RecordTableModel([
            ("time", "Zeit"), ("object", "Objekt"), ("objectName", "Objektname"), ("field", "Metadatum"),
            ("newValue", "Wert"), ("oldValue", "Gespeicherter Wert"),
        ], self)
        self.historyTable = RecordTableModel([
            ("time", "Zeit (UTC)"), ("eventType", "Ereignis"), ("operator", "Bearbeitet durch"),
            ("outcome", "Ergebnis"), ("field", "Metadatum"), ("oldValue", "Alter Wert"), ("newValue", "Neuer Wert"),
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
        if self._gui_blocked():
            self.message.emit("Vorgang läuft", "Während der Validierung kann das Paket nicht bearbeitet werden.")
            return None
        if not self._ensure_workspace():
            return None
        return self._pkg

    def _gui_blocked(self) -> bool:
        return self._busy and (not self._io_active or self._io_waiting)

    def _edit_allowed(self) -> bool:
        if self._pkg is None or self._pkg.read_only or self._gui_blocked():
            return False
        if not self.auditOperator:
            self.auditOperatorRequired.emit()
            return False
        return True

    @Property(bool, notify=taskStateChanged)
    def canCancelTask(self) -> bool:
        if self._task_control is not None:
            return self._task_control.can_cancel
        return self._busy and self._worker is not None and not self._worker.isInterruptionRequested()

    @Property("qlonglong", notify=progressChanged)
    def completedBytes(self) -> int:
        return self._io_completed

    @Property("qlonglong", notify=progressChanged)
    def totalBytes(self) -> int:
        return self._io_total

    def _on_io_progress(self, phase: str, completed: int, total: int):
        if not self._io_active:
            return
        self._io_completed, self._io_total = completed, total
        self._progress = min(100, int(completed * 100 / total)) if total else 0
        self._set_status(phase)
        self.progressChanged.emit()

    def _on_io_state(self):
        self.taskStateChanged.emit()

    def _ensure_workspace(self) -> bool:
        pkg = self._pkg
        if pkg is None or pkg.read_only or pkg.root_dir is None:
            return False
        if not self.auditOperator:
            self.auditOperatorRequired.emit()
            return False
        try:
            if self._workspace is None:
                if read_bytes(pkg.metadata_path) != self._opened_metadata:
                    raise AuditError("Metadata changed since the package was opened. Reopen before editing.")
                self._workspace = MetadataWorkspace(pkg.metadata_path, pkg.root_dir, operator=self.auditOperator,
                                                    software_version=self._software_version)
                if self._workspace.journal.verify().sequence == 0:
                    initial_manifest = manifest(pkg.root_dir)
                    self._workspace.check()
                    self._workspace.journal.append(
                        "package registration", agent_identifier=self.auditOperator,
                        software_version=self._software_version,
                        detail={"packageName": pkg.name, "schemaVersion": pkg.root.get("schemaVersion", ""),
                                "deliveryType": pkg.delivery_type,
                                "metadataSha256": hashlib.sha256(read_bytes(pkg.metadata_path)).hexdigest(),
                                "manifest": initial_manifest,
                                "note": "Current package state registered; earlier history is unknown."})
            self._workspace.operator = self.auditOperator
            self._workspace.check()
            if self._file_workspace is not None:
                self._file_workspace.operator = self.auditOperator
                self._file_workspace.max_bytes = self.workspaceLimitGiB * 1024 ** 3
                self._file_workspace.check()
            elif has_file_draft(self._workspace.journal):
                raise AuditError("A staged package is available. Recover it before editing or saving.")
            self._refresh_history()
            return True
        except TaskCancelled:
            raise
        except (AuditError, OSError) as exc:
            self.message.emit("Metadaten-Historie", str(exc))
            return False

    def _get_audit_operator(self) -> str:
        return str(self.setting("audit/operator", "")).strip()

    def _set_audit_operator(self, value: str) -> None:
        self.set_setting("audit/operator", value.strip())

    auditOperator = Property(str, _get_audit_operator, _set_audit_operator, notify=settingsChanged)

    def _get_workspace_limit(self) -> int:
        return max(1, min(1024, self.setting("audit/workspaceLimitGiB", 32)))

    def _set_workspace_limit(self, value: int) -> None:
        self.set_setting("audit/workspaceLimitGiB", max(1, min(1024, value)))

    workspaceLimitGiB = Property(int, _get_workspace_limit, _set_workspace_limit, notify=settingsChanged)

    def _get_retention_count(self) -> int:
        return max(1, min(100, self.setting("storage/keepCopies", 3)))

    def _set_retention_count(self, value: int):
        self.set_setting("storage/keepCopies", max(1, min(100, value)))

    retentionCopies = Property(int, _get_retention_count, _set_retention_count, notify=settingsChanged)

    def _get_retention_age(self) -> int:
        return max(0, min(3650, self.setting("storage/minimumAgeDays", 7)))

    def _set_retention_age(self, value: int):
        self.set_setting("storage/minimumAgeDays", max(0, min(3650, value)))

    retentionAgeDays = Property(int, _get_retention_age, _set_retention_age, notify=settingsChanged)

    @Property("QVariantList", notify=retentionChanged)
    def retentionCandidates(self) -> list:
        return self._retention_preview["candidates"] if self._retention_preview else []

    @Property("qlonglong", notify=retentionChanged)
    def retentionBytes(self) -> int:
        return self._retention_preview["reclaimBytes"] if self._retention_preview else 0

    @Property(int, notify=retentionChanged)
    def retentionProtectedCount(self) -> int:
        return len(self._retention_preview["protected"]) if self._retention_preview else 0

    @Slot(result=bool)
    @io_task(False)
    def previewRetentionCleanup(self) -> bool:
        if self.require_writable() is None:
            return False
        try:
            self._retention_manager = RetentionManager(self._workspace)
            self._retention_preview = self._retention_manager.preview(self.retentionCopies, self.retentionAgeDays)
        except TaskCancelled:
            raise
        except (AuditError, OSError) as exc:
            self._retention_preview = None
            self.message.emit("Speicherbereinigung", str(exc))
            self.retentionChanged.emit()
            return False
        self.retentionChanged.emit()
        return True

    @Slot(result=bool)
    @io_task(False)
    def applyRetentionCleanup(self) -> bool:
        if self.require_writable() is None or self._retention_manager is None or self._retention_preview is None:
            return False
        try:
            if (self._retention_preview["keepCount"] != self.retentionCopies
                    or self._retention_preview["minimumAgeDays"] != self.retentionAgeDays):
                raise AuditError("Retention settings changed. Review a new cleanup preview.")
            self._retention_manager.apply(self._retention_preview)
        except TaskCancelled:
            raise
        except (AuditError, OSError) as exc:
            self.message.emit("Speicherbereinigung", str(exc))
            self._refresh_history()
            return False
        self._retention_preview = None
        self.retentionChanged.emit()
        self._refresh_history()
        return True

    @io_task()
    def stage_file_operation(self, action):
        pkg = self.require_writable()
        if pkg is None:
            return None
        if self._file_workspace is None:
            self._file_workspace = FileWorkspace(self._workspace, self.workspaceLimitGiB * 1024 ** 3)
        if self._undo_history is None:
            self._undo_history = UndoHistory(self._workspace.directory, self.workspaceLimitGiB * 1024 ** 3)
        self._undo_history.max_bytes = self.workspaceLimitGiB * 1024 ** 3
        if self._undo_pending is not None:
            for snapshot in self._undo_pending:
                self._undo_history.release(snapshot)
            self._undo_pending = None
        snapshots = []
        selected = pkg.element(self.editor.currentKey)
        selected_identifier = selected.get("id", "") if selected is not None else ""
        operation_identifier = "urn:uuid:" + str(uuid.uuid4())
        event_count = len(self._pending_audit)
        try:
            snapshots.append(self._undo_history.capture(
                pkg.file_root, etree.tostring(pkg.tree, encoding="UTF-8", xml_declaration=True)))

            def run(package):
                result = action(package)
                snapshots.append(self._undo_history.capture(
                    package.file_root, etree.tostring(package.tree, encoding="UTF-8", xml_declaration=True)))
                if snapshots[0].files == snapshots[1].files and snapshots[0].xml == snapshots[1].xml:
                    raise UnchangedOperation(result)
                self._pending_audit.append({"event_type": "package operation", "operator": self.auditOperator,
                                           "detail": {"scope": "staged-package", "operationIdentifier": operation_identifier,
                                                      "operationDateTime": datetime.now(timezone.utc).isoformat(),
                                                      "xmlChanges": metadata_changes(snapshots[0].xml, snapshots[1].xml),
                                                      "fileChanges": file_changes(snapshots[0].files, snapshots[1].files)}})
                return result

            result = self._file_workspace.stage_operation(pkg, run, self._pending_audit)
            if snapshots[0].files == snapshots[1].files and snapshots[0].xml == snapshots[1].xml:
                for snapshot in snapshots:
                    self._undo_history.release(snapshot)
                if pkg.file_root == pkg.root_dir:
                    self._file_workspace = None
            else:
                self._undo_pending = tuple(snapshots)
                self._undo_identifier = operation_identifier
            return result
        except BaseException:
            del self._pending_audit[event_count:]
            for snapshot in snapshots:
                self._undo_history.release(snapshot)
            if pkg.file_root == pkg.root_dir:
                self._file_workspace = None
            self.rebuild_navigators()
            self.editor.set_package(pkg)
            self._full_issues = []
            self._had_full_run = False
            self._run_continuous_validation()
            self._restore_xml_selection(selected_identifier)
            raise

    def _restore_xml_selection(self, identifier: str):
        if identifier:
            selected = self._pkg.root.xpath("//*[@id=$identifier]", identifier=identifier)
            if selected:
                self.reveal(self._pkg.key(selected[0]))

    def apply_editor_operation(self, action) -> bool:
        try:
            result = self.stage_file_operation(lambda package: (action(package), True)[1])
            return result is True and self._undo_pending is not None
        except (AuditError, OSError) as exc:
            self.message.emit("Bearbeitung fehlgeschlagen", str(exc))
            return False

    def _finish_undo_operation(self, label: str) -> str:
        if self._undo_pending is None:
            return ""
        before, after = self._undo_pending
        self._undo_pending = None
        if self._undo_history.record(label, before, after, self._undo_identifier):
            self.undoChanged.emit()
            return self._undo_history.entries[-1].identifier
        return ""

    @Property(bool, notify=undoChanged)
    def canUndo(self) -> bool:
        return bool(self._undo_history and self._undo_history.can_undo and not self.readOnly and not self._busy)

    @Property(bool, notify=undoChanged)
    def canRedo(self) -> bool:
        return bool(self._undo_history and self._undo_history.can_redo and not self.readOnly and not self._busy)

    @Property(str, notify=undoChanged)
    def undoLabel(self) -> str:
        return self._undo_history.entries[self._undo_history.position - 1].label if self.canUndo else ""

    @Property(str, notify=undoChanged)
    def redoLabel(self) -> str:
        return self._undo_history.entries[self._undo_history.position].label if self.canRedo else ""

    def _reverse_operation(self, redo: bool) -> bool:
        available = self._undo_history and (self._undo_history.can_redo if redo else self._undo_history.can_undo)
        if not available or self.require_writable() is None:
            return False
        history = self._undo_history
        selected = self._pkg.element(self.editor.currentKey)
        selected_identifier = selected.get("id", "") if selected is not None else ""
        try:
            entry = history.redo_target() if redo else history.undo_target()
            snapshot = entry.after if redo else entry.before
            if self._file_workspace is None:
                self._file_workspace = FileWorkspace(self._workspace, self.workspaceLimitGiB * 1024 ** 3)
            event = {"event_type": "redo" if redo else "undo", "operator": self.auditOperator,
                     "detail": {"scope": "staged-package", "operationIdentifier": entry.identifier,
                                "reversesOperationIdentifier": entry.identifier, "label": entry.label,
                                "snapshotIdentifier": snapshot.identifier}}

            def restore(package):
                history.check(snapshot)
                remove_staging_tree(package.file_root)
                copy_tree(snapshot.directory, package.file_root)
                snapshot.restore_modes(package.file_root)
                package.restore_xml(snapshot.xml)

            self._file_workspace.stage_operation(self._pkg, restore, self._pending_audit + [event])
        except (AuditError, OSError) as exc:
            self.message.emit("Paket rückgängig", str(exc))
            self.rebuild_navigators()
            self.editor.set_package(self._pkg)
            self._full_issues = []
            self._had_full_run = False
            self._run_continuous_validation()
            self._restore_xml_selection(selected_identifier)
            return False
        self._pending_audit.append(event)
        history.position += 1 if redo else -1
        self.changesTable.append({"time": datetime.now().strftime("%d.%m.%Y %H:%M:%S"), "object": "Paket",
                                  "objectName": self._pkg.name, "field": "Redo" if redo else "Undo",
                                  "oldValue": "", "newValue": entry.label, "key": 0})
        self._set_dirty(True)
        self._full_issues = []
        self._had_full_run = False
        self.rebuild_navigators()
        self.editor.set_package(self._pkg)
        self._refresh_notes()
        self._run_continuous_validation()
        self._restore_xml_selection(selected_identifier)
        self._refresh_history()
        self.undoChanged.emit()
        return True

    @Slot(result=bool)
    @io_task(False)
    def undo(self) -> bool:
        return self._reverse_operation(False)

    @Slot(result=bool)
    @io_task(False)
    def redo(self) -> bool:
        return self._reverse_operation(True)

    @Slot()
    @io_task()
    def clearUndoHistory(self):
        self._clear_undo_history()

    def _clear_undo_history(self):
        if self._gui_blocked():
            return
        if self._undo_history is not None:
            try:
                self._undo_history.clear()
            except (AuditError, OSError) as exc:
                self.message.emit("Paket-Verlauf", str(exc))
                return
        self._undo_pending = None
        self._undo_identifier = ""
        self.undoChanged.emit()

    def _persist_file_draft(self):
        if self._file_workspace is None:
            return
        try:
            self._file_workspace.persist(self._pkg, self._pending_audit)
            self._refresh_history()
        except TaskCancelled:
            raise
        except (AuditError, OSError) as exc:
            self.message.emit("Arbeitskopie", str(exc))

    @Property(str, notify=historyChanged)
    def auditCompanion(self) -> str:
        return str(companion_directory(self._pkg.root_dir)) if self.hasSip else ""

    @Property(bool, notify=historyChanged)
    def hasHistory(self) -> bool:
        return self.historyTable.total > 0

    @Property(str, notify=historyChanged)
    def historySearch(self) -> str:
        return self._history_search

    @Property(str, notify=historyChanged)
    def historyEventFilter(self) -> str:
        return self._history_event_filter

    @Property(str, notify=historyChanged)
    def historyOutcomeFilter(self) -> str:
        return self._history_outcome_filter

    @Property("QVariantList", notify=historyChanged)
    def historyEventTypes(self) -> list:
        return sorted({row["eventType"] for row in self.historyTable.records()})

    @Slot(str)
    def setHistorySearch(self, value: str) -> None:
        self._history_search = value.strip()
        self._apply_history_filter()

    @Slot(str)
    def setHistoryEventFilter(self, value: str) -> None:
        self._history_event_filter = value.strip()
        self._apply_history_filter()

    @Slot(str)
    def setHistoryOutcomeFilter(self, value: str) -> None:
        self._history_outcome_filter = value.strip()
        self._apply_history_filter()

    def _apply_history_filter(self, emit: bool = True) -> None:
        search_text = self._history_search.casefold()
        event_type = self._history_event_filter
        outcome = self._history_outcome_filter

        def matches(row):
            if event_type and row["eventType"] != event_type:
                return False
            if outcome and row["outcome"] != outcome:
                return False
            searchable = " ".join(str(row.get(key, "")) for key in (
                "time", "eventType", "operator", "outcome", "field", "oldValue", "newValue",
                "eventIdentifier", "transactionIdentifier", "detail"))
            return not search_text or search_text in searchable.casefold()

        active = bool(search_text or event_type or outcome)
        self.historyTable.set_filter(matches if active else None)
        if emit:
            self.historyChanged.emit()

    def _refresh_history(self) -> None:
        records = []
        if self.hasSip:
            path = companion_directory(self._pkg.root_dir) / "journal.sqlite3"
            if path.exists():
                try:
                    records = AuditJournal(path, read_only=True).records()
                except AuditError as exc:
                    self.message.emit("Metadaten-Historie", str(exc))
        rows = []
        for record in records:
            payload = record["payload"]
            detail = payload["detail"]
            rows.append({"time": payload["eventDateTime"], "eventType": payload["eventType"],
                         "operator": payload["agentIdentifier"], "outcome": payload["outcome"],
                         "field": detail.get("field", ""), "oldValue": detail.get("oldValue", ""),
                         "newValue": detail.get("newValue", ""), "eventIdentifier": payload["eventIdentifier"],
                         "detail": detail, "transactionIdentifier": payload["transactionIdentifier"],
                         "key": 0})
        self.historyTable.set_records(rows)
        self._apply_history_filter(emit=False)
        self.historyChanged.emit()

    @Slot(int, result=str)
    def historyDetails(self, row: int) -> str:
        import json

        record = self.historyTable.recordAt(row)
        if not record:
            return ""
        details = dict(record)
        details["deletedObjects"] = _deleted_objects(record.get("detail", {}))
        details["changeSummary"] = _history_change_summary(record.get("detail", {}))
        return json.dumps(details, ensure_ascii=False, indent=2)

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

    def _get_theme_mode(self) -> str:
        value = str(self.setting("ui/theme", "system")).lower()
        return value if value in ("system", "light", "dark") else "system"

    def _set_theme_mode(self, value: str) -> None:
        self.set_setting("ui/theme", value if value in ("system", "light", "dark") else "system")

    themeMode = Property(str, _get_theme_mode, _set_theme_mode, notify=settingsChanged)

    def _get_show_incoming_file_references(self) -> bool:
        return bool(self.setting("ui/showIncomingFileReferences", False))

    def _set_show_incoming_file_references(self, value: bool) -> None:
        self.set_setting("ui/showIncomingFileReferences", bool(value))

    showIncomingFileReferences = Property(bool, _get_show_incoming_file_references,
                                         _set_show_incoming_file_references, notify=settingsChanged)

    @Property(str, notify=settingsChanged)
    def systemTheme(self) -> str:
        app = QGuiApplication.instance()
        if app is None:
            return "light"
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        if scheme == Qt.ColorScheme.Light:
            return "light"
        return "dark" if app.palette().window().color().lightnessF() < 0.5 else "light"

    # ---------------------------------------------------------------- opening / closing

    @Slot(QUrl, bool)
    @io_task()
    def openPackage(self, url: QUrl, read_only: bool = False) -> None:
        self._open(lambda: self._load_folder(url.toLocalFile(), read_only))

    @Slot(str)
    @io_task()
    def openRecent(self, path: str) -> None:
        self._open(lambda: self._load_folder(path, False))

    def _load_folder(self, path, read_only):
        if not read_only:
            recover_file_commit(Path(path), self.auditOperator, self._software_version)
        return SipPackage.open_folder(path, read_only)

    @Slot(QUrl)
    @io_task()
    def openMetadata(self, url: QUrl) -> None:
        self._open(lambda: SipPackage.open_metadata(url.toLocalFile()))

    def _open(self, loader) -> None:
        try:
            pkg = loader()
        except TaskCancelled:
            raise
        except (InvalidPackageError, AuditError, OSError) as exc:
            self.message.emit("Paket kann nicht geöffnet werden", str(exc))
            return
        if not self.set_package(pkg):
            return
        self._set_status(f"Paket {pkg.name} geöffnet" + (" (schreibgeschützt)" if pkg.read_only else ""))
        self.packageOpened.emit()

    def set_package(self, pkg: SipPackage | None) -> bool:
        if self._gui_blocked():
            return False
        opened_metadata = read_bytes(pkg.metadata_path) if pkg is not None else None
        if pkg is not None:
            current_xml = etree.tostring(pkg.tree, encoding="UTF-8", xml_declaration=True)

            def unchanged_metadata():
                parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
                parsed = etree.fromstring(opened_metadata, parser)
                original = etree.fromstring(current_xml, parser)
                return etree.tostring(parsed, method="c14n") == etree.tostring(original, method="c14n")

            if not run_background(unchanged_metadata, "Check opened metadata"):
                self.message.emit("Paket öffnen", "Metadata changed while the package was opened. Reopen before editing.")
                return False
        with critical_section():
            return self._set_package_state(pkg, opened_metadata)

    def recordCreatedPackage(self, pkg: SipPackage) -> bool:
        if not self.auditOperator.strip():
            self.auditOperatorRequired.emit()
            self.message.emit("Neues Paket", "Bestätigen Sie die Identität, um die Paketerstellung zu protokollieren.")
            return False
        if self._busy or self._dirty:
            return False
        try:
            initial_manifest = manifest(pkg.root_dir)
            workspace = MetadataWorkspace(pkg.metadata_path, pkg.root_dir, operator=self.auditOperator,
                                          software_version=self._software_version)
            workspace.journal.append(
                "package creation", agent_identifier=self.auditOperator, software_version=self._software_version,
                detail={"packageName": pkg.name, "schemaVersion": pkg.root.get("schemaVersion", ""),
                        "deliveryType": pkg.delivery_type, "manifest": initial_manifest})
            if not self.set_package(pkg):
                return False
            self._workspace = workspace
            self._refresh_history()
            return True
        except (AuditError, OSError) as exc:
            self.message.emit("Paketerstellung protokollieren fehlgeschlagen", str(exc))
            return False

    def _set_package_state(self, pkg, opened_metadata):
        if not self._discard_current():
            return False
        self._cancel_validation()
        self._clear_undo_history()
        self._undo_history = None
        self._retention_preview = None
        self._retention_manager = None
        self.retentionChanged.emit()
        self._pkg = pkg
        self._opened_metadata = opened_metadata
        self._workspace = None
        self._file_workspace = None
        self._pending_audit = []
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
        self._refresh_history()
        return True

    def _discard_current(self) -> bool:
        if self._file_workspace is not None:
            try:
                self._file_workspace.operator = self.auditOperator
                self._file_workspace.discard()
            except (AuditError, OSError) as exc:
                self.message.emit("Verwerfen fehlgeschlagen", str(exc))
                return False
            self._file_workspace = None
            self._pkg.file_root = self._pkg.root_dir
            self._pending_audit = []
        if self._workspace is not None and self._pending_audit:
            try:
                self._workspace.operator = self.auditOperator
                self._workspace.discard(self._pending_audit)
            except (AuditError, OSError) as exc:
                self.message.emit("Verwerfen fehlgeschlagen", str(exc))
                return False
        self._pending_audit = []
        return True

    @Slot(result=bool)
    @io_task(False)
    def discardChanges(self) -> bool:
        if self._pkg is None:
            return True
        if not self._discard_current():
            return False
        try:
            pkg = SipPackage.open_metadata(self._pkg.metadata_path)
        except (InvalidPackageError, OSError) as exc:
            self.message.emit("Verwerfen fehlgeschlagen", str(exc))
            return False
        pkg.read_only = pkg.read_only or self._pkg.read_only
        return self.set_package(pkg)

    @Slot(result=bool)
    @io_task(False)
    def recoverMetadata(self) -> bool:
        if self._pkg is None or self._pkg.read_only:
            return False
        if not self.auditOperator:
            self.auditOperatorRequired.emit()
            return False
        try:
            recover_file_commit(self._pkg.root_dir, self.auditOperator, self._software_version)
            self._workspace = MetadataWorkspace(self._pkg.metadata_path, self._pkg.root_dir,
                                                operator=self.auditOperator, software_version=self._software_version)
            pkg = SipPackage.open_metadata(self._pkg.metadata_path)
        except TaskCancelled:
            raise
        except (AuditError, OSError, InvalidPackageError) as exc:
            self.message.emit("Wiederherstellung fehlgeschlagen", str(exc))
            return False
        self._pending_audit = []
        self._file_workspace = None
        workspace = self._workspace
        if not self.set_package(pkg):
            return False
        if has_file_draft(workspace.journal):
            self._workspace = workspace
            self._file_workspace = FileWorkspace(workspace, self.workspaceLimitGiB * 1024 ** 3)
            try:
                self._pending_audit = self._file_workspace.restore(pkg)
            except TaskCancelled:
                self._file_workspace = None
                raise
            except (AuditError, OSError) as exc:
                self.message.emit("Wiederherstellung fehlgeschlagen", str(exc))
                self._file_workspace = None
                return False
            self._set_dirty(True)
            self.changesTable.set_records([
                {"time": "", "object": event["detail"].get("object", ""),
                 "objectName": event["detail"].get("objectName", ""),
                 "field": event["detail"].get("field", ""),
                 "oldValue": event["detail"].get("oldValue", ""),
                 "newValue": event["detail"].get("newValue", ""), "key": 0}
                for event in self._pending_audit])
            self.rebuild_navigators()
            self.editor.set_package(pkg)
            self._run_continuous_validation()
        return True

    @Slot()
    @io_task()
    def closePackage(self) -> None:
        if self._pkg is not None:
            if self.set_package(None):
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
    @io_task(False)
    def save(self) -> bool:
        if self.require_writable() is None:
            return False
        try:
            data = etree.tostring(self._pkg.tree, encoding="UTF-8", xml_declaration=True)
            if self._file_workspace is not None:
                self._file_workspace.commit(self._pkg, self._pending_audit)
                self._file_workspace = None
            else:
                self._workspace.save(data, self._pending_audit)
        except TaskCancelled:
            raise
        except (OSError, AuditError) as exc:
            self.message.emit("Speichern fehlgeschlagen", str(exc))
            self._refresh_history()
            return False
        self._pending_audit = []
        self._opened_metadata = read_bytes(self._pkg.metadata_path)
        self._set_dirty(False)
        # The view 'Änderungen' only lists changes since the last save.
        self.changesTable.set_records([])
        self._set_status("Paket gespeichert")
        self._refresh_history()
        return True

    @Slot(QUrl)
    def zipPackage(self, url: QUrl) -> None:
        if self._pkg is None:
            return
        if self._dirty:
            self.message.emit("Export", "Bitte speichern Sie das Paket vor dem Export.")
            return
        try:
            self._pkg.zip_to(url.toLocalFile())
            self._set_status(f"Paket gezippt: {url.toLocalFile()}")
        except (OSError, InvalidPackageError) as exc:
            self.message.emit("Paket zippen fehlgeschlagen", str(exc))

    @Slot(QUrl, bool)
    @io_task(False)
    def exportPremis(self, url: QUrl, redact_values: bool) -> None:
        pkg = self._pkg
        if pkg is None or pkg.root_dir is None:
            return
        if not self.auditOperator.strip():
            self.auditOperatorRequired.emit()
            return
        if self._dirty or pkg.file_root != pkg.root_dir:
            self.message.emit("PREMIS-Export", "Bitte speichern Sie das Paket vor dem Export.")
            return
        destination = Path(url.toLocalFile())
        journal_path = companion_directory(pkg.root_dir) / "journal.sqlite3"
        try:
            resolved_destination = destination.resolve()
            sip_root = Path(pkg.root_dir).resolve()
            companion = companion_directory(pkg.root_dir).resolve()
            if (not destination.name or resolved_destination.is_relative_to(sip_root)
                    or resolved_destination.is_relative_to(companion)):
                raise AuditError("Choose a PREMIS export file outside the SIP and its companion.")

            def export():
                journal = AuditJournal(journal_path)
                checkpoint = journal.verify()
                metadata_xml = pkg.metadata_path.read_bytes()
                sip_manifest = manifest(pkg.root_dir)
                if sip_manifest.get("header/metadata.xml", {}).get("sha256") != hashlib.sha256(metadata_xml).hexdigest():
                    raise AuditError("The SIP changed while the PREMIS export snapshot was being created.")
                data = journal.premis_xml(redact_values=redact_values, metadata_xml=metadata_xml,
                                          sip_manifest=sip_manifest)
                if manifest(pkg.root_dir) != sip_manifest:
                    raise AuditError("The SIP changed while the PREMIS export was being created.")
                if journal.verify() != checkpoint:
                    raise AuditError("The preservation journal changed during PREMIS export.")
                with critical_section(check_cancel=False):
                    _write_export_file(destination, data)
                    try:
                        journal.append("preservation export", agent_identifier=self.auditOperator,
                                       software_version=self._software_version,
                                       detail={"scope": "companion-export", "format": "PREMIS 3.0",
                                               "redacted": redact_values,
                                               "sourceSequence": checkpoint.sequence,
                                               "sourceDigest": checkpoint.digest})
                        return ""
                    except (AuditError, OSError) as exc:
                        return str(exc)

            audit_error = run_background(export, "Export PREMIS")
            self._set_status(f"PREMIS exportiert: {destination}")
            self._refresh_history()
            if audit_error:
                self.message.emit("PREMIS exportiert, aber Exportereignis nicht protokolliert", audit_error)
        except TaskCancelled:
            raise
        except (AuditError, OSError) as exc:
            self.message.emit("PREMIS-Export fehlgeschlagen", str(exc))

    @Slot(QUrl, bool, str)
    @io_task(False)
    def exportAuditBundle(self, url: QUrl, redact_values: bool, mets_version: str) -> None:
        pkg = self._pkg
        if pkg is None or pkg.root_dir is None:
            return
        if self._dirty or pkg.file_root != pkg.root_dir:
            self.message.emit("METS/PREMIS-Export", "Bitte speichern Sie das Paket vor dem Export.")
            return
        if not self.auditOperator.strip():
            self.auditOperatorRequired.emit()
            return
        destination = Path(url.toLocalFile())
        journal_path = companion_directory(pkg.root_dir) / "journal.sqlite3"
        try:
            export_directory = run_background(
                lambda: _build_audit_bundle(pkg.root_dir, journal_path, destination,
                                            redact_values, mets_version, self.auditOperator,
                                            self._software_version),
                "Export SIP with METS/PREMIS")
            self._set_status(f"SIP/METS/PREMIS exportiert: {export_directory['directory']}")
            self._refresh_history()
            if export_directory["auditError"]:
                self.message.emit("Export erstellt, aber Exportereignis nicht protokolliert",
                                  export_directory["auditError"])
        except TaskCancelled:
            raise
        except (AuditError, InvalidPackageError, OSError, ValueError) as exc:
            self.message.emit("METS/PREMIS-Export fehlgeschlagen", str(exc))

    @Slot(QUrl)
    def exportMetadata(self, url: QUrl) -> None:
        if self._pkg is None:
            return
        if self._dirty:
            self.message.emit("Export", "Bitte speichern Sie das Paket vor dem Export.")
            return
        try:
            self._pkg.export_metadata(url.toLocalFile())
            self._set_status(f"metadata.xml exportiert: {url.toLocalFile()}")
        except OSError as exc:
            self.message.emit("Export fehlgeschlagen", str(exc))

    def _table(self, which: str) -> RecordTableModel | None:
        return {"validation": self.validationTable, "changes": self.changesTable, "search": self.searchTable,
            "notes": self.notesTable, "sample": self.sampleTable, "history": self.historyTable}.get(which)

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
        self._validation_operator = ""
        if self._pkg.root_dir is not None:
            if not self.auditOperator.strip():
                self.auditOperatorRequired.emit()
                self.message.emit("Validierung", "Bestätigen Sie die Identität und starten Sie die Validierung erneut.")
                return
            self._validation_operator = self.auditOperator
        validator = validation.Validator(self._pkg, self.validateSipName, identify_formats=full)
        self._worker = ValidationWorker(validator, full, self)
        self._task_control = self._worker.control
        self._worker.control.state_changed = self.taskStateChanged.emit
        self._worker.progressChanged.connect(self._on_progress)
        self._worker.bytesChanged.connect(self._on_validation_bytes)
        self._worker.finished.connect(lambda: self._on_validation_finished(full))
        self._progress = 0
        self._io_completed = self._io_total = 0
        self.progressChanged.emit()
        self._set_busy(True)
        self._set_status("Paket wird validiert ...")
        self._worker.start()

    @Slot()
    def cancelTask(self) -> None:
        if self._task_control is not None:
            if self._task_control.cancel():
                self._set_status("Abbrechen ...")
                if self._worker is not None and self._worker.isRunning():
                    self._worker.requestInterruption()
            self.taskStateChanged.emit()
            return
        self._cancel_validation()

    def _cancel_validation(self):
        if self._worker is not None and self._worker.isRunning():
            self._worker.control.cancel()
            self._set_status("Abbrechen ...")
            self._worker.requestInterruption()
            self.taskStateChanged.emit()

    def _on_progress(self, value: int) -> None:
        self._progress = value
        self.progressChanged.emit()

    def _on_validation_bytes(self, phase: str, completed: int, total: int):
        if self._worker is None:
            return
        self._io_completed, self._io_total = completed, total
        self._set_status("Validierung: " + phase)
        self.progressChanged.emit()

    def _on_validation_finished(self, full: bool) -> None:
        worker, self._worker = self._worker, None
        self._task_control = None
        self._set_busy(False)
        if worker is None:
            return
        worker.deleteLater()
        self._record_validation_event(full, worker)
        if worker.error:
            self.message.emit("Validierung fehlgeschlagen", worker.error)
            return
        if worker.cancelled or worker.control.cancel_requested:
            self._set_status("Validierung abgebrochen")
            return
        for issue in worker.result:
            path = issue.pop("_snapshotPath", "")
            elements = self._pkg.root.xpath(path, namespaces={prefix: uri for prefix, uri in self._pkg.root.nsmap.items() if prefix}) if path else []
            issue["key"] = self._pkg.key(elements[0]) if elements else 0
        if full:
            full_only = {c.id for c in validation.CHECKS if c.full_only}
            self._full_issues = [i for i in worker.result if i["checkId"] in full_only]
            self._had_full_run = True
        self._publish_issues(worker.result if full else self._merge(worker.result))
        self._set_status(f"Validierung abgeschlossen: {self.errorCount} Fehler, {self.warningCount} Warnungen")
        remaining = {i["checkId"] for i in self.validationTable.records() if i["severity"] == validation.ERROR}
        if full and remaining == {"validity_failed"}:
            self.validityPrompt.emit()

    def _record_validation_event(self, full: bool, worker: ValidationWorker) -> None:
        pkg = self._pkg
        if pkg is None or pkg.root_dir is None or not self._validation_operator:
            return
        issue_counts = {}
        for issue in worker.result:
            counts = issue_counts.setdefault(issue["checkId"], {"errors": 0, "warnings": 0})
            counts["errors" if issue["severity"] == validation.ERROR else "warnings"] += 1
        if worker.error:
            result = "error"
            outcome = "failure"
        elif worker.cancelled or worker.control.cancel_requested:
            result = "cancelled"
            outcome = "failure"
        elif any(issue["severity"] == validation.ERROR for issue in worker.result):
            result = "invalid"
            outcome = "failure"
        elif any(issue["severity"] == validation.WARNING for issue in worker.result):
            result = "valid_with_warnings"
            outcome = "success"
        else:
            result = "valid"
            outcome = "success"
        detail = {"scope": "package-validation", "mode": "full" if full else "continuous",
                  "result": result, "schemaVersion": pkg.root.get("schemaVersion", ""),
                  "deliveryType": pkg.delivery_type, "metadataSha256": hashlib.sha256(
                      worker._snapshot_xml).hexdigest(), "issueCounts": issue_counts}
        try:
            journal_path = companion_directory(pkg.root_dir) / "journal.sqlite3"
            journal = AuditJournal(journal_path)
            journal.append("validation", agent_identifier=self._validation_operator,
                           software_version=self._software_version, detail=detail, outcome=outcome)
            self._refresh_history()
        except (AuditError, OSError) as exc:
            self.message.emit("Validierung nicht protokolliert", str(exc))

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
        attached = [i for i in self._full_issues
                if i["checkId"] not in FILE_SYSTEM_CHECKS and i["checkId"] != DROID_FORMAT_CHECK
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

    @io_task()
    def after_change(self, description: str, key: int = 0, file_system: bool = False, rebuild: bool = True) -> None:
        """Refresh models and persist staged changes without modifying the source SIP."""
        pkg = self._pkg
        if pkg is None:
            return
        if self._undo_pending is None:
            self._run_continuous_validation()
            return
        pkg.invalidate_file_index()
        if description:
            el = pkg.element(key) if key else None
            self._record_change(key, schema.KIND_LABELS.get(pkg.kind(el), "") if el is not None else "Paket",
                                pkg.display_name(el) if el is not None and self._is_attached(el) else "",
                                "Struktur", "", description)
        if file_system:
            self._refresh_file_system_checks()
        self._set_dirty(True)
        self._persist_file_draft()
        self._full_issues = [i for i in self._full_issues if not i["key"] or self._is_attached(pkg.element(i["key"]))]
        if rebuild:
            self.rebuild_navigators()
        self.editor.forget_missing()
        self.editor.refresh()
        self._refresh_notes()
        self._run_continuous_validation()
        self._set_status(description or self._status)

    @io_task()
    def _on_field_edited(self, key: int, kind: str, name: str, field: str, old: str, new: str) -> None:
        self._record_change(key, kind, name, field, old, new)
        pkg = self._pkg
        el = pkg.element(key)
        if el is not None:
            label = pkg.display_name(el)
            for model in (self.classificationModel, self.dossierModel, self.packageModel):
                model.update_label(key, label)
        self._set_dirty(True)
        self._persist_file_draft()
        self._run_continuous_validation()
        self.editor.refresh()

    def _record_change(self, key: int, kind: str, name: str, field: str, old: str, new: str) -> None:
        operation_identifier = self._finish_undo_operation(field if field != "Struktur" else new)
        self.changesTable.append({
            "time": datetime.now().strftime("%d.%m.%Y %H:%M:%S"), "object": kind, "objectName": name,
            "field": field, "oldValue": old, "newValue": new, "key": key,
        })
        element = self._pkg.element(key) if key else None
        detail = {"object": kind, "objectName": name, "field": field, "oldValue": old, "newValue": new,
                  "scope": "staged-package",
                  "operationIdentifier": operation_identifier,
                  "objectId": element.get("id", "") if element is not None else "",
                  "path": self._pkg.tree.getpath(element) if element is not None and self._is_attached(element) else ""}
        self._pending_audit.append({"event_type": "structural modification" if field == "Struktur" else "metadata modification",
                                    "operator": self.auditOperator, "detail": detail})

    def _refresh_notes(self) -> None:
        self.notesTable.set_records(notes.all_notes(self._pkg) if self._pkg is not None else [])

    # ---------------------------------------------------------------- editing helpers

    @Slot()
    def accumulateTimeSpans(self) -> None:
        """Extras > Zeiträume auf Ablieferung kumulieren."""
        pkg = self.require_writable()
        if pkg is None:
            return
        try:
            start, end = self.stage_file_operation(lambda package: structure.accumulate_time_spans(package, package.delivery))
        except (AuditError, OSError) as exc:
            self.message.emit("Bearbeitung fehlgeschlagen", str(exc))
            return
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
            self.undoChanged.emit()
            self.taskStateChanged.emit()

    def _set_status(self, text: str) -> None:
        self._status = text
        self.statusChanged.emit()

    def set_status(self, text: str) -> None:
        self._set_status(text)

    def shutdown(self) -> None:
        self.cancelTask()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()
            self._worker.deleteLater()
            self._worker = None
            self._task_control = None
        if self._worker is None or not self._worker.isRunning():
            self._set_busy(False)
            self.clearUndoHistory()


SIMPLE_SEARCH_COLUMNS = [("object", "Objekt"), ("objectName", "Objektname"), ("field", "Metadatum"), ("value", "Wert")]
