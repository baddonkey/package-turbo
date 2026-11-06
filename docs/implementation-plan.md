# Independent Package Turbo: Implementation Plan

Approved scope: an independent, offline Python/PySide6/QML desktop workspace for
eCH-0160 SIPs. Keep existing useful workflows and shortcuts; do not rewrite as a
web application. No commits, pushes or history rewrites without explicit approval.

## First Milestone

Implemented on `feature/independent-ech0160-audit-ux`:

- Independent product wording and Help routed exclusively to the Package Turbo guide.
- No original-application discrepancy hints, comparison wording, dark-red callouts
  or comparison legend in the guide. Real limitations and safety warnings remain.
- Separate official eCH-0160 schema assets for 1.0, 1.1 and 1.3, retaining 1.2.
- Version selection for GEVER/FILES creation across 1.0-1.3; default 1.3.
- Save/reopen preserves the selected version. Unknown versions are read-only.
- Schema-derived contextual types, child sequence and creation permissions for Mappen,
  including v1.3 recursion and rejection of v1.3-only structures in v1.2 packages.
- Missing standard-schema repair selects the declared version, rather than always 1.2.
- Unsupported checksum algorithms are reported explicitly, never silently treated as MD5.
- A Qt-independent append-only SQLite audit foundation, canonical JSON/SHA-256 chaining,
  stable package/event IDs, UTC timestamps, transaction grouping, honest outcomes and checkpoints.
- Schema-validated PREMIS 3.0, METS 2 and METS 1.12.1 companion serializers.
- Full and explicitly labelled redacted exports; no undocumented files inside the SIP.
- Native Qt smoke coverage for schema selection and nonblank readable rendering;
  corrected location-row alignment and duplicate Cancel buttons in package creation.

The existing Changes table is temporary and is still cleared on Save. The separate
metadata history and save transaction integration are described in the next milestone.

The original test baseline was 59 passing tests. The first milestone passes 104 tests,
including 23 audit/export tests and a native offscreen Qt screenshot/interaction check.
An isolated wheel build succeeds; installed-resource checks are part of the milestone
verification. These are development checks, not production certification.

## Second Milestone: Audited Metadata Commits

Implemented:

- Atomic event batches: event rows and journal head updates roll back together on failure.
- A metadata-only workspace outside the SIP at `<SIP-name>.package-turbo`, with an
  OS-level workspace lock, per-session baseline, durable prepared XML snapshots and
  an atomic replacement followed by transactional audit completion.
- External changes and another session's commits invalidate stale in-memory work.
- Failed preparation never replaces XML. Interrupted replacement/completion retains
  its recovery intent. Recovery compares the actual file against before/after hashes,
  completes a known commit exactly once or records failure, and refuses ambiguous files.
- Confirmed audit operator required before application mutation. Individual editor
  changes retain their operator, object XML ID/path and old/new values when saved.
- Structural/note operations retain summary events; commit records additionally describe
  actual XML locator/value differences and before/after metadata SHA-256 hashes.
- Explicit discard records an outcome without replacing XML. Failure to record discard
  or finish a save prevents the normal close continuation.
- Persistent Metadata History UI, event/transaction details, operator Preferences and
  explicit recovery. Read-only history browsing does not create or update the journal.
- Mutations are blocked while validation is running, protecting the shared XML tree.
- Native Qt smoke coverage for save/history display and operator Preferences, in addition
  to failure-injection and concurrent-session transaction tests.
- Recovery snapshots, edit payloads and operator/version values are bound to the immutable
  preparation event; stored baselines must match completed preservation history.

Verification: 128 tests pass, including 24 journal/export tests, 16 metadata workspace
tests and native Qt history/operator rendering. The built wheel is also checked using
isolated imports so source-checkout resources cannot conceal packaging omissions.

Still pending: filesystem staging/rollback and per-file events/fixity, creation and
preservation-operation capture, XML-entity UUID mapping, package undo/redo, persisted
draft recovery before Save, full history filtering/export UI, completed language
catalogues and full standards/receiver-profile coverage. Initial package creation is
not yet an audit event. Do not claim every package operation is fully audited.

The filesystem transaction limitations from this milestone are addressed below. A crash
before Save can still lose a metadata-only draft that has not joined a recorded file draft.

