# package-turbo

<p align="center">
  <img src="docs/user-guide/img/02-ueberblick.png" alt="Package Turbo showing an open SIP package" width="100%">
</p>

An independent desktop workspace for creating, editing and validating eCH-0160
Submission Information Packages (SIPs), built with Python, PySide6 and QML.
Package Turbo is experimental and is not yet intended for production use.

## Features

- Open and create eCH-0160 SIPs (versions 1.0, 1.1, 1.2, and 1.3), with v1.3 as the creation default.
- Preserve the selected schema version when editing and saving; open unknown versions read-only.
- Edit ordered repeated text values and schema-declared file-reference attributes.
- Create and edit structured GEVER processes/activities for eCH 1.1-1.3 while preserving legacy 1.0 text.
- Browse package structure, edit metadata, and open content files.
- Validate metadata against the package's XML schemas and assist with corrections.
- Search metadata, add notes, and create samples.
- View reports and statistics, and export tables to Excel.

## Run

Requires Python 3.11 or newer.

```sh
pip install .
package-turbo
```

See the [user guide](docs/user-guide/Benutzerdokumentation.md) for details.

## Development Roadmap

The [implementation plan](docs/implementation-plan.md) tracks independent product
development, complete standards coverage, preservation history, safer editing and
native releases. Schema-based creation and validation do not yet mean that every
metadata feature has a complete editor workflow.

The generated [eCH-0160 XSD inventory](docs/ech0160-xsd-inventory.csv) shows declarations,
cardinalities, facets, likely code surfaces and linked tests across bundled releases. It
is an engineering inventory, not proof of complete normative eCH or receiving-archive
compliance.

The preservation foundation in `ph_backend.audit` provides an append-only SQLite
journal, RFC 8785 canonical JSON and SHA-256 chaining, trusted checkpoint checks,
and PREMIS 3.0 / METS 2 / METS 1.12.1 companion serializers. Application metadata
edits now require a confirmed operator and are recorded when committed or explicitly
discarded. The Metadata History view survives Save and reopening, independently of
the temporary Changes view. An external `<SIP-name>.package-turbo` companion holds
the journal and interrupted-save recovery state.

Metadata saves detect external/stale-session changes and use durable preparation,
atomic XML replacement and exactly-once completion/recovery. If a save is interrupted,
use Metadata History's recovery action before resuming edits. Application file commands
now operate on a staged copy: Save commits the combined XML/files snapshot, while Discard
leaves the original SIP untouched. Prepared directory replacements recover against
SHA-256 manifests; verified original copies are retained in the companion.

This conservative implementation copies and hashes complete packages, rejects links and
junctions, and uses a configurable workspace storage limit (32 GiB by default). Large
packages can take time and space. Copying, hashing, snapshot-byte IO and durability flushes
now run through Qt workers with phase/byte progress and cooperative cancellation. XML
mutations and model updates remain on the GUI thread; mutating reentrancy is blocked
while worker events are processed.
Recorded drafts, including metadata edits, can be resumed using the recovery action.
Package Undo/Redo now restores verified XML/files snapshots within the current session,
including reversals after Save (which are staged until saved again). Its default horizon
is 20 operations, subject to the workspace storage limit. Reversals append linked audit
events; clearing undo snapshots does not erase preservation history.

Undo is cleared on Discard, package switch or normal shutdown; it is not reconstructed
after restart. Cancel is accepted before protected commit/recovery phases, not halfway
through an irreversible package swap. It does not discard earlier accepted work.
Validation uses a separate XML snapshot and can be interrupted during checksum hashing.

Undo snapshots now reuse read-only, content-addressed objects inside their private session
store. Hardlinks exist only between those immutable objects and snapshot references, never
to mutable SIP/staging files; restoration makes an independent working copy. Storage quotas
count shared object bytes once. This reduces repeated snapshot storage, not full staging or
rollback-copy costs, and full fixity checks still run.

Storage cleanup is explicit and previewed: configurable copy count/age defaults to three
copies and seven days. Only registered, verified older rollback copies are candidates; the
latest rollback, drafts, undo stores, recovery checkpoints, journal and unknown data stay
protected. Stale/modified previews are rejected and cleanup outcomes are audited.

Efficient incremental staging, automatic orphan cleanup, complete history export UI,
comprehensive operation capture and production qualification remain pending. Keep an
untouched source copy.

## Sample SIP files

Sample SIPs are available from [KOST/CECO](https://kost-ceco.ch/cms/ech-0160-archivische-ablieferungsschnittstelle.html).

## License and Third-Party Notices

Package Turbo's original code is provided under the MIT License; see [LICENSE](LICENSE).
Third-party packages, tools, icons, schemas and sample-material notices are listed in
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md). Their terms remain separate from the
project license.