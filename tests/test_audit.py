import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pytest
from lxml import etree

from ph_backend.audit import AuditCheckpoint, AuditError, AuditJournal, PREMIS_NS, ZERO_DIGEST


def _append(journal, **kwargs):
    return journal.append("metadata modification", agent_identifier="operator:test",
                          software_version="0.1.0", **kwargs)


def test_journal_survives_reopen_and_preserves_details(tmp_path):
    path = tmp_path / "audit" / "journal.sqlite3"
    journal = AuditJournal(path)
    detail = {"target": "_dos1", "field": "titel", "old": "Old", "new": "New"}
    first = _append(journal, detail=detail)
    detail["new"] = "Changed caller value"
    checkpoint = journal.verify()
    assert checkpoint.sequence == 1 and checkpoint.digest == first["digest"]
    reopened = AuditJournal(path, package_identifier=journal.package_identifier)
    assert reopened.verify(checkpoint) == checkpoint
    assert reopened.records()[0]["payload"]["detail"]["new"] == "New"
    timestamp = datetime.fromisoformat(first["payload"]["eventDateTime"])
    assert timestamp.utcoffset() == timezone.utc.utcoffset(timestamp)


def test_empty_journal_and_wrong_identity(tmp_path):
    path = tmp_path / "journal.sqlite3"
    journal = AuditJournal(path)
    assert journal.verify() == AuditCheckpoint(journal.package_identifier, 0, ZERO_DIGEST)
    with pytest.raises(AuditError, match="different package"):
        AuditJournal(path, package_identifier="other-package")
    with pytest.raises(AuditError, match="different package"):
        journal.verify(AuditCheckpoint("other", 0, ZERO_DIGEST))


def test_read_only_journal_never_creates_or_appends(tmp_path):
    path = tmp_path / "missing" / "journal.sqlite3"
    with pytest.raises(AuditError, match="does not exist"):
        AuditJournal(path, read_only=True)
    assert not path.parent.exists()
    writable = AuditJournal(path)
    _append(writable)
    before = path.read_bytes()
    journal = AuditJournal(path, read_only=True)
    assert len(journal.records()) == 1
    with pytest.raises(AuditError, match="read-only"):
        _append(journal)
    assert path.read_bytes() == before


def test_concurrent_appends_form_one_chain(tmp_path):
    path = tmp_path / "journal.sqlite3"
    journal = AuditJournal(path)

    def append_one(number):
        writer = AuditJournal(path, package_identifier=journal.package_identifier)
        return _append(writer, detail={"number": number})

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(append_one, range(12)))
    assert journal.verify().sequence == 12
    assert sorted(result["payload"]["sequence"] for result in results) == list(range(1, 13))


