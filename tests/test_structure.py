import pytest

from ph_backend import files, package_factory, structure, xsd_info
from ph_backend.package_factory import PackageCreationError
from ph_backend.sip import SipPackage
from ph_backend.validation import Validator


def _schema_errors(pkg):
    return [i["description"] for i in Validator(pkg).run(full=False) if i["checkId"] == "schema"]


@pytest.fixture
def new_pkg(tmp_path):
    return package_factory.create_package(tmp_path, "SIP_20260104_Testamt_Ref1", "Testamt")


def test_new_package_is_schema_valid(new_pkg):
    assert new_pkg.delivery_type == "GEVER"
    assert len(list(new_pkg.iter_kind("ordnungssystemposition"))) == 1
    assert _schema_errors(new_pkg) == []
    full = {i["checkId"] for i in Validator(new_pkg).run(full=True)}
    assert not full & {"checksum", "surplus_file", "missing_file", "header_content", "sip_name"}


def test_new_files_package(tmp_path):
    pkg = package_factory.create_package(tmp_path, "SIP_20260104_Amt_X", "Amt", delivery_type="FILES")
    assert pkg.delivery_type == "FILES" and _schema_errors(pkg) == []


def test_new_package_name_rules(tmp_path):
    with pytest.raises(PackageCreationError):
        package_factory.create_package(tmp_path, "SIP 2026", "Amt")
    with pytest.raises(PackageCreationError):
        package_factory.create_package(tmp_path, "Paket_ohne_Muster", "Amt")
    package_factory.create_package(tmp_path, "Paket_ohne_Muster", "Amt", validate_sip_name=False)
    assert package_factory.suggested_name("Bundesamt für Test", "Ref 1").startswith("SIP_")


def test_csv_import(tmp_path):
    csv_path = tmp_path / "plan.csv"
    csv_path.write_text("nummer|type|titel|federfuehrendeOrganisationseinheit\n1||Führung|\n10||Planung|x\n"
                        "10.1|dossier|Jahresplanung|\n2||Ressourcen|\n", encoding="utf-8")
    pkg = package_factory.create_package(tmp_path, "SIP_20260104_Amt_CSV", "Amt", csv_path=csv_path)
    positions = {pkg.text(p, "nummer"): p for p in pkg.iter_kind("ordnungssystemposition")}
    assert set(positions) == {"1", "10", "2"}
    assert positions["10"].getparent() is positions["1"]
    dossier = next(pkg.iter_kind("dossier"))
    assert dossier.getparent() is positions["10"] and pkg.text(dossier, "aktenzeichen") == "10.1"
    assert pkg.text(positions["10"], "federfuehrendeOrganisationseinheit") == "x"
    assert _schema_errors(pkg) == []


def test_csv_import_requires_nummer(tmp_path):
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("titel\nx\n", encoding="utf-8")
    with pytest.raises(structure.StructureError):
        package_factory.create_package(tmp_path, "SIP_20260104_Amt_Bad", "Amt", csv_path=csv_path)
    assert not (tmp_path / "SIP_20260104_Amt_Bad").exists()


def test_build_import_assign_and_validate(new_pkg, tmp_path):
    pkg = new_pkg
    source = tmp_path / "ablage"
    (source / "Gruppe A" / "Dossier 1").mkdir(parents=True)
    (source / "Gruppe A" / "Dossier 1" / "brief.pdf").write_bytes(b"%PDF-1.4 a")
    (source / "Gruppe A" / "Dossier 1" / "notiz.txt").write_bytes(b"b")
    (source / "Gruppe A" / "lose.pdf").write_bytes(b"%PDF-1.4 c")
    content = next(o for o in pkg.iter_kind("ordner") if pkg.text(o, "name") == "content")
    stats = files.import_paths(pkg, content, [source])
    assert stats["files"] == 3 and stats["folders"] == 3

    structure.delete(pkg, list(pkg.iter_kind("ordnungssystemposition")))
    top = next(o for o in pkg.children(content, "ordner") if pkg.text(o, "name") == "ablage")
    created, unassigned = structure.mass_assign(pkg, [top], pkg.classification_system, 1, 1)
    assert created == 2 and unassigned == 1
    dossier = next(pkg.iter_kind("dossier"))
    assert pkg.text(dossier, "titel") == "Dossier 1"
    # GEVER dossiers reference files through documents.
    assert len(list(dossier.iter(pkg.q("dokument")))) == 2
    pkg.save()
    assert _schema_errors(pkg) == []
    full = {i["checkId"] for i in Validator(pkg).run(full=True)}
    assert not full & {"checksum", "surplus_file", "missing_file", "surplus_folder"}
    assert "charset" in full

    assert files.normalize_names(pkg) == 2
    assert "charset" not in {i["checkId"] for i in Validator(pkg).run(full=False)}
    assert files.denormalize(pkg) == 2
    assert files.shorten_paths(pkg) > 0
    names = {pkg.text(f, "name") for f in pkg.iter_kind("datei") if pkg.relpath(f).parts[0] == "content"}
    assert names == {"P1.pdf", "P2.txt", "P3.pdf"} or all(n.startswith("P") for n in names)
    pkg.save()
    full = {i["checkId"] for i in Validator(pkg).run(full=True)}
    assert not full & {"checksum", "surplus_file", "missing_file", "schema"}


def test_mass_assign_rules(new_pkg):
    with pytest.raises(structure.StructureError):
        structure.mass_assign(new_pkg, [], new_pkg.classification_system, 0, 1)


