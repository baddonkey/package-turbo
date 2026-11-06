import pytest

from ph_backend import file_formats
from ph_backend.sip import SipPackage
from ph_backend.validation import CHECKS, ERROR, WARNING, Validator, summarize


def _checks(issues):
    return {i["checkId"] for i in issues}


def test_continuous_checks_on_synthetic_sip(sip_dir):
    issues = Validator(SipPackage.open_folder(sip_dir)).run(full=False)
    found = _checks(issues)
    assert {"empty_folders", "unassigned_files", "empty_dossiers", "dossier_title", "open_time_span"} <= found
    assert not any(c.full_only for c in CHECKS if c.id in found)


def test_full_validation_detects_file_system_mismatch(sip_dir):
    baseline = Validator(SipPackage.open_folder(sip_dir)).run(full=True)
    assert not _checks(baseline) & {"checksum", "missing_file", "surplus_file"}

    (sip_dir / "content" / "d0001" / "p000001.pdf").write_bytes(b"changed")
    (sip_dir / "content" / "d0001" / "surplus.pdf").write_bytes(b"x")
    (sip_dir / "content" / "d0001" / "p000002.txt").unlink()
    (sip_dir / "stray.txt").write_text("x")
    issues = Validator(SipPackage.open_folder(sip_dir)).run(full=True)
    found = _checks(issues)
    assert {"checksum", "surplus_file", "missing_file", "illegal_entries", "header_content",
            "validity_failed"} <= found


