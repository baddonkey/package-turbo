import pytest
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QGuiApplication

from ph_backend.backend import Backend
from ph_backend.controllers import (FileController, NoteController, PackageController, SearchController,
                                    StructureController)


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication(["test", "-platform", "offscreen"])


@pytest.fixture
def backend(app, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    backend = Backend(settings)
    backend.messages = []
    backend.message.connect(lambda title, text: backend.messages.append((title, text)))
    return backend


@pytest.fixture
def opened(backend, sip_dir):
    backend.openPackage(QUrl.fromLocalFile(str(sip_dir)), False)
    return backend


def test_open_edit_save_cycle(opened, sip_dir):
    backend = opened
    assert backend.hasPackage and not backend.dirty
    assert backend.classificationModel.itemCount() > 0
    assert backend.recentPackages == [str(sip_dir)]

    pkg = backend.package
    dossier = next(pkg.iter_kind("dossier"))
    backend.select(pkg.key(dossier))
    assert backend.editor.currentTab == "dossier"

    backend.editor.setField(pkg.key(dossier), "titel", "Neuer Dossiertitel")
    assert backend.dirty and backend.changesTable.total == 1
    assert backend.classificationModel.indexOfKey(pkg.key(dossier)).data() == "Neuer Dossiertitel"
    assert backend.save() and not backend.dirty
    assert backend.changesTable.total == 0
    assert "Neuer Dossiertitel" in (sip_dir / "header" / "metadata.xml").read_text(encoding="utf-8")


def test_invalid_date_is_reported(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.editor.setTimeSpan(pkg.key(dossier), "entstehungszeitraum", "2001-02", "")
    assert opened.messages and not opened.dirty


def test_editor_offers_choices_and_errors(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.select(pkg.key(dossier))
    fields = {f["tag"]: f for s in opened.editor.sections for f in s["primary"] + s["more"]}
    assert fields["erscheinungsform"]["type"] == "choice"
    assert "gemischt" in fields["erscheinungsform"]["choices"]
    assert fields["datenschutz"]["choices"] == ["", "true", "false"]
    assert fields["eroeffnungsdatum"]["type"] == "timepoint"
    opened.editor.setField(pkg.key(dossier), "titel", "Kurz")
    fields = {f["tag"]: f for s in opened.editor.sections for f in s["primary"]}
    assert "5 Zeichen" in fields["titel"]["error"]


def test_read_only_blocks_edits(backend, sip_dir):
    backend.openPackage(QUrl.fromLocalFile(str(sip_dir)), True)
    pkg = backend.package
    dossier = next(pkg.iter_kind("dossier"))
    backend.editor.setField(pkg.key(dossier), "titel", "x")
    assert not backend.dirty and not backend.save()
    StructureController(backend).deleteObjects([pkg.key(dossier)])
    assert next(pkg.iter_kind("dossier")) is dossier


def test_search_controller(opened):
    ctl = SearchController(opened)
    assert ctl.simpleSearch("bericht") >= 2
    assert opened.searchTable.columnLabels() == ["Objekt", "Objektname", "Metadatum", "Wert"]
    assert ctl.advancedSearch([{"kind": "dossier", "tag": "titel", "value": "leer"}]) == 1
    assert opened.searchTable.columnLabels()[-1] == "Titel"
    assert ctl.advancedSearch([{"kind": "dossier", "tag": "titel", "value": ""}]) == -1
    opened.sampleSize = 1
    ctl.drawSample()
    assert opened.sampleTable.total == 1


def test_structure_controller(opened):
    pkg = opened.package
    ctl = StructureController(opened)
    position = next(pkg.iter_kind("ordnungssystemposition"))
    assert "ordnungssystemposition" not in ctl.allowedChildren(pkg.key(position))
    key = ctl.addObjects(pkg.key(position), "dossier", 2)
    assert key and opened.dirty and opened.changesTable.total == 1
    new_dossier = pkg.element(key)
    file_el = pkg.file_by_id("_file2")
    assert ctl.assignFiles([pkg.key(file_el)], key) == 1
    ctl.cut([key])
    target = next(d for d in pkg.iter_kind("dossier") if pkg.text(d, "titel") == "Leer")
    ctl.paste(pkg.key(target))
    assert new_dossier.getparent() is target
    ctl.deleteObjects([key])
    assert new_dossier.getparent() is None
    ctl.renumber("decimal")
    assert pkg.text(position, "nummer") == "0"
    kinds = [k["kind"] for k in ctl.massEditKinds(pkg.key(pkg.classification_system))]
    assert "dossier" in kinds
    ctl.massEdit(pkg.key(pkg.classification_system), "dossier", "inhalt", "x", "")
    assert all(pkg.text(d, "inhalt") == "x" for d in pkg.iter_kind("dossier"))
    ctl.addObjects(pkg.key(position), "ordnungssystemposition", 1)
    assert opened.messages


def test_file_controller_and_fixes(opened, sip_dir, tmp_path):
    pkg = opened.package
    ctl = FileController(opened)
    content = next(o for o in pkg.iter_kind("ordner") if pkg.text(o, "name") == "content")
    source = tmp_path / "neu.pdf"
    source.write_bytes(b"%PDF-1.4")
    url = QUrl.fromLocalFile(str(source)).toString()
    assert ctl.importConflicts(pkg.key(content), [url]) == []
    ctl.importUrls(pkg.key(content), [url], True, False)
    assert (sip_dir / "content" / "neu.pdf").is_file() and not opened.dirty
    assert ctl.importConflicts(pkg.key(content), [url]) == ["neu.pdf"]

    (sip_dir / "content" / "d0001" / "p000001.pdf").write_bytes(b"new content")
    opened.validate(True)
    opened._worker.wait()
    QGuiApplication.processEvents()
    rows = [i for i, r in enumerate(opened.validationTable.visible_records()) if r["checkId"] == "checksum"]
    assert rows and ctl.fixActions(rows[0])[0]["id"] == "recompute_checksum"
    ctl.applyFix("recompute_checksum", rows)
    assert not [r for r in opened.validationTable.records() if r["checkId"] == "checksum"]

    (sip_dir / "stray.txt").write_text("x")
    opened.validate(True)
    opened._worker.wait()
    QGuiApplication.processEvents()
    rows = [i for i, r in enumerate(opened.validationTable.visible_records()) if r["checkId"] == "illegal_entries"]
    ctl.applyFix("delete_fs", rows)
    assert not (sip_dir / "stray.txt").exists()
    assert not [r for r in opened.validationTable.records() if r["checkId"] == "illegal_entries"]


def test_notes_controller(opened):
    pkg = opened.package
    ctl = NoteController(opened)
    dossier = next(pkg.iter_kind("dossier"))
    assert ctl.canHaveNotes(pkg.key(dossier))
    ctl.addNote([pkg.key(dossier)], "prüfen")
    assert opened.notesTable.total == 1
    note_key = opened.notesTable.recordAt(0)["noteKey"]
    ctl.editNote(note_key, "ok")
    assert opened.notesTable.recordAt(0)["comment"] == "ok"
    index = opened.classificationModel.indexOfKey(pkg.key(dossier))
    from ph_backend.navigators import NOTE_ROLE
    assert index.data(NOTE_ROLE) is True
    ctl.deleteNotes([note_key])
    assert opened.notesTable.total == 0


def test_package_controller(backend, tmp_path):
    ctl = PackageController(backend, [])
    name = ctl.suggestedName("Testamt", "R1")
    assert ctl.nameError(name) == "" and ctl.nameError("x y")
    assert ctl.createPackage(QUrl.fromLocalFile(str(tmp_path)), name, "Testamt", "GEVER", "", "Plan", QUrl())
    assert backend.hasPackage and backend.packageName == name
    ctl.savePerspective("Breit", {"left": 500, "bottom": 200})
    assert ctl.perspectives == ["Breit"] and ctl.perspective("Breit")["left"] == 500
    ctl.deletePerspective("Breit")
    assert ctl.perspectives == []


def test_accumulate_time_spans(opened):
    opened.accumulateTimeSpans()
    pkg = opened.package
    assert pkg.time_span(pkg.delivery, "entstehungszeitraum") == ("2007", "2008")
