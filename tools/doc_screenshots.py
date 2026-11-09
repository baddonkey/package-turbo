"""Generates the screenshots of docs/user-guide by driving the running application.

Usage: .venv\\Scripts\\python.exe tools\\doc_screenshots.py [--lang fr]
Needs the KOST-CECO sample in samples/SIP_20220328_KOST_eCH1.2G_1a-3d-IO. Opens a real window for about a minute.
"""

import shutil
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QPoint, QSettings, QTimer  # noqa: E402
from PySide6.QtGui import QCursor, QGuiApplication, QImage, QPainter  # noqa: E402
from PySide6.QtPdf import QPdfDocument  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

import main  # noqa: E402
from ph_backend import notes, reports  # noqa: E402
from ph_backend.backend import Backend  # noqa: E402
from ph_backend.sip import SipPackage  # noqa: E402

SAMPLE = ROOT / "samples" / "SIP_20220328_KOST_eCH1.2G_1a-3d-IO"
LANG = "fr" if "--lang" in sys.argv and sys.argv[-1] == "fr" else "de"
OUT = ROOT / "docs" / "user-guide" / "img"
WORK = Path(tempfile.mkdtemp(prefix="pt-doc-"))
STEP_MS = 900

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(WORK / "settings"))


class ScreenshotBackend(Backend):
    def __init__(self, settings):
        super().__init__(settings)
        self.language = LANG
        self.themeMode = "light"
        self.auditOperator = "Dokumentation"
        self.reporterName = "Dokumentation"


