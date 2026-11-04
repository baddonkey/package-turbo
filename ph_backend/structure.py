"""Editing the classification system (Ordnungssystem-Navigator, user documentation 8.1.2 and 8.3, 9.2, 9.4)."""

import csv
import re
from pathlib import Path

from . import schema, timespan, xsd_info
from .sip import SipPackage, localname


class StructureError(Exception):
    pass


CONTAINERS = {
    "ordnungssystemposition": ("ordnungssystem", "ordnungssystemposition"),
    "dossier": ("ordnungssystemposition", "dossier", "subdossier"),
    "dokument": ("dossier", "subdossier", "mappe"),
    "mappe": ("ordnungssystem", "ordnungssystemposition", "dossier", "subdossier", "mappe"),
}
DEFAULT_TITLES = {
    "ordnungssystemposition": "Neue Ordnungssystemposition",
    "dossier": "Neues Dossier",
    "dokument": "Neues Dokument",
    "mappe": "Neue Mappe",
}


def _check_parent(pkg: SipPackage, parent, tag: str) -> None:
    kind = pkg.kind(parent)
    if kind not in CONTAINERS[tag]:
        raise StructureError(f"{schema.KIND_LABELS.get(tag, tag)} kann nicht unter "
                             f"{schema.KIND_LABELS.get(kind, kind)} angelegt werden.")
    if tag == "ordnungssystemposition" and pkg.children(parent, "dossier"):
        raise StructureError("Unter einer Ordnungssystemposition mit Dossiers können keine weiteren "
                             "Ordnungssystempositionen angelegt werden.")
    if tag == "dossier" and kind == "ordnungssystemposition" and pkg.children(parent, "ordnungssystemposition"):
        raise StructureError("Dossiers können nur auf der untersten Stufe des Ordnungssystems angelegt werden.")


def _number_of(pkg: SipPackage, el) -> str:
    kind = pkg.kind(el)
    if kind == "ordnungssystemposition":
        return pkg.text(el, "nummer")
    if kind in ("dossier", "subdossier"):
        return pkg.text(el, "aktenzeichen")
    return ""


def _next_number(pkg: SipPackage, parent, tag: str) -> str:
    field = "nummer" if tag == "ordnungssystemposition" else "aktenzeichen"
    used = {pkg.text(c, field) for c in pkg.children(parent, tag)}
    prefix = _number_of(pkg, parent)
    separator = "" if tag == "ordnungssystemposition" else ("." if prefix else "")
    index = len(pkg.children(parent, tag))
    while True:
        candidate = f"{prefix}{separator}{index}"
        if candidate not in used:
            return candidate
        index += 1


def add_objects(pkg: SipPackage, parent, tag: str, count: int = 1, title: str | None = None) -> list:
    """Neue Ordnungssystemposition / Dossier / Dokument / Mappe (also several at once)."""
    _check_parent(pkg, parent, tag)
    created = []
    for _ in range(max(1, count)):
        el = pkg.create_child(parent, tag, with_id=True)
        if tag == "ordnungssystemposition":
            pkg.set_text(el, "nummer", _next_number(pkg, parent, tag), required=True)
        elif tag == "dossier":
            pkg.set_text(el, "aktenzeichen", _next_number(pkg, parent, tag), required=True)
        pkg.set_text(el, "titel", title or DEFAULT_TITLES[tag], required=True)
        if tag == "dokument":
            pkg.set_text(el, "erscheinungsform", "digital")
        fill_required(pkg, el)
        created.append(el)
    return created


_SPAN_TYPES = {"historischerZeitraum", "zeitraum"}


def fill_required(pkg: SipPackage, el) -> None:
    """Adds XSD-mandatory simple elements that are still missing, with neutral default values."""
    info = xsd_info.for_package(pkg)
    for element in info.elements(xsd_info.type_name(pkg, el, info)):
        if element.min_occurs == 0 or pkg.child(el, element.name) is not None:
            continue
        if element.name in schema.STRUCTURAL_TAGS:
            continue
        if element.type in _SPAN_TYPES:
            pkg.set_time_span(el, element.name, timespan.NOT_SPECIFIED, timespan.NOT_SPECIFIED)
            continue
        choices = info.simple(element.type).enums
        default = "digital" if "digital" in choices else (choices[0] if choices else timespan.NOT_SPECIFIED)
        pkg.set_text(el, element.name, default, required=True)


def delete(pkg: SipPackage, elements) -> int:
    count = 0
    for el in elements:
        if localname(el) in ("ordnungssystem", "ablieferung", "paket"):
            raise StructureError("Das Ordnungssystem selbst kann nicht gelöscht werden.")
        if el.getparent() is not None:
            pkg.remove(el)
            count += 1
    return count