## Third Milestone: Staged Package Files

Implemented:

- Application file commands operate through `FileWorkspace` on a sibling staging copy,
  including imports, replacements, renames, deletions, normalisation and file fix-ups.
- Save commits one recorded XML/files snapshot; Discard removes the working copy without
  changing the original SIP. Validation and file opening use staged paths while editing.
- Full file/directory SHA-256 manifests and per-path before/after file events. Draft and
  commit intents are bound to immutable journal records, including operator/version.
- A per-operation checkpoint restores staged files and XML on failure. Publication failure
  restores the last recorded staged XML so pending in-memory edits can be retried.
- A prepared directory swap preserves the original in the companion and supports exactly-once
  success/failure recovery, including interruption between the two renames. This is a recoverable
  multi-file transaction, not a claim that two filesystem renames are jointly atomic.
- Draft mutations are frozen while a package commit is prepared. External modifications,
  tampered drafts, and changes during copying/swap are refused; conflicting originals are retained.
- Recorded staged drafts can be restored after restart; their pending operations appear in Changes.
- Read-only opening does not restore, discard or commit drafts. Writable recovery requires an operator.
- Reject symlinks/junctions/special package files and recursive imports from the SIP or its companion.
- Default 32 GiB companion limit, configurable from 1-1024 GiB in Preferences; checks include
  staging/checkpoint copies and retained originals. Check available space before copying.
- Keep verified earlier rollback packages across repeated saves; never silently prune them.
- Block ZIP/XML exports of dirty work and direct primitive saves of a staged package.
- Native Qt smoke coverage includes staged change visibility, storage-limit Preferences and Discard.
- Flush staged file data before commit preparation and sync directory updates where supported;
  Windows flushes use non-truncating writable handles while preserving read-only file mode.
- Temporary checkpoint/staging cleanup handles Windows read-only flags without changing source
  or retained backup modes.
- Unique rename intermediates preserve unrelated files and restore the source name on failure.

Verification: 147 tests pass, including 15 staging/recovery tests, 16 metadata workspace tests,
24 journal/export tests and native Qt checks. The wheel builds and its isolated backend workflow
verifies staged imports, combined commit, retained original fixity, safe discard and PREMIS validity.

This implementation intentionally copies/hashes full packages synchronously. Incremental staging,
background progress/cancellation, full package undo/redo, retention/pruning policy, metadata-only
draft autosave, per-object PREMIS identity modelling, initial creation/validation/export events and
complete history export/filter UI remain pending. Retained copies are not a user-facing Undo feature.

These historical limitations are superseded for session Undo/Redo and metadata draft persistence
by the fourth milestone below. Background/cancellable copying and retention controls remain pending.

Direct low-level `ph_backend.files` calls without an application workspace retain their primitive
filesystem semantics. Scripts must explicitly use the workspace APIs for staged/audited operations.
Do not delete or modify the companion to bypass a conflict. Never claim exhaustive standards
compliance, legal clearance or production readiness from these development checks.

## Fourth Milestone: Session Package Undo/Redo

Implemented:

- Verified before/after XML and complete file snapshots for successful application metadata,
  structure, note and file operations. Mutations and snapshot capture run inside the staged
  operation checkpoint; failed actions or after-snapshot failures restore the previous work.
- Package Undo/Redo stages snapshot restoration without modifying the original SIP until Save.
  It works after Save while the same package/session remains open, and restores deleted file
  bytes and their XML references together.
- Link compensating `undo`/`redo` events to stable operation identifiers. Original events are
  never removed; a new branch drops redo snapshots, not preservation history.
- Persist operation identifiers, UTC operation time and actual XML/file deltas atomically
  with the draft before subsequent detailed UI field signals. Metadata drafts now use the
  same recorded staging path and can be resumed after restart.
- Native menu shortcuts and explicit package toolbar buttons. Focused text-field Undo retains
  priority for unsubmitted typing. XML-ID selection is restored when that object still exists.
- Default 20-step session horizon; oldest snapshots expire within that bound. Full-copy snapshots
  also count against the companion storage limit. Storage/copy failures refuse or roll back edits.
- Read-only/busy state disables reversals. Tampered snapshots, external changes and prepared
  commits cannot be reversed blindly. No-op operations create neither undo entries nor hidden drafts.