def test_missing_checksum_is_reported(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    file_element = pkg.file_by_id("_file1")
    assert not [issue for issue in Validator(pkg).run(full=True) if issue["checkId"] == "checksum"]
    pkg.set_text(file_element, "pruefsumme", "")

    issues = Validator(pkg).run(full=True)

    assert any(issue["checkId"] == "checksum" and issue["fieldTag"] == "pruefsumme" for issue in issues)


def test_sip_name_check_can_be_disabled(sip_dir):
    renamed = sip_dir.rename(sip_dir.with_name("not_a_sip_name"))
    pkg = SipPackage.open_folder(renamed)
    assert "sip_name" in _checks(Validator(pkg).run(full=True))
    assert "sip_name" not in _checks(Validator(pkg, validate_sip_name=False).run(full=True))


def test_unsupported_checksum_is_reported_not_silently_md5(sip_dir):
    import pytest
    from ph_backend.sip import UnsupportedChecksumError, file_checksum

    pkg = SipPackage.open_folder(sip_dir)
    file_el = pkg.file_by_id("_file1")
    pkg.set_text(file_el, "pruefalgorithmus", "UNKNOWN", required=True)
    with pytest.raises(UnsupportedChecksumError):
        file_checksum(pkg.fs_path(file_el), "UNKNOWN")
    issues = Validator(pkg).run(full=True)
    assert any(issue["checkId"] == "checksum" and issue["fieldTag"] == "pruefalgorithmus" for issue in issues)


def test_dangling_datei_ref_is_reported(tmp_path):
    from ph_backend import files, package_factory, structure

    pkg = package_factory.create_package(tmp_path, "SIP_20261105_Test_DanglingRef", "Test",
                                         version="1.0", delivery_type="FILES")
    content = next(element for element in pkg.iter_kind("ordner") if pkg.text(element, "name") == "content")
    source = tmp_path / "reference.txt"
    source.write_text("reference", encoding="utf-8")
    files.import_paths(pkg, content, [source])
    file_element = next(element for element in pkg.children(content, "datei"))
    dossier = structure.add_objects(pkg, next(pkg.iter_kind("ordnungssystemposition")), "dossier")[0]
    document = structure.add_objects(pkg, dossier, "dokument")[0]
    structure.assign_files(pkg, document, [file_element])
    pkg.children(document, "dateiRef")[0].text = "_missing_file"

    issues = Validator(pkg).run(full=True)

    assert any(issue["checkId"] == "invalid_reference" and issue["value"] == "_missing_file"
               for issue in issues)


@pytest.mark.parametrize("version", ["1.0", "1.1", "1.2", "1.3"])
@pytest.mark.parametrize("delivery_type", ["GEVER", "FILES"])
def test_mandatory_metadata_is_reported_after_sip_save_and_reopen(tmp_path, version, delivery_type):
    from ph_backend import package_factory, structure
    from ph_backend.sip import SipPackage

    pkg = package_factory.create_package(tmp_path, f"SIP_20261106_Test_Required_{version}_{delivery_type}", "Test",
                                         version=version, delivery_type=delivery_type)
    position = next(pkg.iter_kind("ordnungssystemposition"))
    structure.add_objects(pkg, position, "dossier")
    required_fields = (("ablieferung", "ablieferndeStelle"), ("dossier", "titel"))

    for kind, field in required_fields:
        owner = pkg.delivery if kind == "ablieferung" else next(pkg.iter_kind("dossier"))
        pkg.set_text(owner, field, "")
        pkg.save()
        pkg = SipPackage.open_folder(pkg.root_dir)
        issues = Validator(pkg).run(full=True)
        assert any(issue["checkId"] == "missing_values" and issue["fieldTag"] == field for issue in issues), (
            version, delivery_type, field)

        reopened_owner = pkg.delivery if kind == "ablieferung" else next(pkg.iter_kind("dossier"))
        pkg.set_text(reopened_owner, field, "Restored required value", required=True)
        pkg.save()
        pkg = SipPackage.open_folder(pkg.root_dir)
        issues = Validator(pkg).run(full=True)
        assert not any(issue["checkId"] == "missing_values" and issue["fieldTag"] == field for issue in issues), (
            version, delivery_type, field)
        assert not any(issue["checkId"] == "schema" for issue in issues), (version, delivery_type, field)


@pytest.mark.parametrize("version", ["1.0", "1.1"])
def test_legacy_files_provenance_fields_roundtrip(tmp_path, version):
    from ph_backend import package_factory
    from ph_backend.sip import SipPackage

    pkg = package_factory.create_package(tmp_path, f"SIP_20261106_Test_LegacyFiles_{version}", "Test",
                                         version=version, delivery_type="FILES")
    for field, value in (("systemName", "Source system"), ("systemBeschreibung", "Source description")):
        pkg.set_text(pkg.provenance, field, value, required=True)
        pkg.save()
        pkg = SipPackage.open_folder(pkg.root_dir)
        issues = Validator(pkg).run(full=True)
        assert not any(issue["checkId"] == "missing_values" and issue["fieldTag"] == field
                   for issue in issues), (version, field)
        assert not any(issue["checkId"] == "schema" for issue in issues), (version, field)

        pkg.set_text(pkg.provenance, field, "")
        pkg.save()
        pkg = SipPackage.open_folder(pkg.root_dir)
        assert any(issue["checkId"] == "missing_values" and issue["fieldTag"] == field
                   for issue in Validator(pkg).run(full=True)), (version, field)


def test_optional_metadata_fields_may_be_absent(tmp_path):
    from ph_backend import package_factory

    pkg = package_factory.create_package(tmp_path, "SIP_20261105_Test_OptionalFields", "Test",
                                         version="1.3", delivery_type="FILES")
    for tag in ("ablieferungsnummer", "schutzfristenkategorie", "schutzfrist"):
        element = pkg.child(pkg.delivery, tag)
        if element is not None:
            pkg.delivery.remove(element)

    issues = Validator(pkg).run(full=False)

    missing = {issue["fieldTag"] for issue in issues if issue["checkId"] == "missing_values"}
    assert not missing & {"ablieferungsnummer", "schutzfristenkategorie", "schutzfrist"}


def test_time_span_checks(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    dossier = next(pkg.iter_kind("dossier"))
    pkg.set_time_span(dossier, "entstehungszeitraum", "2009", "2001")
    issues = Validator(pkg).run(full=False)
    assert "invalid_time_span" in _checks(issues)
    pkg.set_time_span(dossier, "entstehungszeitraum", "2001", "2003")
    assert "time_span_hierarchy" in _checks(Validator(pkg).run(full=False))


def test_estimated_dossier_period_requires_reason(tmp_path):
    from ph_backend import package_factory, structure
    from ph_backend.sip import SipPackage

    pkg = package_factory.create_package(tmp_path, "SIP_20261106_Test_EstimatedPeriod", "Test",
                                         version="1.3", delivery_type="GEVER")
    dossier = structure.add_objects(pkg, next(pkg.iter_kind("ordnungssystemposition")), "dossier")[0]
    pkg.set_time_span(dossier, "entstehungszeitraum", "ca. 2000", "2001")

    issues = Validator(pkg).run(full=False)
    assert any(issue["checkId"] == "missing_values" and issue["fieldTag"] == "entstehungszeitraumAnmerkung"
               for issue in issues)
    pkg.save()
    pkg = SipPackage.open_folder(pkg.root_dir)
    assert any(issue["checkId"] == "missing_values" and issue["fieldTag"] == "entstehungszeitraumAnmerkung"
               for issue in Validator(pkg).run(full=False))

    dossier = next(pkg.iter_kind("dossier"))
    pkg.set_text(dossier, "entstehungszeitraumAnmerkung", "Date estimated from incomplete records")
    pkg.save()
    pkg = SipPackage.open_folder(pkg.root_dir)
    issues = Validator(pkg).run(full=False)
    assert not any(issue["checkId"] == "missing_values" and issue["fieldTag"] == "entstehungszeitraumAnmerkung"
                   for issue in issues)


def test_protection_period_inconsistency(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    dossier = next(pkg.iter_kind("dossier"))
    pkg.set_text(dossier, "schutzfristenkategorie", "BGA")
    issues = Validator(pkg).run(full=False)
    assert any(i["checkId"] == "protection_period" and i["key"] == pkg.key(dossier) for i in issues)
    pkg.set_text(dossier, "schutzfrist", "50")
    assert any(i["checkId"] == "protection_period" and "einheitlich" in i["description"]
               for i in Validator(pkg).run(full=False))


def test_duplicate_position_numbers(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    position = next(pkg.iter_kind("ordnungssystemposition"))
    from copy import deepcopy
    clone = deepcopy(position)
    clone.set("id", "_osp2")
    for el in clone.iter():
        if el.get("id") and el is not clone:
            el.set("id", el.get("id") + "_copy")
    position.addnext(clone)
    assert "position_number" in _checks(Validator(pkg).run(full=False))


def test_summarize_counts_every_check(sip_dir):
    issues = Validator(SipPackage.open_folder(sip_dir)).run(full=True)
    summary = summarize(issues)
    assert len(summary) == len(CHECKS)
    assert sum(s["errors"] + s["warnings"] for s in summary) == len(issues)


def test_kad_classification():
    assert file_formats.classify("a.PDF").rating == file_formats.RECOMMENDED
    assert file_formats.classify("a.docx").rating == file_formats.ACCEPTED
    assert file_formats.classify("a.odt").rating == file_formats.NOT_ACCEPTED
    assert file_formats.classify("a.xyz").rating == file_formats.UNKNOWN
    assert file_formats.classify("noext").rating == file_formats.UNKNOWN


def test_file_format_check_follows_kad(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    assert "file_format" not in _checks(Validator(pkg).run(full=True))
    pkg.child(pkg.file_by_id("_file1"), "name").text = "p000001.odt"
    pkg.child(pkg.file_by_id("_file2"), "name").text = "p000002.xyz"
    pkg.invalidate_file_index()
    severities = {i["value"]: i["severity"] for i in Validator(pkg).run(full=True) if i["checkId"] == "file_format"}
    assert severities == {"p000001.odt": ERROR, "p000002.xyz": WARNING}


def test_kost_sample_is_schema_valid(sample_sip):
    issues = Validator(SipPackage.open_folder(sample_sip)).run(full=True)
    found = _checks(issues)
    assert not found & {"schema", "checksum", "missing_file", "surplus_file", "illegal_entries"}