def unassign(pkg: SipPackage, owner, file_el) -> bool:
    ident = file_el.get("id", "")
    for ref in pkg.children(owner, "dateiRef"):
        if (ref.text or "").strip() == ident:
            owner.remove(ref)
            return True
    return False


def _is_ancestor(candidate, el) -> bool:
    node = el
    while node is not None:
        if node is candidate:
            return True
        node = node.getparent()
    return False


def move(pkg: SipPackage, el, new_parent, before=None) -> None:
    tag = localname(el)
    if tag not in CONTAINERS:
        raise StructureError("Dieses Objekt kann nicht verschoben werden.")
    if _is_ancestor(el, new_parent):
        raise StructureError("Ein Objekt kann nicht in sich selbst verschoben werden.")
    if new_parent is not el.getparent():
        _check_parent(pkg, new_parent, tag)
    pkg.insert_element(new_parent, el, before=before)


def move_relative(pkg: SipPackage, el, offset: int) -> bool:
    """Moves el up (-1) or down (+1) among its siblings of the same type."""
    siblings = pkg.children(el.getparent(), localname(el))
    index = siblings.index(el) + offset
    if not 0 <= index < len(siblings):
        return False
    if offset < 0:
        siblings[index].addprevious(el)
    else:
        siblings[index].addnext(el)
    return True


def _accepts_file_refs(pkg: SipPackage, el) -> bool:
    info = xsd_info.for_package(pkg)
    return info.element(xsd_info.type_name(pkg, el, info), "dateiRef") is not None


def _title_for_file(pkg: SipPackage, file_el) -> str:
    name = pkg.text(file_el, "originalName") or pkg.text(file_el, "name")
    return Path(name).stem or name


def assign_files(pkg: SipPackage, target, files, create_documents: bool = False) -> int:
    """Assigns files to a dossier, document or folder (Mappe); GEVER dossiers get one document per file."""
    kind = pkg.kind(target)
    if kind not in ("dossier", "subdossier", "dokument", "mappe"):
        raise StructureError("Dateien können nur Dossiers, Dokumenten oder Mappen zugewiesen werden.")
    existing = {(r.text or "").strip() for r in pkg.children(target, "dateiRef")}
    use_documents = kind in ("dossier", "subdossier") and (create_documents or not _accepts_file_refs(pkg, target))
    count = 0
    for file_el in files:
        ident = file_el.get("id")
        if not ident or ident in existing:
            continue
        holder = add_objects(pkg, target, "dokument", 1, _title_for_file(pkg, file_el))[0] if use_documents else target
        ref = pkg.create_child(holder, "dateiRef")
        ref.text = ident
        count += 1
    return count


def document_for_file(pkg: SipPackage, owner, file_el):
    """Neues Dokument für diese Datei: replaces a direct file reference of a dossier by a document."""
    if not unassign(pkg, owner, file_el):
        raise StructureError("Die Datei ist dem Objekt nicht direkt zugewiesen.")
    doc = add_objects(pkg, owner, "dokument", 1, _title_for_file(pkg, file_el))[0]
    pkg.create_child(doc, "dateiRef").text = file_el.get("id")
    return doc


def documents_for_files(pkg: SipPackage, dossier) -> int:
    files = pkg.referenced_files(dossier)
    for file_el in files:
        document_for_file(pkg, dossier, file_el)
    return len(files)


def renumber(pkg: SipPackage, scheme: str = "decimal") -> int:
    """Ordnungssystem neu nummerieren: 'decimal' (freie Zehnergliederung) or 'hundred' (00-99 per level)."""
    width, limit = (1, 10) if scheme == "decimal" else (2, 100)
    count = 0

    def walk(parent, prefix: str) -> None:
        nonlocal count
        positions = pkg.children(parent, "ordnungssystemposition")
        if len(positions) > limit:
            raise StructureError(f"Auf einer Stufe sind höchstens {limit} Positionen möglich "
                                 f"({len(positions)} unter «{pkg.display_name(parent)}»).")
        for index, position in enumerate(positions):
            number = f"{prefix}{index:0{width}d}"
            pkg.set_text(position, "nummer", number, required=True)
            count += 1
            walk(position, number)

    walk(pkg.classification_system, "")
    return count