- An explicit Clear Package History command removes only this session's undo/redo snapshots.
  Discard, package switch and normal shutdown clear them while keeping the journal and required
  draft/rollback data. Undo state is intentionally not reconstructed after a restart.
- Native button/shortcut tests, focused-text Ctrl+Z coverage, deletion/reference/structure/note
  reversals, after-Save reversal, branching, lifecycle cleanup and fault/tamper checks.
- Retain the prior working checkpoint if rollback is blocked; never delete the only recovery
  copy on that failure path. Restored XML invalidates old full-validation cache results.

Verification: 170 tests pass, including 5 standalone undo tests and native Qt shortcut/rendering
checks. Isolated-wheel verification exercises staged reversals and compensating PREMIS events.

At this milestone snapshot copying remained synchronous and potentially expensive. Background/cancellation and
incremental storage are next; history filters/export UI, configurable retention/pruning, complete
PREMIS object identities, creation/validation/export capture, translations, legal review and full
standards coverage remain pending. Crashed processes can leave unreferenced session snapshot
directories; automatic orphan cleanup is not yet implemented. Do not remove the whole companion
or retained originals to bypass its storage limit.

## Fifth Milestone: Responsive Cooperative IO

Implemented:

- Qt-independent task controls, thread-local processing contexts and chunked file copy/hash
  helpers. Report first-chunk progress immediately, then throttle subsequent UI updates.
- `QtTaskExecutor` runs isolated path/byte functions on a worker while a local Qt event loop
  keeps rendering, timers and Cancel active. Existing synchronous API results are preserved;
  this is not a fire-and-forget API conversion.
- Workspace, undo snapshots, imported/replaced files, quota scans, metadata bytes/comparisons
  and durability flushes use the worker path. Workers do not mutate GUI models or live XML.
- Block reentrant edits, Save, Undo/Redo, package creation/switch/close and conflicting recovery
  while worker IO is active. Read and verify new metadata before publishing package state;
  canceled reads leave the current package intact.
- Cooperative cancellation at chunk/phase boundaries before commit. The cancellation slot
  requests interruption without waiting. Rollback/temporary cleanup and atomic publication
  run in critical sections; cancellation cannot interrupt protected commit/recovery completion.
- Native progress dialog with current phase, byte counts, indeterminate phases and accurate
  Cancel enablement. Window closure during work requests cancellation rather than abandoning
  a worker or a protected transaction.
- Full validation owns a separate parsed XML snapshot. Map issue locators to GUI keys only
  after completion; canceled results are never published as complete validation. Checksum
  hashing supports cancellation and byte reporting within a file, not just between rules.
- Explicit canceled-result state survives QThread completion; do not rely on the thread's
  transient interruption flag after it has stopped.
- Tests cover GUI heartbeat during blocked worker IO, nonblocking Cancel, canceled-copy source
  fixity, reentrant guards, protected commit rejection, stale package transitions, isolated
  validation/key mapping, a repeated-chunk 16 MiB import and progress values above 2 GiB.
- Native screenshots/tests cover cancelable copy progress and disabled Cancel during commit.

Verification: 190 tests pass. The isolated wheel is checked for worker-backed staging,
source preservation under cancellation, protected Save, Undo/Redo and valid PREMIS output.

Cancellation is cooperative, not a forced thread termination. It can wait for an in-flight
filesystem call to return and does not discard previously accepted drafts. GUI-owned XML
mutation/serialization, model rebuilds, schema presentation and journal bookkeeping still
execute on the GUI thread; not every possible large-package handler is now nonblocking.
Full copies/hashes remain conservative and expensive. Incremental storage, retention controls,
performance budgets on real large fixtures, history filters/export, comprehensive event/identity
modelling, translation coverage, rights review and complete standards certification remain pending.

The undo-storage and explicit retention portions are implemented in the sixth milestone;
mutable staging/checkpoint copies and broader performance qualification remain conservative.

## Sixth Milestone: Private Object Reuse And Safe Retention

Implemented:

- Undo snapshots store file bytes once per SHA-256 inside a private per-session object store.
  Verify existing objects before reuse; link only immutable store objects to private snapshots.
  Never hardlink source SIP files or mutable staging files. Restoring a snapshot uses independent
  copies and restores original file modes before subsequent editing.