def test_rename_delete_and_references(new_pkg, tmp_path):
    pkg = new_pkg
    content = next(o for o in pkg.iter_kind("ordner") if pkg.text(o, "name") == "content")
    folder = files.create_folder(pkg, content, "akten")
    with pytest.raises(files.FileOperationError):
        files.create_folder(pkg, content, "nicht erlaubt")
    src = tmp_path / "a.pdf"
    src.write_bytes(b"%PDF-1.4")
    files.import_paths(pkg, folder, [src])
    file_el = pkg.children(folder, "datei")[0]
    position = next(pkg.iter_kind("ordnungssystemposition"))
    dossier = structure.add_objects(pkg, position, "dossier")[0]
    assert structure.assign_files(pkg, dossier, [file_el]) == 1

    files.rename(pkg, file_el, "b.pdf")
    assert (pkg.root_dir / "content" / "akten" / "b.pdf").is_file()
    assert pkg.text(file_el, "originalName") == "a.pdf"
    with pytest.raises(files.FileOperationError):
        files.rename(pkg, file_el, "ä.pdf")

    src.write_bytes(b"%PDF-1.4 changed")
    old = pkg.text(file_el, "pruefsumme")
    files.replace_file(pkg, file_el, src)
    assert pkg.text(file_el, "pruefsumme") != old

    files.delete_entries(pkg, [folder])
    assert not (pkg.root_dir / "content" / "akten").exists()
    assert pkg.referenced_ids() == set()
    with pytest.raises(files.FileOperationError):
        files.delete_entries(pkg, [content])


def test_fix_actions(new_pkg):
    pkg = new_pkg
    (pkg.root_dir / "stray.txt").write_text("x")
    (pkg.root_dir / "content" / "neu").mkdir()
    (pkg.root_dir / "content" / "neu" / "x.pdf").write_bytes(b"%PDF")
    issues = Validator(pkg).run(full=True)
    assert {"illegal_entries", "surplus_file", "surplus_folder"} <= {i["checkId"] for i in issues}
    files.delete_from_file_system(pkg, "stray.txt")
    assert files.add_to_table_of_contents(pkg, "content/neu") == 1
    with pytest.raises(files.FileOperationError):
        files.delete_from_file_system(pkg, "../outside")
    found = {i["checkId"] for i in Validator(pkg).run(full=True)}
    assert not found & {"illegal_entries", "surplus_file", "surplus_folder"}

    file_el = next(f for f in pkg.iter_kind("datei") if pkg.text(f, "name") == "x.pdf")
    (pkg.root_dir / "content" / "neu" / "x.pdf").unlink()
    files.remove_from_metadata(pkg, file_el)
    assert "missing_file" not in {i["checkId"] for i in Validator(pkg).run(full=True)}

    pkg.set_text(pkg.delivery, "ablieferungstyp", "")
    assert files.set_delivery_type(pkg) == "GEVER"


def test_objects_move_renumber_and_time_spans(new_pkg):
    pkg = new_pkg
    system = pkg.classification_system
    first = next(pkg.iter_kind("ordnungssystemposition"))
    a, b = structure.add_objects(pkg, system, "ordnungssystemposition", 2)
    child = structure.add_objects(pkg, first, "ordnungssystemposition")[0]
    dossier = structure.add_objects(pkg, child, "dossier")[0]
    with pytest.raises(structure.StructureError):
        structure.add_objects(pkg, child, "ordnungssystemposition")
    with pytest.raises(structure.StructureError):
        structure.move(pkg, first, child)
    structure.move(pkg, child, b)
    assert child.getparent() is b
    assert structure.move_relative(pkg, b, -1)
    assert structure.renumber(pkg, "decimal") == 4
    assert sorted(pkg.text(p, "nummer") for p in pkg.iter_kind("ordnungssystemposition")) == ["0", "1", "10", "2"]
    assert structure.renumber(pkg, "hundred") == 4
    assert pkg.text(child, "nummer") == "0100"

    doc = structure.add_objects(pkg, dossier, "dokument")[0]
    pkg.set_time_span(doc, "entstehungszeitraum", "01.02.2001", "ca. 2003")
    assert pkg.time_span_display(doc, "entstehungszeitraum") == ("01.02.2001", "ca. 2003")
    assert structure.accumulate_time_spans(pkg, dossier) == ("2001-02-01", "2003")
    structure.propagate_time_span_up(pkg, dossier)
    assert pkg.time_span(pkg.delivery, "entstehungszeitraum") == ("2001-02-01", "2003")
    assert _schema_errors(pkg) == []

    assert structure.mass_edit(pkg, system, "dossier", "inhalt", "Gleich") == 1
    assert pkg.text(dossier, "inhalt") == "Gleich"
    assert "dokument" in structure.mass_edit_kinds(pkg, system)
    structure.delete(pkg, [dossier])
    with pytest.raises(structure.StructureError):
        structure.delete(pkg, [system])


def test_xsd_choices(new_pkg):
    info = xsd_info.for_package(new_pkg)
    dossier_type = "dossierGever"
    assert info.choices(dossier_type, "erscheinungsform") == ["keine Angabe", "digital", "nicht digital", "gemischt"]
    assert info.choices(dossier_type, "datenschutz") == ["true", "false"]
    assert info.is_required(dossier_type, "titel")
    assert info.choices("datei", "pruefalgorithmus") == ["MD5", "SHA-1", "SHA-256", "SHA-512"]
