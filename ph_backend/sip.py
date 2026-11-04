"""Loading, querying, editing and saving an eCH-0160 Submission Information Package (SIP)."""

import hashlib
import os
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from lxml import etree

from . import schema, timespan

HASH_ALGORITHMS = {"MD5": "md5", "SHA-1": "sha1", "SHA-256": "sha256", "SHA-512": "sha512"}


class InvalidPackageError(Exception):
    pass


def localname(el) -> str:
    return etree.QName(el).localname if el is not None and isinstance(el.tag, str) else ""


def _safe_parser() -> etree.XMLParser:
    # Never resolve entities or touch the network for user supplied XML.
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)


def parse_xml(path: Path):
    try:
        return etree.parse(str(path), _safe_parser())
    except etree.XMLSyntaxError as exc:
        raise InvalidPackageError(
            f"Die Datei {path.name} konnte nicht gelesen werden (Zeile {exc.lineno}): {exc.msg}"
        ) from exc
    except OSError as exc:
        raise InvalidPackageError(f"Die Datei {path} konnte nicht geöffnet werden: {exc}") from exc


def file_checksum(path: Path, algorithm: str) -> str:
    digest = hashlib.new(HASH_ALGORITHMS.get(algorithm.upper(), "md5"))
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SipPackage:
    def __init__(self, metadata_path: Path, tree, root_dir: Path | None, read_only: bool):
        self.metadata_path = Path(metadata_path)
        self.tree = tree
        self.root = tree.getroot()
        self.root_dir = Path(root_dir) if root_dir else None
        self.read_only = read_only
        self.ns = etree.QName(self.root).namespace
        self._by_key: dict[int, object] = {}
        self._key_of: dict[object, int] = {}
        self._next_key = 1
        self._file_index_valid = False
        self._path_of: dict[int, PurePosixPath] = {}
        self._file_by_id: dict[str, object] = {}
        if localname(self.root) != "paket":
            raise InvalidPackageError("Die Datei metadata.xml enthält kein Element <paket>.")
        if self.delivery is None:
            raise InvalidPackageError("Fehlende Entität: Das metadata.xml enthält keine <ablieferung>.")

    # ---------------------------------------------------------------- opening

    @classmethod
    def open_folder(cls, folder: str | Path, read_only: bool = False) -> "SipPackage":
        folder = Path(folder)
        metadata = folder / "header" / "metadata.xml"
        if not folder.is_dir() or not metadata.is_file():
            raise InvalidPackageError(
                f"Beim selektierten Ordner '{folder.name}' handelt es sich um kein gültiges Paket "
                "(Ordner header oder Datei metadata.xml fehlt)."
            )
        return cls(metadata, parse_xml(metadata), folder, read_only)

    @classmethod
    def open_metadata(cls, path: str | Path) -> "SipPackage":
        path = Path(path)
        sip_root = path.parent.parent
        inside_sip = path.parent.name == "header" and (sip_root / "content").is_dir()
        # A standalone metadata.xml can only be viewed, never edited.
        return cls(path, parse_xml(path), sip_root if inside_sip else None, read_only=not inside_sip)

    # ---------------------------------------------------------------- element helpers

    def q(self, name: str) -> str:
        return f"{{{self.ns}}}{name}" if self.ns else name

    @staticmethod
    def children(el, name: str | None = None) -> list:
        if el is None:
            return []
        return [c for c in el if isinstance(c.tag, str) and (name is None or localname(c) == name)]

    def child(self, el, name: str):
        found = self.children(el, name)
        return found[0] if found else None

    def text(self, el, name: str) -> str:
        c = self.child(el, name)
        return (c.text or "").strip() if c is not None else ""

    def key(self, el) -> int:
        k = self._key_of.get(el)
        if k is None:
            k = self._next_key
            self._next_key += 1
            self._key_of[el] = k
            self._by_key[k] = el
        return k

    def element(self, key: int):
        return self._by_key.get(int(key))

    def kind(self, el) -> str:
        name = localname(el)
        if name == "dossier" and localname(el.getparent()) == "dossier":
            return "subdossier"
        return name

    @property
    def delivery(self):
        return self.child(self.root, "ablieferung")

    @property
    def provenance(self):
        return self.child(self.delivery, "provenienz")

    @property
    def classification_system(self):
        return self.child(self.delivery, "ordnungssystem")

    @property
    def table_of_contents(self):
        return self.child(self.root, "inhaltsverzeichnis")

    @property
    def delivery_type(self) -> str:
        return self.text(self.delivery, "ablieferungstyp")

    @property
    def name(self) -> str:
        return self.root_dir.name if self.root_dir else str(self.metadata_path)

    def display_name(self, el) -> str:
        kind = self.kind(el)
        if kind == "ordnungssystemposition":
            return f"{self.text(el, 'nummer')} {self.text(el, 'titel')}".strip()
        if kind in ("dossier", "subdossier", "dokument", "mappe", "vorgang"):
            return self.text(el, "titel") or "(ohne Titel)"
        if kind in ("datei", "ordner"):
            return self.text(el, "name")
        if kind == "ordnungssystem":
            return self.text(el, "name") or "Ordnungssystem"
        if kind == "ablieferung":
            return self.text(el, "ablieferungsnummer") or self.text(el, "ablieferndeStelle") or "Ablieferung"
        if kind == "provenienz":
            return self.text(el, "aktenbildnerName") or "Provenienz"
        if kind == "aktivitaet":
            return self.text(el, "vorschreibung") or "Aktivität"
        if kind == "paket":
            return self.name
        return schema.KIND_LABELS.get(kind, kind)

    def ancestors(self, el) -> list:
        """Chain from the delivery down to (excluding) el, used for the editor breadcrumb."""
        chain = []
        parent = el.getparent()
        while parent is not None and localname(parent) not in ("paket", "inhaltsverzeichnis"):
            chain.append(parent)
            parent = parent.getparent()
        return list(reversed(chain))

    # ---------------------------------------------------------------- editing

    def set_text(self, el, tag: str, value: str, required: bool = False) -> None:
        value = value.strip()
        c = self.child(el, tag)
        if not value and not required:
            if c is not None:
                el.remove(c)
            return
        if c is None:
            c = self._insert_child(el, tag)
        c.text = value

    def time_span(self, el, tag: str) -> tuple[str, str]:
        span = self.child(el, tag)
        return self.text(self.child(span, "von"), "datum"), self.text(self.child(span, "bis"), "datum")

    def time_span_display(self, el, tag: str) -> tuple[str, str]:
        span = self.child(el, tag)
        return self._point_display(self.child(span, "von")), self._point_display(self.child(span, "bis"))

    def time_point_display(self, el, tag: str) -> str:
        return self._point_display(self.child(el, tag))

    def _point_display(self, point) -> str:
        if point is None:
            return ""
        return timespan.format_point(self.text(point, "ca").lower() == "true", self.text(point, "datum"))

    def _write_point(self, point, text: str) -> None:
        approximate, value = timespan.parse_point(text)
        ca = self.child(point, "ca")
        if approximate and ca is None:
            ca = etree.Element(self.q("ca"))
            point.insert(0, ca)
        if approximate:
            ca.text = "true"
        elif ca is not None:
            point.remove(ca)
        date_el = self.child(point, "datum")
        if date_el is None:
            date_el = etree.SubElement(point, self.q("datum"))
        date_el.text = value

    def set_time_point(self, el, tag: str, text: str) -> None:
        """Raises timespan.DateFormatError for invalid input."""
        point = self.child(el, tag)
        if not text.strip():
            if point is not None:
                el.remove(point)
            return
        timespan.parse_point(text)
        if point is None:
            point = self._insert_child(el, tag)
        self._write_point(point, text)

    def set_time_span(self, el, tag: str, start: str, end: str) -> None:
        """Accepts JJJJ, TT.MM.JJJJ, JJJJ-MM-TT, 'keine Angabe' and a 'ca.' prefix; raises DateFormatError."""
        start, end = start.strip(), end.strip()
        span = self.child(el, tag)
        if not start and not end:
            if span is not None:
                el.remove(span)
            return
        timespan.parse_point(start)
        timespan.parse_point(end)
        if span is None:
            span = self._insert_child(el, tag)
        for part, value in (("von", start), ("bis", end)):
            boundary = self.child(span, part)
            if boundary is None:
                boundary = etree.SubElement(span, self.q(part))
            self._write_point(boundary, value)

    def additional_data(self, el) -> list[tuple[str, str]]:
        """Merkmale of <zusatzDaten> as (name, value) pairs."""
        container = self.child(el, "zusatzDaten")
        return [(m.get("name", ""), (m.text or "").strip()) for m in self.children(container, "merkmal")]

    def set_additional_data(self, el, items: list[tuple[str, str]]) -> None:
        """Replaces all Merkmale; <zusatzDaten> is removed when empty because it needs at least one Merkmal."""
        items = [(n.strip(), v.strip()) for n, v in items if n.strip() or v.strip()]
        container = self.child(el, "zusatzDaten")
        if container is not None:
            el.remove(container)
        if not items:
            return
        container = self._insert_child(el, "zusatzDaten")
        for name, value in items:
            merkmal = etree.SubElement(container, self.q("merkmal"))
            merkmal.set("name", name)
            merkmal.text = value

    @staticmethod
    def new_id() -> str:
        return "_" + uuid.uuid4().hex[:22]

    def create_child(self, parent, tag: str, with_id: bool = False):
        el = self._insert_child(parent, tag)
        if with_id:
            el.set("id", self.new_id())
        return el

    def remove(self, el) -> None:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)
        self.invalidate_file_index()

    def _insert_child(self, el, tag: str):
        return self.insert_element(el, etree.Element(self.q(tag)))

    def insert_element(self, parent, new, before=None):
        """Places new under parent at the position required by the XSD sequence (or before a sibling)."""
        if new.getparent() is not None:
            new.getparent().remove(new)
        if before is not None:
            before.addprevious(new)
            return new
        order = schema.CHILD_ORDER.get(self.kind(parent), [])
        tag = localname(new)
        rank = order.index(tag) if tag in order else len(order)
        for existing in self.children(parent):
            name = localname(existing)
            if name in order and order.index(name) > rank:
                existing.addprevious(new)
                break
        else:
            parent.append(new)
        return new

    # ---------------------------------------------------------------- files

    def _ensure_file_index(self) -> None:
        if self._file_index_valid:
            return
        self._path_of.clear()
        self._file_by_id.clear()

        def walk(el, base: PurePosixPath):
            for c in self.children(el):
                name = localname(c)
                if name not in ("ordner", "datei"):
                    continue
                path = base / self.text(c, "name")
                self._path_of[self.key(c)] = path
                if name == "datei" and c.get("id"):
                    self._file_by_id[c.get("id")] = c
                if name == "ordner":
                    walk(c, path)

        walk(self.table_of_contents, PurePosixPath())
        self._file_index_valid = True

    def invalidate_file_index(self) -> None:
        self._file_index_valid = False

    def walk_table_of_contents(self):
        """Yields (element, relative posix path) for every ordner/datei entry."""
        self._ensure_file_index()
        for key, path in list(self._path_of.items()):
            yield self._by_key[key], path

    def relpath(self, el) -> PurePosixPath | None:
        self._ensure_file_index()
        return self._path_of.get(self.key(el))

    def fs_path(self, el) -> Path | None:
        rel = self.relpath(el)
        if rel is None or self.root_dir is None:
            return None
        path = self.root_dir.joinpath(*rel.parts)
        # Names come from untrusted metadata; refuse anything escaping the package folder.
        if not path.resolve().is_relative_to(self.root_dir.resolve()):
            return None
        return path

    def file_by_id(self, ident: str):
        self._ensure_file_index()
        return self._file_by_id.get(ident.strip())

    def referenced_files(self, el) -> list:
        result = []
        for ref in self.children(el, "dateiRef"):
            file_el = self.file_by_id(ref.text or "")
            if file_el is not None:
                result.append(file_el)
        return result

    def referenced_ids(self) -> set[str]:
        return {(r.text or "").strip() for r in self.root.iter(self.q("dateiRef"))}

    def iter_kind(self, *names: str):
        for name in names:
            yield from self.root.iter(self.q(name))

    def xsd_path(self) -> Path | None:
        xsd_dir = self.metadata_path.parent / "xsd"
        candidates = sorted(xsd_dir.glob("*.xsd")) if xsd_dir.is_dir() else []
        for c in candidates:
            if c.name.lower() == "arelda.xsd":
                return c
        return candidates[0] if candidates else None

    # ---------------------------------------------------------------- persistence

    def save(self) -> None:
        if self.read_only:
            raise PermissionError("Das Paket ist schreibgeschützt geöffnet.")
        tmp = self.metadata_path.with_suffix(".xml.tmp")
        self.tree.write(str(tmp), encoding="UTF-8", xml_declaration=True)
        os.replace(tmp, self.metadata_path)

    def export_metadata(self, dest: str | Path) -> None:
        self.tree.write(str(dest), encoding="UTF-8", xml_declaration=True)

    def zip_to(self, dest: str | Path) -> None:
        if self.root_dir is None:
            raise InvalidPackageError("Nur ein vollständiges SIP kann gezippt werden.")
        base = self.root_dir.parent
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            for path in sorted(self.root_dir.rglob("*")):
                zf.write(path, path.relative_to(base).as_posix())
