"""Durable package-level preservation events and PREMIS 3.0 export."""

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import rfc8785
from lxml import etree

PREMIS_NS = "http://www.loc.gov/premis/v3"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
ZERO_DIGEST = "0" * 64
FORMAT_VERSION = 1


class AuditError(Exception):
    pass


@dataclass(frozen=True)
class AuditCheckpoint:
    package_identifier: str
    sequence: int
    digest: str


def _digest(previous: str, payload: bytes) -> str:
    return hashlib.sha256(bytes.fromhex(previous) + payload).hexdigest()


class AuditJournal:
    def __init__(self, path: Path, package_identifier: str | None = None, read_only: bool = False):
        self.path = Path(path).resolve()
        self.read_only = read_only
        if package_identifier is not None and not package_identifier.strip():
            raise AuditError("A package identifier must not be empty.")
        if not self.path.exists():
            if read_only:
                raise AuditError("The audit journal does not exist.")
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self._connection("rwc") as connection:
                statements = ("""CREATE TABLE journal (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        format_version INTEGER NOT NULL,
                        package_identifier TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        digest TEXT NOT NULL
                    )""", """CREATE TABLE events (
                        sequence INTEGER PRIMARY KEY,
                        payload TEXT NOT NULL,
                        previous_digest TEXT NOT NULL,
                        digest TEXT NOT NULL
                    )""", """CREATE TRIGGER immutable_event_update BEFORE UPDATE ON events
                        BEGIN SELECT RAISE(ABORT, 'Audit events are immutable'); END""",
                    """CREATE TRIGGER immutable_event_delete BEFORE DELETE ON events
                        BEGIN SELECT RAISE(ABORT, 'Audit events are immutable'); END""")
                existing = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='journal'").fetchone()
                if existing is None:
                    for statement in statements:
                        connection.execute(statement)
                    identifier = package_identifier or "urn:uuid:" + str(uuid.uuid4())
                    connection.execute("INSERT INTO journal VALUES (1, ?, ?, 0, ?)",
                                       (FORMAT_VERSION, identifier, ZERO_DIGEST))
                connection.commit()
            if os.name != "nt":
                self.path.chmod(0o600)
        with self._connection("ro") as connection:
            header, _ = self._verify(connection)
        self.package_identifier = header["package_identifier"]
        if package_identifier is not None and self.package_identifier != package_identifier:
            raise AuditError("The journal belongs to a different package.")

    @contextmanager
    def _connection(self, mode: str):
        connection = None
        try:
            connection = sqlite3.connect(self.path.as_uri() + "?mode=" + mode, uri=True, timeout=10)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN" if mode == "ro" else "BEGIN IMMEDIATE")
            yield connection
        except sqlite3.Error as exc:
            raise AuditError(f"Audit journal operation failed: {exc}") from exc
        finally:
            if connection is not None:
                connection.close()

    def _verify(self, connection, checkpoint: AuditCheckpoint | None = None):
        header = connection.execute("SELECT * FROM journal WHERE id=1").fetchone()
        if header is None or header["format_version"] != FORMAT_VERSION:
            raise AuditError("Unsupported or missing audit journal header.")
        previous = ZERO_DIGEST
        records = []
        checkpoint_found = checkpoint is None or checkpoint.sequence == 0 and checkpoint.digest == ZERO_DIGEST
        if checkpoint is not None and checkpoint.package_identifier != header["package_identifier"]:
            raise AuditError("The checkpoint belongs to a different package.")
        for expected, row in enumerate(connection.execute("SELECT * FROM events ORDER BY sequence"), start=1):
            try:
                payload = json.loads(row["payload"])
                canonical = rfc8785.dumps(payload)
                valid = (row["sequence"] == expected and row["previous_digest"] == previous
                         and row["digest"] == _digest(previous, canonical)
                         and payload["sequence"] == expected
                         and payload["packageIdentifier"] == header["package_identifier"])
            except (ValueError, TypeError, KeyError) as exc:
                raise AuditError(f"Invalid audit event at sequence {expected}.") from exc
            if not valid:
                raise AuditError(f"Audit chain verification failed at sequence {expected}.")
            previous = row["digest"]
            records.append({"payload": payload, "digest": previous, "previousDigest": row["previous_digest"]})
            if checkpoint is not None and checkpoint.sequence == expected:
                checkpoint_found = checkpoint.digest == previous
        if len(records) != header["sequence"] or previous != header["digest"]:
            raise AuditError("The audit journal head does not match its events.")
        if not checkpoint_found:
            raise AuditError("The audit journal does not match the trusted checkpoint.")
        return header, records

    def verify(self, checkpoint: AuditCheckpoint | None = None) -> AuditCheckpoint:
        with self._connection("ro") as connection:
            header, _ = self._verify(connection, checkpoint)
            return AuditCheckpoint(header["package_identifier"], header["sequence"], header["digest"])

    def records(self) -> list[dict]:
        with self._connection("ro") as connection:
            _, records = self._verify(connection)
            return records

    def append(self, event_type: str, *, agent_identifier: str, software_version: str,
               detail: dict | None = None, outcome: str = "success",
               transaction_identifier: str | None = None) -> dict:
        return self.append_many([{
            "event_type": event_type, "agent_identifier": agent_identifier,
            "software_version": software_version, "detail": detail, "outcome": outcome,
            "transaction_identifier": transaction_identifier,
        }])[0]

    def append_many(self, events: list[dict]) -> list[dict]:
        if self.read_only:
            raise AuditError("The audit journal is read-only.")
        with self._connection("rw") as connection:
            self._verify(connection)
            records = [self._append(connection, **event) for event in events]
            connection.commit()
            return records

    def _append(self, connection, event_type: str, *, agent_identifier: str, software_version: str,
                detail: dict | None = None, outcome: str = "success",
                transaction_identifier: str | None = None) -> dict:
        for value in (event_type, agent_identifier, software_version):
            if not isinstance(value, str) or not value.strip():
                raise AuditError("Event type, operator and software version are required.")
        if outcome not in ("success", "failure", "discarded"):
            raise AuditError("Unsupported audit event outcome.")
        if detail is not None and not isinstance(detail, dict):
            raise AuditError("Event detail must be a JSON object.")
        if transaction_identifier is not None and not transaction_identifier.strip():
            raise AuditError("A transaction identifier must not be empty.")
        header = connection.execute("SELECT * FROM journal WHERE id=1").fetchone()
        if header["package_identifier"] != self.package_identifier:
            raise AuditError("The journal package identity has changed.")
        payload = {
            "sequence": header["sequence"] + 1,
            "packageIdentifier": self.package_identifier,
            "eventIdentifier": "urn:uuid:" + str(uuid.uuid4()),
            "eventType": event_type,
            "eventDateTime": datetime.now(timezone.utc).isoformat(),
            "agentIdentifier": agent_identifier,
            "softwareVersion": software_version,
            "transactionIdentifier": transaction_identifier or "urn:uuid:" + str(uuid.uuid4()),
            "outcome": outcome,
            "detail": {} if detail is None else detail,
        }
        try:
            canonical = rfc8785.dumps(payload)
        except (ValueError, TypeError) as exc:
            raise AuditError("Event detail cannot be encoded as canonical JSON.") from exc
        digest = _digest(header["digest"], canonical)
        connection.execute("INSERT INTO events VALUES (?, ?, ?, ?)",
                           (payload["sequence"], canonical.decode("utf-8"), header["digest"], digest))
        connection.execute("UPDATE journal SET sequence=?, digest=? WHERE id=1",
                           (payload["sequence"], digest))
        return {"payload": json.loads(canonical), "digest": digest, "previousDigest": header["digest"]}

    def premis_xml(self, redact_values: bool = False) -> bytes:
        records = self.records()
        root = etree.Element(f"{{{PREMIS_NS}}}premis", nsmap={"premis": PREMIS_NS, "xsi": XSI_NS}, version="3.0")

        def child(parent, name: str, text: str | None = None):
            element = etree.SubElement(parent, f"{{{PREMIS_NS}}}{name}")
            if text is not None:
                element.text = text
            return element

        def identifier(parent, name: str, value: str, kind: str = "local"):
            container = child(parent, name)
            child(container, name + "Type", kind)
            child(container, name + "Value", value)
            return container

        package = child(root, "object")
        package.set(f"{{{XSI_NS}}}type", "premis:representation")
        identifier(package, "objectIdentifier", self.package_identifier)
        operators = set()
        software_versions = set()
        for record in records:
            payload = record["payload"]
            event = child(root, "event")
            identifier(event, "eventIdentifier", payload["eventIdentifier"], "URN")
            child(event, "eventType", payload["eventType"])
            child(event, "eventDateTime", payload["eventDateTime"])
            information = child(event, "eventDetailInformation")
            exported_detail = {
                "profile": "package-turbo-audit-v1",
                "sequence": payload["sequence"],
                "transactionIdentifier": payload["transactionIdentifier"],
                "sourceEventDigest": record["digest"],
                "previousDigest": record["previousDigest"],
                "redacted": redact_values,
            }
            if not redact_values:
                exported_detail["detail"] = payload["detail"]
            child(information, "eventDetail", rfc8785.dumps(exported_detail).decode("utf-8"))
            outcome = child(event, "eventOutcomeInformation")
            child(outcome, "eventOutcome", payload["outcome"])
            operator = identifier(event, "linkingAgentIdentifier", payload["agentIdentifier"])
            child(operator, "linkingAgentRole", "implementer")
            software_id = "package-turbo:" + payload["softwareVersion"]
            software = identifier(event, "linkingAgentIdentifier", software_id)
            child(software, "linkingAgentRole", "executing program")
            identifier(event, "linkingObjectIdentifier", self.package_identifier)
            operators.add(payload["agentIdentifier"])
            software_versions.add(payload["softwareVersion"])
        for operator_id in sorted(operators):
            operator = child(root, "agent")
            identifier(operator, "agentIdentifier", operator_id)
            child(operator, "agentType", "person")
        for version in sorted(software_versions):
            software = child(root, "agent")
            identifier(software, "agentIdentifier", "package-turbo:" + version)
            child(software, "agentName", "Package Turbo")
            child(software, "agentType", "software")
            child(software, "agentVersion", version)
        return etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)

    def mets_xml(self, package_filename: str, package_sha256: str, *, premis_filename: str = "premis.xml",
                 version: str = "2", redact_values: bool = False) -> bytes:
        if version not in ("2", "1.12.1"):
            raise AuditError("Unsupported METS export version.")
        for filename in (package_filename, premis_filename):
            path = PurePosixPath(filename)
            if (not filename or path.is_absolute() or any(part in (".", "..") for part in filename.split("/"))
                    or ":" in filename or "\\" in filename or "\x00" in filename or filename.endswith("/")):
                raise AuditError("Companion paths must be safe relative paths.")
        if package_filename == premis_filename:
            raise AuditError("The package and PREMIS references must be different files.")
        if len(package_sha256) != 64 or any(character not in "0123456789abcdefABCDEF" for character in package_sha256):
            raise AuditError("The package needs a SHA-256 digest.")
        premis_bytes = self.premis_xml(redact_values=redact_values)
        namespace = "http://www.loc.gov/METS/v2" if version == "2" else "http://www.loc.gov/METS/"
        xlink = "http://www.w3.org/1999/xlink"
        namespaces = {"mets": namespace}
        if version != "2":
            namespaces["xlink"] = xlink
        root = etree.Element(f"{{{namespace}}}mets", nsmap=namespaces, OBJID=self.package_identifier,
                             PROFILE="urn:package-turbo:mets-companion:1",
                             LABEL="Package Turbo companion: " + ("REDACTED" if redact_values else "FULL"))

        def child(parent, name: str, **attributes):
            return etree.SubElement(parent, f"{{{namespace}}}{name}", **attributes)

        def location(parent, name: str, filename: str, **attributes):
            element = child(parent, name, LOCTYPE="URL", **attributes)
            element.set("LOCREF" if version == "2" else f"{{{xlink}}}href", quote(filename, safe="/"))
            return element

        if version == "2":
            section = child(root, "mdSec")
            provenance = child(section, "md", ID="preservation", USE="DIGIPROV")
        else:
            section = child(root, "amdSec")
            provenance = child(section, "digiprovMD", ID="preservation")
        location(provenance, "mdRef", premis_filename, MDTYPE="PREMIS", MIMETYPE="application/xml",
                 CHECKSUM=hashlib.sha256(premis_bytes).hexdigest(), CHECKSUMTYPE="SHA-256")
        files = child(root, "fileSec")
        group = child(files, "fileGrp", USE="SIP")
        metadata_reference = {"MDID" if version == "2" else "ADMID": "preservation"}
        package = child(group, "file", ID="sip", MIMETYPE="application/zip", CHECKSUM=package_sha256.lower(),
                        CHECKSUMTYPE="SHA-256", **metadata_reference)
        location(package, "FLocat", package_filename)
        structures = child(root, "structSec") if version == "2" else root
        structure = child(structures, "structMap", TYPE="physical")
        division = child(structure, "div", TYPE="SIP", **metadata_reference)
        child(division, "fptr", FILEID="sip")
        return etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)