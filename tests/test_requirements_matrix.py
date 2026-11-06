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
        "partial-dossier-rule-verified"}
    assert all(row["candidate_code_surface"] and row["test_evidence"] for row in rows)
    assert sum(row["in_1_0"] == "true" for row in rows) == 51
    assert sum(row["in_1_1"] == "true" for row in rows) == 54
    assert sum(row["in_1_2_0"] == "true" for row in rows) == 60
    assert sum(row["in_1_3_0"] == "true" for row in rows) == 60


def test_normative_matrix_distinguishes_profiles_and_known_slices():
    with MATRIX.open(encoding="utf-8", newline="") as stream:
        rows = {row["requirement_id"]: row for row in csv.DictReader(stream)}

    assert rows["M_4.3-1"]["profile_scope"] == "GEVER"
    assert rows["M_4.4-1"]["profile_scope"] == "FILES"
    assert rows["M_4.12-2"]["in_1_0"] == "false"
    assert rows["M_4.12-2"]["in_1_3_0"] == "true"
    assert "attribute workflow only" in rows["M_4.12-2"]["test_evidence"]
    assert rows["M_4.5-1"]["assessment"] == "partial-sip-roundtrip-verified"
    assert rows["M_4.10-1"]["assessment"] == "partial-dossier-rule-verified"