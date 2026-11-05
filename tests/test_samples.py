"""Regression tests with the public KOST-CECO eCH-0160 test packages (downloaded to samples/, skipped otherwise)."""

from pathlib import Path

import pytest
from PySide6.QtGui import QGuiApplication

from ph_backend import navigators, statistics
from ph_backend.editor import MetadataEditor
from ph_backend.sip import SipPackage
from ph_backend.validation import Validator

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

SAMPLES = [
    "SIP_20070923_eCH1.0G_RIS",
    "SIP_20070923_eCH1.1G_RIS_vorgang",
    "SIP_20120628_eCH1.0F_BfB",
    "SIP_20220328_KOST_eCH1.2G_1a-3d-IO",
    "SIP_20220328_KOST_eCH1.2F_1a-3d-IO",
    "SIP_20260421_KOST_eCH1.3F_1a-3d-IO",
]


@pytest.fixture(scope="module", autouse=True)
def app():
    return QGuiApplication.instance() or QGuiApplication(["test", "-platform", "offscreen"])


@pytest.mark.parametrize("name", SAMPLES)
def test_sample_versions(name):
    folder = SAMPLES_DIR / name
    if not folder.is_dir():
        pytest.skip(f"{name} not available in samples/")
    pkg = SipPackage.open_folder(folder, read_only=True)
    issues = Validator(pkg).run(full=True)
    found = {i["checkId"] for i in issues}
    assert not found & {"schema", "checksum", "missing_file", "surplus_file", "wrong_file"}
    if pkg.root.get("schemaVersion") in {"5.0", "5.1"}:
        assert not any(i["checkId"] == "missing_values" and i["fieldTag"] == "entstehungszeitraum"
                       for i in issues)
    for build in (navigators.build_classification_tree, navigators.build_dossier_tree, navigators.build_package_tree):
        model = navigators.NavigatorModel(["x"])
        build(model, pkg)
        assert model.itemCount() > 1
    editor = MetadataEditor()
    editor.set_package(pkg)
    editor.showElement(pkg.key(next(pkg.iter_kind("dossier"))))
    assert editor.sections and editor.sections[0]["primary"]
    assert statistics.time_span_comparison(pkg)["bars"]