def _span_bounds(pkg: SipPackage, elements):
    lower, upper = None, None
    for el in elements:
        start, end = pkg.time_span(el, "entstehungszeitraum")
        lo, up = timespan.parse_lower(start), timespan.parse_upper(end)
        if lo and (lower is None or lo < lower[0]):
            lower = (lo, start)
        if up and (upper is None or up > upper[0]):
            upper = (up, end)
    return (lower[1] if lower else ""), (upper[1] if upper else "")


def accumulate_time_spans(pkg: SipPackage, el) -> tuple[str, str]:
    """Zeiträume kumulieren: span of el covers all spans below it ('keine Angabe' is ignored)."""
    if localname(el) == "ablieferung":
        sources = list(pkg.iter_kind("dossier"))
    else:
        sources = [d for d in el.iter(pkg.q("dossier"), pkg.q("dokument")) if d is not el]
    start, end = _span_bounds(pkg, sources)
    if start or end:
        pkg.set_time_span(el, "entstehungszeitraum", start or timespan.NOT_SPECIFIED, end or timespan.NOT_SPECIFIED)
    return start, end


def propagate_time_span_up(pkg: SipPackage, el):
    """'nach oben übernehmen': widens the parent span (dossier or delivery) so that it contains el."""
    parent = el.getparent()
    if localname(parent) != "dossier":
        parent = pkg.delivery
    start, end = _span_bounds(pkg, [parent, el])
    pkg.set_time_span(parent, "entstehungszeitraum", start or timespan.NOT_SPECIFIED, end or timespan.NOT_SPECIFIED)
    return parent


# ---------------------------------------------------------------- mass assignment (8.3.1)

def _validate_mass_target(pkg: SipPackage, target, osp_levels: int, dossier_levels: int) -> None:
    target_kind = pkg.kind(target)
    if osp_levels < 0 or dossier_levels < 0:
        raise StructureError("Die Anzahl der Stufen darf nicht negativ sein.")
    if target_kind == "ordnungssystem" and osp_levels < 1:
        raise StructureError("Die Struktur muss mindestens eine Ordnungssystemposition enthalten "
                             "(Anzahl OSP Stufen mindestens 1).")
    if target_kind == "ordnungssystemposition":
        if pkg.children(target, "dossier") and osp_levels > 0:
            raise StructureError("Unter einer Ordnungssystemposition mit Dossiers können keine OSP Stufen erstellt werden.")
        if pkg.children(target, "ordnungssystemposition") and osp_levels == 0:
            raise StructureError("Dossiers können nicht neben Ordnungssystempositionen angelegt werden.")
    if target_kind in ("dossier", "subdossier") and osp_levels > 0:
        raise StructureError("Unter einem Dossier können keine OSP Stufen angelegt werden.")
    if target_kind not in ("ordnungssystem", "ordnungssystemposition", "dossier", "subdossier"):
        raise StructureError("Die Massenzuweisung ist nur auf das Ordnungssystem, eine OSP oder ein Dossier möglich.")


