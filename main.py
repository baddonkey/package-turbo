import os
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QSettings, QTranslator
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from ph_backend.backend import Backend
from ph_backend.controllers import (FileController, NoteController, PackageController, SearchController,
                                    StructureController)

BASE_DIR = Path(__file__).resolve().parent
APP_NAME = "Package Turbo"
APP_VERSION = "0.1.0"
_UI_FONT_ID = -1


def _manual_paths() -> list[Path]:
    return [BASE_DIR / "docs" / "user-guide" / "Benutzerdokumentation.md"]


def create_engine(backend: Backend) -> QQmlApplicationEngine:
    global _UI_FONT_ID
    app = QGuiApplication.instance()
    if app is not None:
        font_path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "segoeui.ttf"
        if font_path.is_file() and _UI_FONT_ID < 0:
            _UI_FONT_ID = QFontDatabase.addApplicationFont(str(font_path))
        app.setFont(QFont("Segoe UI", 10))

    backend._software_version = APP_VERSION
    controllers = {
        "structure": StructureController(backend),
        "fileOps": FileController(backend),
        "notesCtl": NoteController(backend),
        "searchCtl": SearchController(backend),
        "packageCtl": PackageController(backend, _manual_paths()),
    }

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(BASE_DIR))
    context = engine.rootContext()
    context.setContextProperty("backend", backend)
    context.setContextProperty("editor", backend.editor)
    for name in ("classificationModel", "dossierModel", "packageModel", "validationTable", "changesTable",
                 "searchTable", "notesTable", "sampleTable", "historyTable"):
        context.setContextProperty(name, getattr(backend, name))
    for name, controller in controllers.items():
        context.setContextProperty(name, controller)
    context.setContextProperty("appVersion", APP_VERSION)

    engine.loadFromModule("App", "Main")
    return engine


def main() -> int:
    QQuickStyle.setStyle("Fusion")

    app = QGuiApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("package-turbo")
    app.setWindowIcon(QIcon(str(BASE_DIR / "App" / "icons" / "app.svg")))

    backend = Backend(QSettings())
    translator = QTranslator(app)
    if backend.language == "fr" and translator.load(str(BASE_DIR / "App" / "i18n" / "package_turbo_fr.qm")):
        app.installTranslator(translator)
        QLocale.setDefault(QLocale(QLocale.Language.French, QLocale.Country.Switzerland))

    engine = create_engine(backend)
    if not engine.rootObjects():
        return -1

    if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir():
        backend.openRecent(sys.argv[1])

    ret = app.exec()
    backend.shutdown()
    del engine
    return ret


if __name__ == "__main__":
    sys.exit(main())