- Logical snapshot views remain complete XML/files trees, while unchanged content is not copied
  again for metadata-only snapshots. Reference release preserves active objects; unreferenced
  verified objects can be removed. Unknown store data is not silently pruned.
- Workspace accounting counts shared inodes once and conservatively counts distinct paths on
  filesystems without usable inode IDs. This is file-byte accounting, not an exact filesystem
  block/metadata/sparse-file reclamation prediction.
- Register older rollback copies in immutable preservation history as they are archived.
- Retention defaults: keep three total rollback generations including the protected latest copy;
  minimum archived age seven days. Preferences allow 1-100 copies and 0-3650 days.
- A native Storage Cleanup dialog previews eligible directory names, archived UTC time, bytes
  and protected-directory count. No automatic deletion; explicit confirmation is required.
- Only registered direct-child `rollback-<UUID>` directories with matching fixity are eligible.
  Protect the current SIP, latest `rollback-package`, active drafts/undo/checkpoints, unknown
  directories and shared/hardlinked candidates. Unregistered backups from older application
  versions remain protected; they are not silently migrated into deletion eligibility.
- Cleanup requires the exact issued preview, unchanged journal head and current policy; verify
  targets again before deleting. Prepared metadata/package commits block cleanup entirely.
- Audit preparation and outcome, including completed targets on partial failure. Cleanup never
  rewrites earlier events. Once deletion begins it is protected from cooperative interruption.
- Tests verify source inode separation, storage growth for metadata-only captures, no unchanged
  content copy, shared-reference cleanup, stale/changed preview refusal, active Undo/Redo and
  draft preservation, partial failure outcomes and real native preview/Apply/Preferences flows.

Verification: 204 tests pass. Isolated-wheel checks exercise object reuse, source separation,
retention preview/apply, preserved Undo/Redo and PREMIS validation. Native preview screenshots
are checked for usable sizing and readable target/byte information.

This is incremental undo storage, not a fully incremental package filesystem. Mutable staging,
per-operation checkpoints, retained originals and materialised reversals still use independent
full copies; hashes continue to verify full contents. Hardlink-capable companion storage is
required for private-object sharing. Automatic crashed-session orphan cleanup, retention
migration for unregistered copies, block-level space measurement, broader performance work,
complete standards/event/identity/export/translation coverage and rights review remain pending.

## Seventh Milestone: Schema-Aware Metadata Workflows

Implemented:

- Ordered repeated simple-text fields, including document authors and repeated process/activity
  references or remarks. List editing supports add, reorder and removal, multiline values and
  schema cardinality; source-row identity carries existing XML elements and vendor attributes.
- Scalar editor and scalar bulk mutation refuse repeated fields rather than overwrite a list.
- Structured GEVER Vorgang/Aktivitaet creation, editing, movement and deletion where declared
  in 1.1-1.3 schemas. Do not invent IDs on types that do not declare them. FILES schemas do not
  offer these GEVER-only objects. Version 1.0 process text remains visible/read-only and is not
  silently converted into structured children.
- Parse inherited and simple-content attribute declarations. Expose dateiRef `version`,
  `repraesentation`, `information` and `reihung` only in 1.2/1.3, where they are declared.
  Preserve assignment text/order and other attributes; unknown attributes remain read-only.
- Native repeated-value and per-reference forms, context-sensitive creation menu items and
  standard staging/audit/Undo/Redo integration for these edits.
- Defer QML editing mutations past their signal handlers so model rebuilds do not delete the
  emitting delegate while nested IO processing runs. Package-generation guards discard stale
  callbacks; Save/Close flush focus-finished edits before proceeding. Native tests verify author,
  reference and activity inputs plus Save while an activity field is still focused.
- Keep expanded optional fields open across metadata refreshes for the same object, so editing
  a repeated author or reference does not hide the list immediately afterward.

### Verified Slice

