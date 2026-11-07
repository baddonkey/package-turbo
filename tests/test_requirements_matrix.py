import csv
from pathlib import Path


MATRIX = Path(__file__).resolve().parents[1] / "docs" / "ech0160-requirements.csv"


def test_normative_matrix_tracks_all_release_requirement_ids():
    with MATRIX.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 60
    assert len({row["requirement_id"] for row in rows}) == len(rows)
    assert {row["level"] for row in rows} == {"M", "K"}
    assert {row["assessment"] for row in rows} <= {
        "not-assessed", "partial-presence-verified", "partial-sip-roundtrip-verified",
        "partial-dossier-rule-verified", "partial-limit-verified", "partial-character-set-verified",
        "partial-integrated-files-verified", "partial-checksum-verified", "partial-encryption-detection",
        "partial-xsd-release-verified", "partial-schema-location-verified", "partial-toc-completeness-verified",
        "partial-reference-integrity-verified", "partial-reference-attributes-verified",
        "partial-files-relationships-verified", "partial-files-classification-verified",
        "partial-sip-root-layout-verified", "partial-schema-bundle-verified",
        "partial-primary-data-header-verified", "partial-protection-scope-verified",
        "partial-sip-name-pattern-verified", "partial-normalization-collision-verified",
        "partial-normalization-roundtrip-verified", "partial-original-name-creation-verified",
        "partial-file-folder-charset-verified", "partial-path-length-boundary-verified",
        "partial-gever-relationships-verified", "partial-gever-classification-scheme-verified",
        "partial-size-boundary-warning-verified", "partial-files-content-hierarchy-verified",
        "partial-primary-data-content-location-verified", "partial-metadata-location-xml-verified",
        "partial-unprefixed-arelda-generation-verified", "partial-release-namespace-mismatch-verified",
        "partial-files-entity-type-consistency-verified", "partial-protection-period-roundtrip-verified",
        "partial-files-layout-classification-roundtrip-verified", "partial-droid-extension-mismatch-verified"}
    assert all(row["candidate_code_surface"] and row["test_evidence"] for row in rows)
    assert sum(row["in_1_0"] == "true" for row in rows) == 51
    assert sum(row["in_1_1"] == "true" for row in rows) == 54
    assert sum(row["in_1_2_0"] == "true" for row in rows) == 60
    assert sum(row["in_1_3_0"] == "true" for row in rows) == 60


def test_normative_matrix_distinguishes_profiles_and_known_slices():
    with MATRIX.open(encoding="utf-8", newline="") as stream:
        rows = {row["requirement_id"]: row for row in csv.DictReader(stream)}

    assert rows["M_4.3-1"]["profile_scope"] == "GEVER"
    assert rows["M_4.3-2"]["assessment"] == "partial-gever-relationships-verified"
    assert rows["M_4.8-2"]["assessment"] == "partial-gever-classification-scheme-verified"
    assert rows["M_4.4-1"]["profile_scope"] == "FILES"
    assert rows["M_4.4-1"]["assessment"] == "partial-files-entity-type-consistency-verified"
    assert rows["M_4.4-2"]["assessment"] == "partial-files-relationships-verified"
    assert rows["M_4.4-3"]["assessment"] == "partial-files-classification-verified"
    assert rows["M_4.8-3"]["assessment"] == "partial-files-layout-classification-roundtrip-verified"
    assert rows["P_3.2-2"]["assessment"] == "partial-droid-extension-mismatch-verified"
    assert rows["M_4.12-2"]["in_1_0"] == "false"
    assert rows["M_4.12-2"]["in_1_3_0"] == "true"
    assert "release gating and XSD-valid save/reopen" in rows["M_4.12-2"]["test_evidence"]
    assert rows["M_4.5-1"]["assessment"] == "partial-sip-roundtrip-verified"
    assert rows["M_4.1-1"]["assessment"] == "partial-metadata-location-xml-verified"
    assert rows["M_4.1-2"]["assessment"] == "partial-release-namespace-mismatch-verified"
    assert rows["M_4.1-3"]["assessment"] == "partial-unprefixed-arelda-generation-verified"
    assert rows["M_4.6-1"]["assessment"] == "partial-xsd-release-verified"
    assert rows["M_4.6-2"]["assessment"] == "partial-schema-location-verified"
    assert rows["M_4.7-1"]["assessment"] == "partial-toc-completeness-verified"
    assert rows["M_4.10-1"]["assessment"] == "partial-dossier-rule-verified"
    assert rows["M_4.11-1"]["assessment"] == "partial-checksum-verified"
    assert rows["M_4.9-2"]["assessment"] == "partial-protection-scope-verified"
    assert rows["M_4.9-1"]["assessment"] == "partial-protection-period-roundtrip-verified"
    assert rows["M_4.12-1"]["assessment"] == "partial-reference-integrity-verified"
    assert rows["M_4.12-2"]["assessment"] == "partial-reference-attributes-verified"
    assert rows["S_5.2-1"]["assessment"] == "partial-limit-verified"
    assert rows["S_5.2-2"]["assessment"] == "partial-limit-verified"
    assert rows["S_5.1-1"]["assessment"] == "partial-size-boundary-warning-verified"
    assert rows["S_5.7-1"]["assessment"] == "partial-files-content-hierarchy-verified"
    assert rows["S_5.4-6"]["assessment"] == "partial-primary-data-content-location-verified"
    assert rows["S_5.5-1"]["assessment"] == "partial-path-length-boundary-verified"
    assert rows["S_5.3-2"]["assessment"] == "partial-character-set-verified"
    assert rows["S_5.3-1"]["assessment"] == "partial-file-folder-charset-verified"
    assert rows["S_5.3-4"]["assessment"] == "partial-normalization-collision-verified"
    assert rows["S_5.3-3"]["assessment"] == "partial-normalization-roundtrip-verified"
    assert rows["S_5.3-5"]["assessment"] == "partial-original-name-creation-verified"
    assert rows["S_5.8-1"]["assessment"] == "partial-integrated-files-verified"
    assert rows["S_5.8-2"]["assessment"] == "partial-integrated-files-verified"
    assert rows["S_5.8-3"]["assessment"] == "partial-integrated-files-verified"
    assert rows["S_5.4-3"]["assessment"] == "partial-sip-root-layout-verified"
    assert rows["S_5.4-5"]["assessment"] == "partial-schema-bundle-verified"
    assert rows["S_5.4-4"]["assessment"] == "partial-primary-data-header-verified"
    assert rows["S_5.4-2"]["assessment"] == "partial-sip-name-pattern-verified"
    assert rows["A_2.6-1"]["assessment"] == "partial-encryption-detection"
    assert rows["A_2.6-2"]["assessment"] == "partial-encryption-detection"