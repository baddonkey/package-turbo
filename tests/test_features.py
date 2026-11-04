import random

import pytest
from lxml import etree
from PySide6.QtGui import QGuiApplication

from ph_backend import notes, reports, sampling, search, statistics, xsd_info
from ph_backend.editor import MetadataEditor
from ph_backend.sip import SipPackage
from ph_backend.validation import Validator


def test_additional_data_on_all_allowed_objects(sample_sip):
    pkg = SipPackage.open_folder(sample_sip)
    info = xsd_info.for_package(pkg)
    targets = [pkg.root, pkg.delivery, pkg.classification_system] + [
        next(pkg.iter_kind(k)) for k in ("ordnungssystemposition", "dossier", "dokument")]
    for el in targets:
        assert info.element(xsd_info.type_name(pkg, el, info), "zusatzDaten") is not None
        pkg.set_additional_data(el, [("Herkunft", "Scan"), ("Projekt", "A-17")])
    assert pkg.additional_data(pkg.delivery) == [("Herkunft", "Scan"), ("Projekt", "A-17")]
    assert not [i for i in Validator(pkg).run(full=False) if i["checkId"] == "schema"]
    pkg.save()
    reopened = SipPackage.open_folder(sample_sip)
    assert reopened.additional_data(next(reopened.iter_kind("dossier"))) == [("Herkunft", "Scan"), ("Projekt", "A-17")]
    reopened.set_additional_data(reopened.delivery, [("", "")])
    assert reopened.child(reopened.delivery, "zusatzDaten") is None