def _mass_assign_plan(pkg: SipPackage, folders, target, osp_levels: int, dossier_levels: int,
                      create_documents: bool, include_top: bool,
                      overrides: dict[int, tuple[int, int]]) -> dict:
    _validate_mass_target(pkg, target, osp_levels, dossier_levels)
    folders = [folder for folder in folders if pkg.kind(folder) == "ordner"]
    if not folders:
        raise StructureError("Wählen Sie mindestens einen Ordner aus.")

    folders = [folder for folder in folders if not any(
        other is not folder and _is_ancestor(other, folder) for other in folders
    )]
    operations: list[dict] = []
    rows: list[dict] = []
    created = assigned = unassigned = 0
    next_virtual = 0

    def add_node(parent_ref, parent_kind: str, folder, kind: str) -> str:
        nonlocal created, next_virtual
        if isinstance(parent_ref, int):
            parent = pkg.element(parent_ref)
            if parent is None:
                raise StructureError("Das gewählte Zuweisungsziel ist nicht mehr verfügbar.")
            _check_parent(pkg, parent, kind)
        elif parent_kind not in CONTAINERS[kind]:
            raise StructureError(f"{schema.KIND_LABELS.get(kind, kind)} kann nicht unter "
                                 f"{schema.KIND_LABELS.get(parent_kind, parent_kind)} angelegt werden.")
        ref = f"new-{next_virtual}"
        next_virtual += 1
        operations.append({
            "type": "create",
            "id": ref,
            "parent": parent_ref,
            "kind": kind,
            "title": pkg.text(folder, "originalName") or pkg.text(folder, "name"),
        })
        created += 1
        return ref

    def place_files(folder, holder_ref, holder_kind: str) -> int:
        nonlocal assigned, unassigned
        files_in_folder = pkg.children(folder, "datei")
        file_keys = [pkg.key(file_el) for file_el in files_in_folder]
        if holder_kind in ("dossier", "subdossier"):
            operations.append({
                "type": "assign",
                "owner": holder_ref,
                "files": file_keys,
                "documents": create_documents,
            })
            assigned += len(file_keys)
            return len(file_keys)
        unassigned += len(file_keys)
        return 0

    def walk(folder, parent_ref, parent_kind: str, depth: int, active_osp: int,
             active_dossier: int, tree_depth: int) -> None:
        key = pkg.key(folder)
        if key in overrides:
            active_osp, active_dossier = overrides[key]
            depth = 1

        holder_ref, holder_kind = parent_ref, parent_kind
        stage, stage_number = "unassigned", 0
        if depth <= active_osp:
            holder_kind = "ordnungssystemposition"
            holder_ref = add_node(parent_ref, parent_kind, folder, holder_kind)
            stage, stage_number = "osp", depth
        elif depth <= active_osp + active_dossier:
            holder_kind = "dossier"
            holder_ref = add_node(parent_ref, parent_kind, folder, holder_kind)
            stage_number = depth - active_osp
            stage = "dossier" if stage_number == 1 else "subdossier"
        elif holder_kind in ("dossier", "subdossier"):
            stage = "existingDossier"

        file_count = place_files(folder, holder_ref, holder_kind)
        rows.append({
            "key": key,
            "name": pkg.text(folder, "originalName") or pkg.text(folder, "name"),
            "depth": tree_depth,
            "stage": stage,
            "stageNumber": stage_number,
            "fileCount": len(pkg.children(folder, "datei")),
            "assignedCount": file_count,
            "ospLevels": active_osp,
            "dossierLevels": active_dossier,
        })
        for subfolder in pkg.children(folder, "ordner"):
            walk(subfolder, holder_ref, holder_kind, depth + 1, active_osp, active_dossier, tree_depth + 1)

    target_ref, target_kind = pkg.key(target), pkg.kind(target)
    for folder in folders:
        key = pkg.key(folder)
        active_osp, active_dossier = overrides.get(key, (osp_levels, dossier_levels))
        if include_top:
            walk(folder, target_ref, target_kind, 1, active_osp, active_dossier, 0)
        else:
            file_count = place_files(folder, target_ref, target_kind)
            rows.append({
                "key": key,
                "name": pkg.text(folder, "originalName") or pkg.text(folder, "name"),
                "depth": 0,
                "stage": "topExcluded",
                "stageNumber": 0,
                "fileCount": len(pkg.children(folder, "datei")),
                "assignedCount": file_count,
                "ospLevels": active_osp,
                "dossierLevels": active_dossier,
            })
            for subfolder in pkg.children(folder, "ordner"):
                walk(subfolder, target_ref, target_kind, 1, active_osp, active_dossier, 1)

    return {
        "operations": operations,
        "rows": rows,
        "created": created,
        "assigned": assigned,
        "unassigned": unassigned,
    }


def _apply_mass_assign_plan(pkg: SipPackage, plan: dict) -> tuple[int, int]:
    created_elements: dict[str, object] = {}
    for operation in plan["operations"]:
        if operation["type"] == "create":
            parent_ref = operation["parent"]
            parent = pkg.element(parent_ref) if isinstance(parent_ref, int) else created_elements[parent_ref]
            created_elements[operation["id"]] = add_objects(
                pkg, parent, operation["kind"], 1, operation["title"]
            )[0]
            continue

        owner_ref = operation["owner"]
        owner = pkg.element(owner_ref) if isinstance(owner_ref, int) else created_elements[owner_ref]
        file_elements = [pkg.element(key) for key in operation["files"]]
        assign_files(pkg, owner, file_elements, operation["documents"])
    return plan["created"], plan["unassigned"]


def mass_assign(pkg: SipPackage, folders, target, osp_levels: int, dossier_levels: int,
                create_documents: bool = False, include_top: bool = False) -> tuple[int, int]:
    """Builds positions and dossiers from folders of the package. Returns (created objects, unassigned files)."""
    plan = _mass_assign_plan(pkg, folders, target, osp_levels, dossier_levels,
                             create_documents, include_top, {})
    return _apply_mass_assign_plan(pkg, plan)


def mass_assign_preview(pkg: SipPackage, folders, target, osp_levels: int, dossier_levels: int,
                        create_documents: bool = False, include_top: bool = False,
                        overrides: dict[int, tuple[int, int]] | None = None) -> dict:
    """Returns the proposed hierarchy and file assignment counts without modifying the package."""
    return _mass_assign_plan(pkg, folders, target, osp_levels, dossier_levels,
                             create_documents, include_top, overrides or {})