def test_events_are_immutable_and_tampering_is_detected(tmp_path):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    _append(journal)
    with sqlite3.connect(journal.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("DELETE FROM events")
        connection.execute("DROP TRIGGER immutable_event_update")
        connection.execute("UPDATE events SET payload='{}' WHERE sequence=1")
    with pytest.raises(AuditError):
        journal.verify()
    with pytest.raises(AuditError):
        _append(journal)


def test_sql_failure_rolls_back_event_and_head(tmp_path):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    _append(journal)
    before = journal.verify()
    with sqlite3.connect(journal.path) as connection:
        connection.execute("""CREATE TRIGGER fail_head_update BEFORE UPDATE ON journal
                              BEGIN SELECT RAISE(ABORT, 'Simulated journal write failure'); END""")
    with pytest.raises(AuditError, match="Simulated journal write failure"):
        _append(journal)
    assert journal.verify() == before
    assert len(journal.records()) == 1


def test_atomic_event_batch_rolls_back_all_on_failure(tmp_path):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    event = {"event_type": "metadata modification", "agent_identifier": "operator",
             "software_version": "0.1.0", "transaction_identifier": "batch-1"}
    with pytest.raises(AuditError, match="required"):
        journal.append_many([event, {**event, "agent_identifier": ""}])
    assert journal.verify().sequence == 0
    records = journal.append_many([event, event])
    assert len(records) == 2 and journal.verify().sequence == 2
    assert records[1]["previousDigest"] == records[0]["digest"]


def test_truncation_and_trusted_checkpoint_are_checked(tmp_path):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    _append(journal)
    first = journal.verify()
    _append(journal)
    second = journal.verify()
    assert journal.verify(first) == second
    with sqlite3.connect(journal.path) as connection:
        connection.execute("DROP TRIGGER immutable_event_delete")
        connection.execute("DELETE FROM events WHERE sequence=2")
    with pytest.raises(AuditError, match="head"):
        journal.verify()
    with sqlite3.connect(journal.path) as connection:
        connection.execute("UPDATE journal SET sequence=1, digest=?", (first.digest,))
    assert journal.verify(first) == first
    with pytest.raises(AuditError, match="checkpoint"):
        journal.verify(second)


@pytest.mark.parametrize("detail", [{"invalid": float("nan")}, {"invalid": object()}])
def test_unencodable_events_do_not_advance_journal(tmp_path, detail):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    with pytest.raises(AuditError, match="canonical JSON"):
        _append(journal, detail=detail)
    assert journal.verify().sequence == 0


def test_failed_and_discarded_events_remain_distinct(tmp_path):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    for outcome in ("failure", "discarded", "success"):
        _append(journal, outcome=outcome, transaction_identifier="transaction-1")
    records = journal.records()
    assert [record["payload"]["outcome"] for record in records] == ["failure", "discarded", "success"]
    assert {record["payload"]["transactionIdentifier"] for record in records} == {"transaction-1"}


@pytest.mark.parametrize("redact_values", [False, True])
def test_premis_export_validates_and_resolves_links(tmp_path, redact_values):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    _append(journal, detail={"old": "Sensitive previous value", "new": "Current value"})
    _append(journal, outcome="failure")
    xml = journal.premis_xml(redact_values=redact_values)
    root = etree.fromstring(xml)
    schema_path = Path(__file__).resolve().parent.parent / "ph_backend/resources/preservation/premis-v3-0.xsd"
    etree.XMLSchema(etree.parse(str(schema_path))).assertValid(root)
    namespaces = {"p": PREMIS_NS}
    assert root.get("version") == "3.0"
    agents = set(root.xpath("p:agent/p:agentIdentifier/p:agentIdentifierValue/text()", namespaces=namespaces))
    assert set(root.xpath("p:event/p:linkingAgentIdentifier/p:linkingAgentIdentifierValue/text()",
                          namespaces=namespaces)) <= agents
    assert set(root.xpath("p:event/p:linkingObjectIdentifier/p:linkingObjectIdentifierValue/text()",
                          namespaces=namespaces)) == {journal.package_identifier}
    assert (b"Sensitive previous value" in xml) is not redact_values
    for text in root.xpath("p:event/p:eventDetailInformation/p:eventDetail/text()", namespaces=namespaces):
        exported = json.loads(text)
        assert exported["redacted"] is redact_values
    assert journal.premis_xml(redact_values=redact_values) == xml
    assert journal.records()[0]["payload"]["detail"]["old"] == "Sensitive previous value"


def test_empty_premis_export_is_valid(tmp_path):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    schema_path = Path(__file__).resolve().parent.parent / "ph_backend/resources/preservation/premis-v3-0.xsd"
    etree.XMLSchema(etree.parse(str(schema_path))).assertValid(etree.fromstring(journal.premis_xml()))


@pytest.mark.parametrize("version", ["2", "1.12.1"])
@pytest.mark.parametrize("redact_values", [False, True])
def test_mets_companion_validates_with_fixity_and_resolved_ids(tmp_path, version, redact_values):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    _append(journal, detail={"old": "Private value"})
    digest = hashlib.sha256(b"Example SIP archive bytes").hexdigest()
    xml = journal.mets_xml("SIP Test.zip", digest, version=version, redact_values=redact_values)
    root = etree.fromstring(xml)
    base = Path(__file__).resolve().parent.parent / "ph_backend/resources/preservation"
    schema = base / ("mets2.xsd" if version == "2" else "mets-1.12.1.xsd")
    etree.XMLSchema(etree.parse(str(schema), etree.XMLParser(no_network=True))).assertValid(root)
    assert root.get("OBJID") == journal.package_identifier
    assert root.get("LABEL").endswith("REDACTED" if redact_values else "FULL")
    reference = root.xpath("//*[local-name()='mdRef']")[0]
    assert reference.get("CHECKSUM") == hashlib.sha256(journal.premis_xml(redact_values)).hexdigest()
    locator = root.xpath("//*[local-name()='FLocat']")[0]
    attribute = "LOCREF" if version == "2" else "{http://www.w3.org/1999/xlink}href"
    assert locator.get(attribute) == "SIP%20Test.zip"
    identifiers = set(root.xpath("//@ID"))
    assert set(root.xpath("//@FILEID")) <= identifiers
    assert set(root.xpath("//@MDID | //@ADMID")) <= identifiers
    assert journal.mets_xml("SIP Test.zip", digest, version=version, redact_values=redact_values) == xml


@pytest.mark.parametrize("filename", ["../package.zip", "/package.zip", "C:/package.zip", "a\\package.zip", "./package.zip"])
def test_mets_rejects_unsafe_companion_references(tmp_path, filename):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    with pytest.raises(AuditError, match="safe relative"):
        journal.mets_xml(filename, "a" * 64)


def test_mets_rejects_unsupported_version_and_invalid_digest(tmp_path):
    journal = AuditJournal(tmp_path / "journal.sqlite3")
    with pytest.raises(AuditError, match="Unsupported METS"):
        journal.mets_xml("sip.zip", "a" * 64, version="3")
    with pytest.raises(AuditError, match="SHA-256"):
        journal.mets_xml("sip.zip", "not-a-digest")