| Capability | eCH 1.0 | eCH 1.1 | eCH 1.2 | eCH 1.3 |
| --- | --- | --- | --- | --- |
| GEVER/FILES create and schema-valid reopen | Tested | Tested | Tested | Tested |
| Repeated document authors, ordered roundtrip | Tested | Tested | Tested | Tested |
| Structured GEVER process/activity editing | Not declared; preserve text | Tested | Tested | Tested |
| Structured process/activity in FILES | Rejected | Rejected | Rejected | Rejected |
| dateiRef optional attributes | Rejected | Rejected | Tested | Tested |
| Repeated activity remarks/references | Not applicable | Tested | Tested | Tested |

### XSD Declaration Inventory

The reproducible [XSD inventory](ech0160-xsd-inventory.csv) contains 2,949 declaration rows
generated from the four bundled schema sets. Regenerate it with `python tools/schema_inventory.py`.
It records eCH release/schemaVersion, shared/GEVER/FILES profile, complex type, effective
elements and inherited attributes, min/max occurrences, simple-type facets, a likely code
surface, linked test evidence where available, and review status.

Rows with exact linked tests say **tested workflow slice; broader requirement review remains**;
catalogued editor fields and conditional sample/schema tests are deliberately not marked tested.
The CSV is an XSD declaration inventory and triage aid, not a normative eCH requirement matrix:
it does not encode the PDF's prose rules, data-dictionary semantics, archive-specific profiles,
full per-value negative cases, or guarantee that conditional sample fixtures were present during
a particular CI run. Empty/unknown coverage is a request for review, not an unsupported-pass claim.

Verification: 262 tests pass. Tests include all eight version/delivery combinations for authors
and reference attributes, structured process roundtrips, legacy and FILES restrictions, list
identity preservation, native field editing, focused Save and audited Undo/Redo.
The deterministic XSD inventory generator compiles every bundled schema set and is tested for
the 1.0-1.3 declarations, repeated authors, dateiRef attribute release differences and v1.3
recursive Mappen.

### Normative Requirement And Data-Dictionary Matrices