def test_additional_data_in_editor_and_search(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    editor = MetadataEditor()
    editor.set_package(pkg)
    edits = []
    editor.fieldEdited.connect(lambda *args: edits.append(args))
    dossier = next(pkg.iter_kind("dossier"))
    editor.showElement(pkg.key(dossier))
    section = editor.sections[0]
    assert section["canHaveAdditionalData"] and section["additionalData"] == []
    editor.setAdditionalData(pkg.key(dossier), [{"name": "Signatur", "value": "XY-1"}])
    assert editor.sections[0]["additionalData"] == [{"name": "Signatur", "value": "XY-1"}]
    assert edits[-1][3] == "Zusatzdaten" and edits[-1][5] == "Signatur=XY-1"
    hits = search.simple_search(pkg, "xy-1")
    assert hits and hits[0]["field"] == "Zusatzdaten"
    found = search.advanced_search(pkg, [search.Criterion("dossier", "zusatzDaten", "Signatur")])
    assert [h["objectName"] for h in found] == ["Dossier mit Datei"]
    editor.showElement(pkg.key(pkg.provenance))
    assert not next(s for s in editor.sections if s["kind"] == "provenienz")["canHaveAdditionalData"]


def test_archival_processes_in_editor(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    processes = []
    for description in ("Erste Beschreibung", "Zweite Beschreibung"):
        process = etree.SubElement(pkg.root, pkg.q("archivischerVorgang"))
        etree.SubElement(process, pkg.q("beschreibung")).text = description
        processes.append(process)

    editor = MetadataEditor()
    editor.set_package(pkg)
    process_tab = next(tab for tab in editor.tabs if tab["id"] == "archivischerVorgang")
    assert process_tab["label"] == "Archivische Vorgänge"

    editor.showTab("archivischerVorgang")
    sections = editor.sections
    assert [section["kind"] for section in sections] == ["archivischerVorgang"] * 2
    descriptions = [field["value"] for section in sections for field in section["primary"] + section["more"]
                    if field["tag"] == "beschreibung"]
    assert descriptions == ["Erste Beschreibung", "Zweite Beschreibung"]
    editor.setField(sections[0]["key"], "beschreibung", "Bearbeitete Beschreibung")
    assert pkg.text(processes[0], "beschreibung") == "Bearbeitete Beschreibung"


@pytest.fixture(scope="module", autouse=True)
def app():
    return QGuiApplication.instance() or QGuiApplication(["test", "-platform", "offscreen"])


def test_notes_roundtrip(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    dossier = next(pkg.iter_kind("dossier"))
    note = notes.add_note(pkg, dossier, "Bitte prüfen", author="tester")
    assert notes.has_notes(pkg, dossier)
    rows = notes.all_notes(pkg)
    assert rows[0]["comment"] == "Bitte prüfen" and rows[0]["author"] == "tester"
    notes.edit_note(pkg, note, "Erledigt")
    pkg.save()
    reopened = SipPackage.open_folder(sip_dir)
    assert notes.all_notes(reopened)[0]["comment"] == "Erledigt"
    notes.delete_note(reopened, reopened.element(notes.all_notes(reopened)[0]["noteKey"]))
    assert notes.all_notes(reopened) == []


def test_notes_are_schema_valid(sample_sip):
    pkg = SipPackage.open_folder(sample_sip)
    for el in [pkg.delivery, next(pkg.iter_kind("dossier")), next(pkg.iter_kind("datei"))]:
        notes.add_note(pkg, el, "Notiz")
    assert not [i for i in Validator(pkg).run(full=False) if i["checkId"] == "schema"]
    with pytest.raises(notes.NoteError):
        notes.add_note(pkg, next(pkg.iter_kind("ordner")), "x")


def test_simple_and_advanced_search(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    assert len(search.simple_search(pkg, "BERICHT")) >= 2
    hits = search.advanced_search(pkg, [search.Criterion("dossier", "titel", "dossier"),
                                        search.Criterion("dossier", "aktenzeichen", "1.1")])
    assert [h["objectName"] for h in hits] == ["Dossier mit Datei"]
    assert hits[0]["value1"] == "1.1"
    empty = search.advanced_search(pkg, [search.Criterion("dossier", "schutzfrist", empty=True)])
    assert len(empty) == 2
    assert search.advanced_search(pkg, [search.Criterion("dossier", "titel", "x"),
                                        search.Criterion("dokument", "titel", "x")]) == []
    with pytest.raises(search.TooManyHits):
        search.simple_search(pkg, "e", max_hits=1)


def test_statistics(sample_sip):
    pkg = SipPackage.open_folder(sample_sip)
    data = statistics.overview(pkg)
    labels = {r["label"]: r["value"] for r in data["records"]}
    assert int(labels["Anzahl Dossiers"]) > 0 and int(labels["Maximale OSP Verzeichnungstiefe"]) >= 1
    assert data["positionsPerLevel"] and data["documentsByFileCount"]
    chart = statistics.time_span_comparison(pkg)
    assert [b["label"] for b in chart["bars"]][:3] == ["Aktenbildner", "Ordnungssystem", "Ablieferung"]
    assert chart["bars"][0]["state"] == "open"
    assert chart["from"] <= 1966 < chart["to"]
    assert statistics.protection_periods(pkg)


def test_sampling(sample_sip):
    pkg = SipPackage.open_folder(sample_sip)
    total = sum(1 for d in pkg.iter_kind("dossier") if pkg.kind(d) == "dossier")
    assert len(sampling.draw_sample(pkg, sampling.ABSOLUTE, 3, random.Random(1))) == min(3, total)
    assert len(sampling.draw_sample(pkg, sampling.PERCENT, 100)) == total
    assert sampling.draw_sample(pkg, sampling.ABSOLUTE, 0) == []


@pytest.mark.parametrize("report", list(reports.REPORTS))
def test_reports(sip_dir, tmp_path, report):
    pkg = SipPackage.open_folder(sip_dir)
    pkg.set_text(next(pkg.iter_kind("dossier")), "titel", "<script>x</script>")
    html = reports.build_html(pkg, report, "Tester")
    assert "<script>" not in html and "Testamt" in html
    target = reports.write_pdf(pkg, report, tmp_path / f"{report}.pdf", "Tester")
    assert target.read_bytes().startswith(b"%PDF")