class Driver:
    def __init__(self, engine: QQmlApplicationEngine):
        self.engine = engine
        self.win = engine.rootObjects()[0]
        context = engine.rootContext()
        self.backend = context.contextProperty("backend")
        self.editor = self.backend.editor
        self.ctl = {n: context.contextProperty(n) for n in ("structure", "fileOps", "notesCtl", "searchCtl", "packageCtl")}
        self.steps = []

    # ---------------------------------------------------------------- helpers

    def find(self, name: str) -> QObject:
        obj = self.win.findChild(QObject, name)
        if obj is None:
            items = [self.win.contentItem()]
            while items:
                item = items.pop()
                if item.objectName() == name:
                    return item
                items.extend(item.childItems())
        if obj is None:
            raise RuntimeError(f"QML object {name} not found")
        return obj

    def call(self, name: str, method: str, *args) -> None:
        if not QMetaObject.invokeMethod(self.find(name), method, *[Q_ARG("QVariant", a) for a in args]):
            raise RuntimeError(f"Cannot invoke {name}.{method}")

    def shot(self, name: str) -> None:
        image = self.win.grabWindow()
        if image.isNull() or not image.save(str(OUT / f"{name}.png")):
            raise RuntimeError(f"Could not save screenshot {name}")
        print("saved", name, flush=True)

    def pkg(self):
        return self.backend.package

    def first(self, kind: str):
        return next(self.pkg().iter_kind(kind))

    def popup_menu(self, menu: str, x: int, y: int) -> None:
        QCursor.setPos(self.win.mapToGlobal(QPoint(x, y)))
        self.call(menu, "popup")

    def tab(self, name: str, index: int) -> None:
        self.find(name).setProperty("currentIndex", index)

    def maximize(self, pane: str) -> None:
        self.win.setProperty("maximized", pane)

    def add(self, action, shot: str | None = None, wait: int = STEP_MS) -> None:
        self.steps.append((action, shot, wait))

    def run(self) -> None:
        def finish_step(shot):
            if self.backend.busy:
                def when_idle():
                    if not self.backend.busy:
                        self.backend.busyChanged.disconnect(when_idle)
                        QTimer.singleShot(100, lambda: finish_step(shot))
                self.backend.busyChanged.connect(when_idle)
                return
            try:
                if shot:
                    self.shot(shot)
            except Exception:
                traceback.print_exc()
                QGuiApplication.instance().exit(1)
                return
            next_step()

        def next_step():
            if not self.steps:
                QGuiApplication.instance().exit(0)
                return
            action, shot, wait = self.steps.pop(0)
            try:
                action()
            except Exception:
                traceback.print_exc()
                QGuiApplication.instance().exit(1)
                return
            QTimer.singleShot(wait, lambda: finish_step(shot))
        QTimer.singleShot(1500, next_step)
        QTimer.singleShot(180000, lambda: QGuiApplication.instance().exit(2))

    # ---------------------------------------------------------------- scenes

    def scenes(self) -> None:
        sip = WORK / SAMPLE.name
        win = self.win
        win.setProperty("width", 1440)
        win.setProperty("height", 900)

        if LANG == "fr":
            self.add(lambda: self.backend.set_package(SipPackage.open_folder(sip)))
            self.add(lambda: self.backend.reveal(self.pkg().key(self.first("dossier"))), "fr-hauptfenster", 1500)
            return

        self.add(lambda: None, "01-start")
        self.add(lambda: self.backend.set_package(SipPackage.open_folder(sip)), "02-ueberblick", 1500)
        self.add(lambda: self.backend.reveal(self.pkg().key(self.first("dossier"))), "03-dossier")
        self.add(lambda: self.editor.showTab("statistik"), "04-statistik")
        self.add(lambda: self.backend.validate(True), None, 3000)
        self.add(lambda: self.editor.showTab("validierung"), "05-validierung")
        self.add(lambda: self.maximize("actions"), "06-validierungshilfe")
        self.add(lambda: self.maximize(""))

        self.add(lambda: self.backend.reveal(self.pkg().key(self.first("ordnungssystemposition"))))
        self.add(lambda: self.popup_menu("classificationMenu", 160, 160), "07-os-kontextmenu")
        self.add(lambda: self.call("classificationMenu", "close"))

        self.add(lambda: (self.tab("navigatorTabs", 0), self.maximize("lowerNav")), "08-dossier-navigator")
        self.add(lambda: self.maximize(""))
        self.add(lambda: self.tab("navigatorTabs", 1))
        content_file = lambda: next(f for f in self.pkg().iter_kind("datei")
                                    if self.pkg().relpath(f).parts[:1] == ("content",))
        self.add(lambda: self.call("packageNavigator", "revealKey", self.pkg().key(content_file())), "09-paket-navigator")
        self.add(lambda: self.popup_menu("packageNavMenu", 160, 620), "10-paket-kontextmenu")
        self.add(lambda: self.call("packageNavMenu", "close"))

        self.add(lambda: self.call("newPackageDialog", "open"), "11-neues-paket")
        self.add(lambda: self.call("newPackageDialog", "close"))
        content = lambda: next(o for o in self.pkg().iter_kind("ordner") if self.pkg().text(o, "name") == "content")
        self.add(lambda: self.call("massAssignDialog", "start", [self.pkg().key(content())],
                                   self.pkg().key(self.pkg().classification_system), "ordnungssystem",
                                   "KOST-CECO: System Test"), "12-massenzuweisung")
        self.add(lambda: self.call("massAssignDialog", "close"))
        self.add(lambda: self.call("massEditDialog", "start", self.pkg().key(self.pkg().classification_system),
                                   "KOST-CECO: System Test"), "13-massenmutation")
        self.add(lambda: self.call("massEditDialog", "close"))
        self.add(lambda: self.call("renumberDialog", "open"), "14-nummerieren")
        self.add(lambda: self.call("renumberDialog", "close"))

        def edit_title():
            dossier = self.first("dossier")
            self.backend.reveal(self.pkg().key(dossier))
            self.editor.setField(self.pkg().key(dossier), "titel", "Test")
        self.add(edit_title, "15-feldfehler")
        self.add(lambda: self.tab("actionTabs", 4), "16-aenderungen")

        def add_note():
            dossier = self.first("dossier")
            self.ctl["notesCtl"].addNote([self.pkg().key(dossier)], "Bitte Schutzfristen mit der abliefernden Stelle klären.")
            self.backend.reveal(self.pkg().key(dossier))
            self.tab("actionTabs", 1)
        self.add(add_note, "17-notizen")
        self.add(lambda: (self.ctl["searchCtl"].drawSample(), self.tab("actionTabs", 2)), "18-stichprobe")
        self.add(lambda: (self.tab("actionTabs", 3), self.find("simpleSearchField").setProperty("text", "Test"),
                  self.ctl["searchCtl"].simpleSearch("Test")), "19-suche")

        def advanced_search():
            search = self.ctl["searchCtl"]
            self.tab("actionTabs", 3)
            self.tab("searchModeTabs", 1)
            kind = self.find("searchKind-0")
            kind_index = next(index for index, value in enumerate(search.kinds, 1) if value["kind"] == "dossier")
            kind.setProperty("currentIndex", kind_index)
            QMetaObject.invokeMethod(kind, "activated", Q_ARG("int", kind_index))
            field_index = next(index for index, value in enumerate(search.fields("dossier"))
                               if value["tag"] == "erscheinungsform")
            self.find("searchField-0").setProperty("currentIndex", field_index)
            self.find("searchValue-0").setProperty("text", "digital")
            search.advancedSearch([{"kind": "dossier", "tag": "erscheinungsform", "value": "digital"}])
        self.add(advanced_search, "20-erweiterte-suche")

        self.add(lambda: self.call("preferencesDialog", "open"), "21-benutzervorgaben")
        self.add(lambda: self.call("preferencesDialog", "close"))

        def show_incoming_file_references():
            identifiers = sorted(self.pkg().referenced_ids())
            if not identifiers:
                raise RuntimeError("The sample SIP has no file references")
            file_element = self.pkg().file_by_id(identifiers[0])
            if file_element is None:
                raise RuntimeError("A sample file reference has no target")
            self.backend.showIncomingFileReferences = True
            self.maximize("editor")
            self.backend.reveal(self.pkg().key(file_element))

        def select_incoming_reference_target():
            target_picker = self.find("incomingReferenceTarget-" + str(self.incoming_file_key))
            if target_picker.property("count") > 1:
                target_picker.setProperty("currentIndex", 1)

        def prepare_incoming_file_references():
            identifiers = sorted(self.pkg().referenced_ids())
            self.incoming_file_key = self.pkg().key(self.pkg().file_by_id(identifiers[0]))
            show_incoming_file_references()

        self.add(prepare_incoming_file_references, None, 1200)
        self.add(select_incoming_reference_target, "26-dateiverweise")
        self.add(lambda: (self.maximize(""), setattr(self.backend, "showIncomingFileReferences", False)))
        self.add(lambda: self.call("shortcutsDialog", "open"), "22-tastenbelegung")
        self.add(lambda: self.call("shortcutsDialog", "close"))
        self.add(lambda: self.call("aboutDialog", "open"), "23-ueber")
        self.add(lambda: self.call("aboutDialog", "close"))

        def additional_data():
            dossier = self.first("dossier")
            key = self.pkg().key(dossier)
            self.backend.reveal(key)
            self.editor.setAdditionalData(key, [{"name": "Projektnummer", "value": "P-2021-017"},
                                                {"name": "Herkunft", "value": "Scan Papierakten"}])
        self.add(additional_data, "25-zusatzdaten")
        self.add(lambda: render_report(self.pkg()))