As checked on 2026-11-05, the [official eCH-0160 page](https://www.ech.ch/de/ech/ech-0160/1.3.0)
lists version 1.3.0 as approved. Its specification says versions 1.0, 1.1 and 1.2.0 remain
valid. The corresponding [version 1.0](https://www.ech.ch/de/ech/ech-0160/1.0),
[version 1.1](https://www.ech.ch/de/ech/ech-0160/1.1) and
[version 1.2.0](https://www.ech.ch/de/ech/ech-0160/1.2.0) pages were used for historic ID checks.

The first-pass [normative requirements matrix](ech0160-requirements.csv) lists 60 actual
requirements from the v1.3.0 specification, with clause page, MUST/SHOULD level, profile scope,
short summary, candidate code surface and test-evidence field. The `in_1_*` columns indicate
only whether an identifier occurs in each older PDF: they do not prove that the clause text or
meaning stayed unchanged. The example ID in the specification's notation section is excluded.
Two rows are partially verified: M_4.5-1 has exhaustive synthetic presence coverage plus real SIP
save/reopen cases for required delivery/dossier fields across all eight release/profile combinations
and legacy FILES provenance; M_4.10-1 has a tested dossier-estimation rule. The other 58 remain `not-assessed`;
candidate code paths and sample smoke tests are not clause-conformance evidence.

The [data-dictionary matrix](ech0160-data-dictionary.csv) contains 969 profile-specific rows
generated from the official 1.0, 1.1, 1.2.0 and 1.3.0 workbooks. It records mandatory/optional
relevance, type, whether a value range is specified, repeatability, versioning where declared,
and worksheet/row source coordinates; dictionary definitions, examples and full value lists are
not copied. For v1.3.0 it identifies 38
mandatory GEVER entries and 28 mandatory FILES entries. Every M-level row is included in the
compact packaged [runtime requirement resource](../ph_backend/resources/metadata_requirements.csv)
and checked for required presence/non-empty scalar values according to release and profile. An
exhaustive synthetic test covers all 218 M-level rows across releases and profiles, with a missing
and present case for each field; this verifies rule mapping, not realistic package roundtrips or
all field semantics. Complex value internals remain subject to XSD validation. Matrix statuses
distinguish this presence evidence from pending field-specific semantic/XSD conformance; K-level
rows remain `not-assessed`. The editor also marks dictionary-required fields and conditionally
marks the dossier estimation note when a period endpoint is approximate.
Real-package tests additionally remove, validate, save, reopen, restore and revalidate required
delivery and dossier fields in all eight version/profile combinations, and round-trip the legacy
FILES `systemName` and `systemBeschreibung` fields for versions 1.0 and 1.1.
The local legacy 1.0 FILES fixture omits `systemName` and `systemBeschreibung`, both marked M
by that release's data dictionary; validation now reports these omissions instead of silently
waiving the requirements.
Regenerate from locally downloaded official workbooks with:

```powershell
python tools/data_dictionary_matrix.py `
  --source 1.0=path\to\v1.0-data-dictionary.xls `
  --source 1.1=path\to\v1.1-data-dictionary.xlsx `
  --source 1.2.0=path\to\v1.2-data-dictionary.xlsx `
  --source 1.3.0=path\to\v1.3-data-dictionary.xlsx
```

The [KOST test-package page](https://kost-ceco.ch/cms/ech-0160-archivische-ablieferungsschnittstelle.html)
lists a 2026-04-21 eCH-0160 v1.3 FILES package. The package was checked against the bundled v1.3
XSD and passed the application's sample smoke workflow. It remains in the ignored local `samples/`
directory; it is not redistributed by this repository. Local test runs skip the fixture when it is
absent. The Windows [CI workflow](../.github/workflows/tests.yml) downloads it transiently from
the official KOST page, verifies SHA-256
`dc4474a3cfe654f7e459cd594cd43d91f7e563b98c39e809417e6778ba023c65`, and sets
`PACKAGE_TURBO_REQUIRE_KOST_FIXTURE=1` so absence is fatal. The ZIP is not committed or attached
as a workflow artifact. The maintainer confirms this project use is non-commercial; review terms
again before redistribution or any commercial use.

Validation now permits omission of optional delivery-number/protection-period fields and enforces
dictionary-mandatory metadata across versions. It also checks that every dateiRef ID resolves to
a content file and treats the v1.3 IDREFS value as a list; tests cover multi-ID references and a
dangling reference. M_4.10-1 tests require an explanation for estimated dossier periods. Existing
positive/negative tests cover checksum and table-of-contents/file-system agreement.

This remains a first-pass traceability baseline, not full standards conformance. Required next
coverage includes clause-by-clause review of all four PDFs and data dictionaries, realistic
mandatory-field package fixtures and remaining conditional constraints, arbitrary repeated/complex
metadata, element attributes such as reihung,
file properties/eigenschaft, archival operations, attachments, complete facet/choice UI validation,
schema trust/resolution hardening, receiver profiles and explicit migration. Whole-document lxml
XMLSchema validation remains authoritative; the current controls do not claim every invalid value
is rejected before staging. Full eCH compliance and legal clearance remain release gates, as are
complete language catalogues and native artifact qualification.

## Remaining Milestones

### 1. Provenance And Rights

- Record source/history, assets, schemas, samples and third-party redistribution terms.
- The author reports that no BAR source code was copied; this is an authorship statement,
  not legal clearance. No project licence was present at the initial review.
- The reproduced manual, PDFs and extracted images are ignored local files. Keep them
  out of deliverables; do not erase local research or rewrite git history automatically.
- Review icons and guide text/image provenance; rewrite product documentation independently
  where necessary. Removing comparison hints alone does not establish original authorship.
- Select a project licence after ownership review. Retain required attribution and obtain
  qualified advice for uncertain materials. No technical change guarantees legal immunity.
- Preserve eCH-mandated namespace identifiers and terminology; do not rename XML namespaces
  to remove `bar.admin.ch` or imply that Package Turbo is endorsed by BAR.

### 2. Complete Standards Coverage

- Build a normative requirement-to-code/test matrix from the official specifications,
  data dictionaries and schemas for 1.0-1.3, including relevant legacy FILES-DOC forms.
- Complete clause-level assessment and mandatory-field test mapping using the first-pass
  matrices documented above; compare requirement text, not just identifier presence.
- Complete attributes, repeated/complex values, dateiRef attributes, file properties,
  archival operations, attachments and editable Vorgang/Aktivitaet where the schema permits.
- Model choices, cardinality, attributes and facets faithfully. Use lxml.XMLSchema for
  validation; do not hand-write an XSD validation engine.
- Preserve unknown nodes/attributes, identifiers and original checksum algorithms.
- Keep secure XML parsing and local schema resolution; reject escaping/network imports.
- Detect missing/mismatched/custom schemas explicitly; never silently migrate on Save.
- Separate eCH rules from receiving-archive policies, including size/path/format limits.
- Migrate only an explicit copy, preview changes/losses, validate the result and audit its
  derivation. Reject unrepresentable downgrades rather than silently dropping information.
- Keep the v1.3 FILES conformance fixture fail-closed in CI; add schema-derived GEVER/feature-edge
  fixtures under reviewed redistribution terms.

### 3. Recoverable Transactions And Audit Integration

- Route editor, structure, file, note, repair, factory and migration commands through a
  Qt-independent workspace service. Capture structured before/after deltas before mutation.
- Stage XML and filesystem changes outside the SIP. Use durable intent, source revision/hash
  checks, writer locking and reversible replacements. Do not claim multi-file atomicity.
- Couple commit outcomes to journal records; an audit failure must block an unaudited commit.
  Record failed/discarded/partial operations truthfully and recover after process interruption.
- Track individual accepted semantic changes, not keystrokes. Group batch operations by
  transaction. Undo/redo produces compensating events and never erases original events.
- Persist object identities, deletion tombstones and copy/migration derivation. Do not use
  session-local integer keys as preservation IDs or change source XML just to add audit IDs.
- Detect missing/mismatched companions and discovered external changes; do not invent earlier
  history or attribute externally performed changes to an unverified operator.
- Audit SIP changes and preservation operations only. Keep clicks/searches/settings out of
  PREMIS; source-code history belongs in git and release notes.
- Export a strict SIP plus an external companion. Bind exports to a consistent snapshot,
  file fixity and checkpoint, without recursive self-hashing or export-event loops.

### 4. UX, Performance And Languages

- Context-focused editing and clear standard/profile/dirty/recovery status; preserve useful
  navigation, search, notes, sampling, reports and multiselection workflows.
- Audit timeline filters, per-object before/after details and deleted-object context.
- Package-level undo/redo, preview for batch edits/imports/conflicts/deletion/normalisation,
  and precise Save/Discard behaviour for staged work.
- Field-level schema errors with direct navigation and rule/profile explanations. Distinguish
  not-run, stale, running, cancelled, failed and passed validation; colour alone is insufficient.
- Cancellable hashing/import/validation/export on immutable snapshots. Reject stale results;
  never block the GUI while waiting for worker cancellation or share mutable XML unsafely.
- Compact icon controls, clear focus/accessibility labels, keyboard-only workflows and
  high-DPI/narrow-window layouts. Retain PySide6/QML and familiar native interactions.
- Complete German/French field labels, help, diagnostics, reports and event display.
  Stored event semantics must remain language-neutral.

### 5. Identification And Native Releases

- Use a maintained signature-identification tool/database, preferably a Siegfried/PRONOM
  adapter, after redistribution review. Run offline, identify tool/database versions and
  report unknown/ambiguous/extension-only evidence honestly.
- Separate identification from KaD/receiver suitability. Identifying a format does not
  prove PDF/A or other specialist conformance. Conversion is not in this milestone.
- Native Windows/macOS/Linux artifacts, native CI runners and installed-app smoke tests.
  Ship supported schemas, translations, original guide and lawful assets; exclude research
  manuals, samples and local journals. No installed Python required for native artifacts.
- Record dependency notices/SBOM and artifact checksums. Signing and publishing need separate
  approval and infrastructure; do not advertise unsigned/unverified builds as certified.

## Audit Profile And Privacy

`ph_backend.audit.AuditJournal` currently records package-level representation events.
Per-XML-entity and per-file PREMIS object modelling remains pending. Application metadata
commits now use `ph_backend.workspace.MetadataWorkspace`; the standalone journal API
does not itself observe changes. A successful preparation event means its durable intent
was written, not that XML replacement or the overall commit has succeeded.

Canonical payloads use RFC 8785. Each SHA-256 digest covers the previous digest bytes
followed by the canonical payload. The stored head checks truncation; an independently
retained `AuditCheckpoint` detects rollback beyond that trusted checkpoint. A privileged
attacker can rewrite both history and head: this is not a signature or authorship proof.

Keep complete old/new metadata values locally, hashes rather than file contents in events,
and restrict access to the companion. The operator ID remains visible in redacted exports;
redaction currently omits event detail rather than anonymising operators. Export labels
must make this distinction clear. Never rewrite the authoritative journal to redact it.

Read-only journal access never creates or appends records. Backup/blob retention and storage
limits belong in the workspace layer; deleting rollback blobs must not delete event history.
Digital signatures, trusted external timestamps, cloud services and telemetry are deferred.

The METS serializers describe a strict SIP ZIP plus a relative PREMIS XML reference under
the local profile `urn:package-turbo:mets-companion:1`. The caller must supply the actual SIP
SHA-256 and write the corresponding PREMIS snapshot; these APIs do not assemble a delivery
bundle or provide a receiving-archive certification.

## Sources And Distribution Review

Official unmodified XML schema assets imported for implementation and interoperability:

| Asset | Source | Download SHA-256 |
| --- | --- | --- |
| eCH 1.0 archive | [eCH attachment](https://www.ech.ch/sites/default/files/imce/eCH-Dossier/0151-0180/eCH-0160/1.0/Beilagen/eCH-0160.xsd.zip) | `9c749abfad1d70235b9c9d37195b6ca0c816d314ea7dcc88d9fd63b8a0e36bfb` |
| eCH 1.1 archive | [eCH attachment](https://www.ech.ch/sites/default/files/imce/eCH-Dossier/0151-0180/eCH-0160/1.1/Beilagen/eCH-0160-1.1.xsd.zip) | `9ca44ef6376ade92f7ad5a6e88f5efab11acef88747336671cf28c1f71b1cd71` |
| eCH 1.3 archive | [eCH attachment](https://www.ech.ch/sites/default/files/imce/eCH-Dossier/0151-0180/eCH-0160/1.3.0/Beilagen/eCH-0160-1.3.0.xsd.zip) | `0231822f081cb61f125c6f3fe6968f331d6f6618ee5c7a19a933a8f1173bdff9` |
| PREMIS 3.0 XSD | [LOC schema](https://www.loc.gov/standards/premis/v3/premis-v3-0.xsd) | `03b8a77a20b32b882ad799e12262671d07ad18210c60233f4e613a1289491cba` |
| METS 2 XSD | [LOC schema](https://www.loc.gov/standards/mets/mets2.xsd) | `1ac4af428d9ab2099b19306344d56916a3dcd7bfd39d7d2276c1fbde24205c96` |
| METS 1.12.1 XSD | [LOC schema](https://www.loc.gov/standards/mets/version1121/mets.xsd) | `8f289c776e490e4763dab0e4b958c74993e5f271718cf244f24d00bb5af62a1f` |
| XLink XSD | [LOC dependency](https://www.loc.gov/standards/mets/xlink.xsd) | `f1f5bb6003165cdd8f6c1fcc32f8fd1f965e1681010f3b9806d9460bcffa8a3c` |

The existing 1.2 bundle predates this work; compare it with the official release and record
its provenance before distribution. The LOC METS documentation/schema pages state CC0;
verify PREMIS, eCH, dependencies, icons and sample terms separately. Download hashes are
integrity evidence, not licence grants or legal clearance.

## Required Release Checks

- Required version/type/feature fixture matrix and unchanged-data roundtrips, including
  checksum/reference integrity, unknown metadata preservation and read-only no writes.
- Every mutation path mapped to events; concurrency, disk-full, denied writes, cancellation,
  process termination and restart tested at each transaction failure window.
- Offline PREMIS/METS schema validation, resolved identifiers/file references, fixity,
  redaction labels and trusted-checkpoint checks.
- Native Qt workflow/screenshots at representative window sizes and 100/150/200% scaling,
  keyboard/screen-reader checks, full German/French coverage and bounded-memory performance.
- Installed Windows/macOS/Linux artifact tests and recorded rights/redistribution clearance.

Use the repository virtual environment to run `python -m pytest`. Narrow tests follow each
edit; the complete suite and built-artifact checks gate release. Passing these foundation
tests does not yet establish exhaustive standards compliance or production readiness.