def mass_assign_with_overrides(pkg: SipPackage, folders, target, osp_levels: int, dossier_levels: int,
                               create_documents: bool = False, include_top: bool = False,
                               overrides: dict[int, tuple[int, int]] | None = None) -> tuple[int, int]:
    """Applies the mass-assignment plan, including per-folder stage overrides."""
    plan = mass_assign_preview(pkg, folders, target, osp_levels, dossier_levels,
                               create_documents, include_top, overrides)
    return _apply_mass_assign_plan(pkg, plan)


# ---------------------------------------------------------------- CSV import (8.1.2)

def _normalized_number(value: str) -> str:
    return re.sub(r"[\s.\-/]", "", value)


def import_csv(pkg: SipPackage, path: str | Path) -> int:
    """Imports positions and dossiers from a '|' separated CSV with a mandatory 'nummer' column."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh, delimiter="|"))
    if not rows or "nummer" not in (rows[0].keys() if rows else []):
        raise StructureError("Die CSV-Datei muss eine Kopfzeile mit der Spalte «nummer» enthalten "
                             "(Trennzeichen «|»).")
    system = pkg.classification_system
    created: list[tuple[str, object]] = []
    for line, row in enumerate(rows, start=2):
        number = (row.get("nummer") or "").strip()
        kind = (row.get("type") or "ordnungssystemposition").strip().lower() or "ordnungssystemposition"
        if kind not in ("ordnungssystemposition", "dossier"):
            raise StructureError(f"Zeile {line}: ungültiger Typ «{kind}» (erlaubt: ordnungssystemposition, dossier).")
        if not number:
            raise StructureError(f"Zeile {line}: die Spalte «nummer» ist leer.")
        key = _normalized_number(number)
        allowed = CONTAINERS["ordnungssystemposition" if kind == "ordnungssystemposition" else "dossier"]
        parent = system
        best = -1
        for other_key, el in created:
            if key.startswith(other_key) and len(other_key) < len(key) and len(other_key) > best \
                    and pkg.kind(el) in allowed:
                parent, best = el, len(other_key)
        if kind == "dossier" and parent is system:
            raise StructureError(f"Zeile {line}: für das Dossier «{number}» wurde keine übergeordnete Position gefunden.")
        el = add_objects(pkg, parent, kind, 1, (row.get("titel") or "").strip() or None)[0]
        pkg.set_text(el, "nummer" if kind == "ordnungssystemposition" else "aktenzeichen", number, required=True)
        text_tags = {d.tag for d in schema.field_defs(pkg.kind(el)) if d.type in (schema.TEXT, schema.MULTILINE)}
        for column, value in row.items():
            if column in text_tags and column not in ("nummer", "aktenzeichen") and value and value.strip():
                pkg.set_text(el, column, value)
        created.append((key, el))
    return len(created)


# ---------------------------------------------------------------- mass edit (9.2)

MASS_EDIT_KINDS = ("ordnungssystemposition", "dossier", "dokument", "mappe", "datei")


def _objects_below(pkg: SipPackage, el, kind: str) -> list:
    if kind == "datei":
        refs = {(r.text or "").strip() for r in el.iter(pkg.q("dateiRef"))}
        return [f for f in (pkg.file_by_id(i) for i in refs) if f is not None]
    found = [e for e in el.iter(pkg.q(kind))]
    return found


def mass_edit_kinds(pkg: SipPackage, el) -> list[str]:
    return [k for k in MASS_EDIT_KINDS if _objects_below(pkg, el, k)]


def mass_edit_fields(kind: str) -> list[dict]:
    return [{"tag": d.tag, "label": d.label, "type": d.type} for d in schema.field_defs(kind)
            if d.type in (schema.TEXT, schema.MULTILINE, schema.TIME_SPAN) and not d.required]


def mass_edit(pkg: SipPackage, el, kind: str, tag: str, value: str, end: str = "") -> int:
    """Sets (or with an empty value deletes) a field on all objects of a kind at or below el."""
    definition = next((d for d in schema.field_defs(kind) if d.tag == tag), None)
    if definition is None:
        raise StructureError("Dieses Metadatum kann nicht mehrfach editiert werden.")
    targets = _objects_below(pkg, el, kind)
    for target in targets:
        if definition.type == schema.TIME_SPAN:
            pkg.set_time_span(target, tag, value, end)
        else:
            pkg.set_text(target, tag, value)
    return len(targets)