def render_report(pkg) -> None:
    for report in ("delivery",):
        pdf = WORK / f"{report}.pdf"
        reports.write_pdf(pkg, report, pdf, "Dokumentation")
        document = QPdfDocument()
        document.load(str(pdf))
        pages = [document.render(i, document.pagePointSize(i).toSize() * 1.6) for i in range(min(2, document.pageCount()))]
        width = sum(p.width() for p in pages) + 20 * (len(pages) - 1)
        combined = QImage(width, max(p.height() for p in pages), QImage.Format.Format_ARGB32)
        combined.fill(0xFFDDDDDD)
        painter = QPainter(combined)
        x = 0
        for page in pages:
            painter.fillRect(x, 0, page.width(), page.height(), 0xFFFFFFFF)
            painter.drawImage(x, 0, page)
            x += page.width() + 20
        painter.end()
        if not combined.save(str(OUT / "24-bericht.png")):
            raise RuntimeError("Could not save report screenshot")
        print("saved 24-bericht", flush=True)


class Engine(QQmlApplicationEngine):
    def loadFromModule(self, *args):
        super().loadFromModule(*args)
        driver = Driver(self)
        driver.scenes()
        driver.run()


def run() -> int:
    if not SAMPLE.is_dir():
        print(f"Sample missing: {SAMPLE}")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SAMPLE, WORK / SAMPLE.name)
    main.QQmlApplicationEngine = Engine
    main.Backend = ScreenshotBackend
    notes.default_author = lambda: "Dokumentation"
    sys.argv = [sys.argv[0]]
    try:
        return main.main()
    finally:
        shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(run())
