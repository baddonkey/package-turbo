import pytest

from ph_backend import timespan
from ph_backend.sip import InvalidPackageError, SipPackage, localname


def test_open_folder_and_query(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    assert pkg.delivery_type == "GEVER"
    assert pkg.text(pkg.provenance, "aktenbildnerName") == "Testamt"
    dossiers = list(pkg.iter_kind("dossier"))
    assert [pkg.display_name(d) for d in dossiers] == ["Dossier mit Datei", "Leer"]
    assert pkg.referenced_ids() == {"_file1"}
    file_el = pkg.file_by_id("_file1")
    assert pkg.relpath(file_el).as_posix() == "content/d0001/p000001.pdf"
    assert pkg.fs_path(file_el).is_file()


def test_open_invalid_folder(tmp_path):
    with pytest.raises(InvalidPackageError):
        SipPackage.open_folder(tmp_path)


def test_open_standalone_metadata_is_read_only(sip_dir, tmp_path):
    copy = tmp_path / "metadata.xml"
    copy.write_bytes((sip_dir / "header" / "metadata.xml").read_bytes())
    pkg = SipPackage.open_metadata(copy)
    assert pkg.read_only and pkg.root_dir is None
    assert not SipPackage.open_metadata(sip_dir / "header" / "metadata.xml").read_only


def test_set_text_inserts_in_schema_order_and_saves(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    dossier = next(pkg.iter_kind("dossier"))
    pkg.set_text(dossier, "schutzfrist", "50")
    pkg.set_text(dossier, "inhalt", "Beschreibung")
    names = [localname(c) for c in pkg.children(dossier)]
    assert names.index("titel") < names.index("inhalt") < names.index("entstehungszeitraum")
    assert names.index("aktenzeichen") < names.index("schutzfrist") < names.index("dokument")
    pkg.save()
    reopened = SipPackage.open_folder(sip_dir)
    assert reopened.text(next(reopened.iter_kind("dossier")), "schutzfrist") == "50"


def test_set_text_empty_removes_optional_element(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    delivery = pkg.delivery
    pkg.set_text(delivery, "ablieferungsnummer", "")
    assert pkg.child(delivery, "ablieferungsnummer") is None


def test_time_span_roundtrip(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    dossier = next(pkg.iter_kind("dossier"))
    pkg.set_time_span(dossier, "entstehungszeitraum", "2001", "")
    assert pkg.time_span(dossier, "entstehungszeitraum") == ("2001", "keine Angabe")
    with pytest.raises(timespan.DateFormatError):
        pkg.set_time_span(dossier, "entstehungszeitraum", "2001-02", "")
    with pytest.raises(timespan.DateFormatError):
        pkg.set_time_span(dossier, "entstehungszeitraum", "31.02.2001", "")
    pkg.set_time_span(dossier, "entstehungszeitraum", "ca. 2001", "31.12.2002")
    assert pkg.time_span(dossier, "entstehungszeitraum") == ("2001", "2002-12-31")
    pkg.set_time_span(dossier, "entstehungszeitraum", "2001", "2002")
    assert pkg.time_span_display(dossier, "entstehungszeitraum") == ("2001", "2002")


def test_save_rejected_when_read_only(sip_dir):
    pkg = SipPackage.open_folder(sip_dir, read_only=True)
    with pytest.raises(PermissionError):
        pkg.save()


def test_fs_path_refuses_traversal(sip_dir):
    pkg = SipPackage.open_folder(sip_dir)
    file_el = pkg.file_by_id("_file2")
    pkg.child(file_el, "name").text = "../../../../outside.txt"
    pkg.invalidate_file_index()
    assert pkg.fs_path(file_el) is None


def test_zip(sip_dir, tmp_path):
    import zipfile

    pkg = SipPackage.open_folder(sip_dir)
    target = tmp_path / "out.zip"
    pkg.zip_to(target)
    names = zipfile.ZipFile(target).namelist()
    assert f"{sip_dir.name}/header/metadata.xml" in names


@pytest.mark.parametrize("value,lower,upper", [
    ("2006", "2006-01-01", "2006-12-31"),
    ("2008-02", "2008-02-01", "2008-02-29"),
    ("2010-05-17", "2010-05-17", "2010-05-17"),
])
def test_timespan_parsing(value, lower, upper):
    assert timespan.parse_lower(value).isoformat() == lower
    assert timespan.parse_upper(value).isoformat() == upper


def test_timespan_open():
    assert timespan.is_open("keine Angabe") and timespan.is_open("") and not timespan.is_open("2001")
