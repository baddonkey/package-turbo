import pytest
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QGuiApplication

from ph_backend.backend import Backend
from ph_backend.controllers import (FileController, NoteController, PackageController, SearchController,
                                    StructureController)


@pytest.fixture(scope="module")
def app():
    return QGuiApplication.instance() or QGuiApplication(["test", "-platform", "offscreen"])


@pytest.fixture
def backend(app, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    backend = Backend(settings)
    backend.auditOperator = "confirmed-test-operator"
    backend.messages = []
    backend.message.connect(lambda title, text: backend.messages.append((title, text)))
    return backend


@pytest.fixture
def opened(backend, sip_dir):
    backend.openPackage(QUrl.fromLocalFile(str(sip_dir)), False)
    return backend


def test_appearance_theme_setting_defaults_to_system_and_persists(backend):
    assert backend.themeMode == "system"
    assert backend.systemTheme in ("light", "dark")

    for theme in ("light", "dark", "system"):
        backend.themeMode = theme
        assert backend.themeMode == theme

    backend.themeMode = "invalid"
    assert backend.themeMode == "system"


def test_incoming_file_reference_setting_defaults_off_and_persists(backend):
    from PySide6.QtCore import QSettings

    assert backend.showIncomingFileReferences is False
    backend.showIncomingFileReferences = True
    backend._settings.sync()
    restored = Backend(QSettings(backend._settings.fileName(), QSettings.Format.IniFormat))
    assert restored.showIncomingFileReferences is True
    restored.shutdown()


def test_open_edit_save_cycle(opened, sip_dir):
    backend = opened
    assert backend.hasPackage and not backend.dirty
    assert backend.classificationModel.itemCount() > 0
    assert backend.recentPackages == [str(sip_dir)]

    pkg = backend.package
    dossier = next(pkg.iter_kind("dossier"))
    backend.select(pkg.key(dossier))
    assert backend.editor.currentTab == "dossier"

    backend.editor.setField(pkg.key(dossier), "titel", "Neuer Dossiertitel")
    assert backend.dirty and backend.changesTable.total == 1
    assert backend.classificationModel.indexOfKey(pkg.key(dossier)).data() == "Neuer Dossiertitel"
    assert backend.save() and not backend.dirty
    assert backend.changesTable.total == 0
    assert "Neuer Dossiertitel" in (sip_dir / "header" / "metadata.xml").read_text(encoding="utf-8")


@pytest.mark.parametrize(("version", "expected"), [("1.0", "4.0"), ("1.1", "4.1"),
                                                    ("1.2", "5.0"), ("1.3", "5.1")])
@pytest.mark.parametrize("delivery_type", ["GEVER", "FILES"])
def test_creation_controller_selects_version_and_delivery_type(backend, tmp_path, version, expected, delivery_type):
    from ph_backend import validation
    from ph_backend.sip import SipPackage

    ctl = PackageController(backend, [])
    assert ctl.xsdVersions[0]["version"] == "1.3"
    assert ctl.createPackage(QUrl.fromLocalFile(str(tmp_path)), "SIP_20260104_Amt_Selected", "Amt",
                             delivery_type, "", "Plan", QUrl(), version)
    assert backend.package.root.get("schemaVersion") == expected
    assert backend.package.delivery_type == delivery_type
    expected_type = "ablieferungGeverSIP" if delivery_type == "GEVER" else "ablieferungFilesSIP"
    assert backend.package.delivery.get("{http://www.w3.org/2001/XMLSchema-instance}type") == expected_type
    assert not [issue for issue in validation.Validator(backend.package).run(full=True)
                if issue["checkId"] == "schema"]
    backend.package.save()
    reopened = SipPackage.open_folder(backend.package.root_dir)
    assert reopened.root.get("schemaVersion") == expected
    assert reopened.delivery_type == delivery_type


def test_package_creation_records_initial_audit_event(backend, tmp_path):
    from pathlib import Path

    controller = PackageController(backend, [])

    assert controller.createPackage(QUrl.fromLocalFile(str(tmp_path)), "SIP_20261106_Amt_Audited",
                                    "Amt", "GEVER", "", "Plan", QUrl(), "1.3")

    events = backend.historyTable.records()
    assert len(events) == 1
    assert events[0]["eventType"] == "package creation"
    detail = events[0]["detail"]
    assert {key: detail[key] for key in ("packageName", "schemaVersion", "deliveryType")} == {
        "packageName": "SIP_20261106_Amt_Audited",
        "schemaVersion": "5.1",
        "deliveryType": "GEVER",
    }
    assert detail["manifest"]["header/metadata.xml"]["sha256"]
    assert detail["manifest"]["content"]["type"] == "directory"
    assert (Path(backend.auditCompanion) / "journal.sqlite3").is_file()


def test_package_creation_requires_operator_before_writing_sip(backend, tmp_path):
    controller = PackageController(backend, [])
    backend.auditOperator = ""
    required = []
    backend.auditOperatorRequired.connect(lambda: required.append(True))

    assert not controller.createPackage(QUrl.fromLocalFile(str(tmp_path)), "SIP_20261106_Amt_NoOperator",
                                         "Amt", "GEVER", "", "Plan", QUrl(), "1.3")

    assert required
    assert list(tmp_path.iterdir()) == []


def test_existing_package_registers_current_baseline_without_claiming_creation(opened):
    from pathlib import Path
    from ph_backend.audit import AuditJournal

    pkg = opened.package
    assert not Path(opened.auditCompanion).exists()
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "First audited change")
    assert opened.save()

    records = AuditJournal(Path(opened.auditCompanion) / "journal.sqlite3", read_only=True).records()
    assert records[0]["payload"]["eventType"] == "package registration"
    detail = records[0]["payload"]["detail"]
    assert detail["note"] == "Current package state registered; earlier history is unknown."
    assert detail["manifest"]["header/metadata.xml"]["sha256"]
    assert records[-1]["payload"]["eventType"] == "package commit"


def test_native_creation_dialog_renders_version_choices(backend, app, tmp_path, sip_dir, monkeypatch):
    import os
    import sys
    from pathlib import Path
    from PySide6.QtCore import QMetaObject, QObject, QPointF, QUrl, Qt
    from PySide6.QtGui import QFont, QFontDatabase, QRawFont, QKeySequence
    from PySide6.QtQuick import QQuickItem, QQuickWindow, QSGRendererInterface
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtTest import QTest
    from PySide6.QtQml import QQmlComponent
    from main import create_engine

    if sys.platform == "win32" and app.platformName() == "offscreen":
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf"
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        assert font_id >= 0
        families = QFontDatabase.applicationFontFamilies(font_id)
        symbol_path = font_path.with_name("seguisym.ttf")
        symbol_id = QFontDatabase.addApplicationFont(str(symbol_path))
        assert symbol_id >= 0
        symbols = QFontDatabase.applicationFontFamilies(symbol_id)
        assert QRawFont.fromFont(QFont(symbols[0], 9)).supportsCharacter(0x21B6)
        font = QFont()
        font.setFamilies(families + symbols)
        font.setPointSize(9)
        app.setFont(font)
    assert QRawFont.fromFont(app.font()).supportsCharacter(ord("A"))
    QQuickStyle.setStyle("Fusion")
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
    engine = create_engine(backend)
    assert engine.rootObjects()
    window = engine.rootObjects()[0]
    window.setWidth(1280)
    window.setHeight(800)
    assert QTest.qWaitForWindowExposed(window, 2000)

    def contrast(foreground, background):
        def luminance(color):
            channels = color.getRgbF()[:3]
            linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                      for value in channels]
            return sum(weight * value for weight, value in zip((0.2126, 0.7152, 0.0722), linear))

        light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
        return (light + 0.05) / (dark + 0.05)

    def visual_items(root):
        pending = [root]
        while pending:
            item = pending.pop()
            yield item
            pending.extend(item.childItems())

    input_dialog = window.findChild(QObject, "inputDialog")
    input_dialog.setProperty("title", "Neue Notiz")
    input_dialog.setProperty("label", "Notiz zu 1 Objekt(en):")
    input_dialog.setProperty("multiline", True)
    badge_component = QQmlComponent(engine, QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / "App" / "KindBadge.qml")))
    badge = badge_component.create()
    badge_text = badge.findChild(QQuickItem, "kindBadgeText")
    for theme in ("light", "dark"):
        backend.themeMode = theme
        assert QMetaObject.invokeMethod(input_dialog, "open")
        QTest.qWait(50)
        background_color = input_dialog.property("background").property("color")
        assert contrast(input_dialog.property("header").property("color"), background_color) >= 4.5
        assert contrast(input_dialog.findChild(QQuickItem, "inputDialogPrompt").property("color"), background_color) >= 4.5
        assert contrast(window.property("secondaryTextColor"), background_color) >= 4.5
        assert window.grabWindow().save(str(tmp_path / ("input-dialog-" + theme + ".png")))
        assert QMetaObject.invokeMethod(input_dialog, "close")
        message_dialog = window.findChild(QObject, "messageDialog")
        message_dialog.setProperty("title", "Hinweis")
        message_dialog.setProperty("message", "Prüfung abgeschlossen")
        assert QMetaObject.invokeMethod(message_dialog, "open")
        QTest.qWait(30)
        assert contrast(message_dialog.findChild(QQuickItem, "messageBoxTitle").property("color"),
                message_dialog.property("header").property("color")) >= 4.5
        assert contrast(message_dialog.findChild(QQuickItem, "messageBoxText").property("color"),
                message_dialog.property("background").property("color")) >= 4.5
        assert QMetaObject.invokeMethod(message_dialog, "close")
        for dialog_name in ("newPackageDialog", "preferencesDialog", "massAssignDialog", "massEditDialog",
                            "auditExportDialog", "storageCleanupDialog"):
            checked_dialog = window.findChild(QObject, dialog_name)
            assert QMetaObject.invokeMethod(checked_dialog, "open")
            QTest.qWait(30)
            dialog_background = checked_dialog.property("background").property("color")
            assert contrast(checked_dialog.property("header").property("color"), dialog_background) >= 4.5
            visible_labels = [item for item in checked_dialog.findChildren(QQuickItem)
                              if item.metaObject().className().startswith("Label_")
                              and item.isVisible() and item.isEnabled() and item.property("text")]
            assert visible_labels
            for label in visible_labels:
                assert contrast(label.property("color"), dialog_background) >= 4.5, (dialog_name, theme, label.property("text"))
            if dialog_name == "preferencesDialog":
                checked_dialog.findChild(QObject, "auditOperatorField").setProperty("text", "Beispiel")
                checked_dialog.findChild(QObject, "reporterNameField").setProperty("text", "Beispiel")
                assert window.grabWindow().save(str(tmp_path / ("preferences-" + theme + ".png")))
            assert QMetaObject.invokeMethod(checked_dialog, "close")
        for kind in ("paket", "ablieferung", "provenienz", "ordnungssystem", "ordnungssystemposition",
                     "dossier", "subdossier", "dokument", "vorgang", "aktivitaet", "mappe", "datei", "ordner", "unknown"):
            badge.setProperty("kind", kind)
            assert contrast(badge_text.property("color"), badge.property("color")) >= 4.5
    backend.themeMode = "system"
    tabs = window.findChild(QQuickItem, "actionTabs")
    tab_list = window.findChild(QQuickItem, "actionTabList")
    scrollbar = window.findChild(QQuickItem, "actionTabScrollBar")
    window.setMinimumWidth(600)
    for width, scroll_expected in ((1280, False), (980, False), (650, True), (1280, False)):
        window.setWidth(width)
        QTest.qWait(100)
        assert scrollbar.isVisible() == scroll_expected
        if scroll_expected:
            assert tab_list.property("contentWidth") > tab_list.width()
            assert scrollbar.mapToScene(QPointF(0, 0)).y() >= tabs.mapToScene(QPointF(0, tabs.height())).y()
        for name, index in (("notesActionTab", 1), ("sampleActionTab", 2)):
            tabs.setProperty("currentIndex", 0)
            QTest.qWait(30)
            button = window.findChild(QQuickItem, name)
            point = button.mapToScene(QPointF(button.width() / 2, button.height() * 0.8)).toPoint()
            QTest.mouseMove(window, point)
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
            assert tabs.property("currentIndex") == index
            if scroll_expected:
                tabs.setProperty("currentIndex", 0)
                QTest.qWait(30)
                start = scrollbar.mapToScene(QPointF(scrollbar.width() * 0.2, scrollbar.height() / 2)).toPoint()
                end = scrollbar.mapToScene(QPointF(scrollbar.width() * 0.8, scrollbar.height() / 2)).toPoint()
                QTest.mousePress(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
                QTest.mouseMove(window, end, 50)
                QTest.mouseRelease(window, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
                assert tab_list.property("contentX") > 0
    window.setMinimumWidth(980)
    package_menu = window.findChild(QObject, "packageMenu")
    recent_name = "SIP_20260421_KOST_eCH1.3G_1a-3d-IO"
    backend._settings.setValue("recentPackages", ["C:/packages/" + recent_name])
    backend.recentChanged.emit()
    assert QMetaObject.invokeMethod(package_menu, "open")
    QTest.qWait(50)
    recent_item = package_menu.findChild(QQuickItem, "recentPackage-0")
    recent_label = recent_item.property("contentItem")
    assert recent_item.property("text") == "1  " + recent_name
    assert package_menu.property("width") > 200
    assert recent_label.property("lineCount") == 1
    assert recent_label.property("paintedWidth") <= recent_label.width()
    long_name = "SIP_" + "longpackageidentifier" * 10
    backend._settings.setValue("recentPackages", ["C:/packages/" + long_name])
    backend.recentChanged.emit()
    QTest.qWait(50)
    recent_item = package_menu.findChild(QQuickItem, "recentPackage-0")
    recent_label = recent_item.property("contentItem")
    assert recent_item.property("text") == "1  " + long_name
    assert package_menu.property("width") <= window.width() - 24
    assert recent_label.property("lineCount") > 1
    assert recent_label.property("paintedWidth") <= recent_label.width()
    assert recent_item.height() >= recent_label.property("paintedHeight")
    menu_items = package_menu.findChildren(QQuickItem)
    open_item = next(item for item in menu_items if item.property("text") == "Paket öffnen..."
                     and item.property("contentItem") is not None)
    save_item = next(item for item in menu_items if item.property("text") == "Speichern"
                     and item.property("contentItem") is not None)
    assert open_item.isEnabled() and not save_item.isEnabled()
    for theme, active_color, disabled_color in (("light", "#1c2d2a", "#899791"),
                                                 ("dark", "#e5eeeb", "#82948e")):
        backend.themeMode = theme
        app.processEvents()
        assert open_item.property("contentItem").property("color").name() == active_color
        assert save_item.property("contentItem").property("color").name() == disabled_color
    assert QMetaObject.invokeMethod(package_menu, "close")
    backend.themeMode = "system"
    dialog = window.findChild(QObject, "newPackageDialog")
    assert QMetaObject.invokeMethod(dialog, "open")
    app.processEvents()
    choices = dialog.findChild(QObject, "schemaVersionBox")
    assert choices.property("count") == 4
    assert choices.property("currentValue") == "1.3"
    choices.setProperty("currentIndex", 3)
    assert choices.property("currentValue") == "1.0"
    centres = []
    for name in ("locationLabel", "locationField", "locationBrowse"):
        item = dialog.findChild(QObject, name)
        centres.append(item.mapToScene(QPointF(0, item.property("height") / 2)).y())
    assert max(centres) - min(centres) < 2
    assert dialog.property("footer").property("count") == 2
    image = window.grabWindow()
    assert not image.isNull()
    colours = {image.pixelColor(horizontal, vertical).rgba()
               for horizontal in range(0, image.width(), 32) for vertical in range(0, image.height(), 32)}
    assert len(colours) > 5
    assert image.save(str(tmp_path / "creation-dialog.png"))
    assert QMetaObject.invokeMethod(dialog, "close")
    from ph_backend.sip import SipPackage

    backend.set_package(SipPackage.open_folder(sip_dir))
    assert save_item.isEnabled()
    for menu_name in ("classificationMenu", "packageNavMenu"):
        navigator_menu = window.findChild(QObject, menu_name)
        assert QMetaObject.invokeMethod(navigator_menu, "open")
        QTest.qWait(50)
        menu_entries = [item for item in navigator_menu.findChildren(QQuickItem)
                        if item.property("text") and item.property("contentItem") is not None]
        assert menu_entries
        for entry in menu_entries:
            assert entry.width() >= entry.implicitWidth(), (menu_name, entry.property("text"))
        assert QMetaObject.invokeMethod(navigator_menu, "close")
    tabs.setProperty("currentIndex", 0)
    QTest.qWait(50)
    for theme in ("light", "dark"):
        backend.themeMode = theme
        QTest.qWait(50)
        delivery_label = window.findChild(QQuickItem, "deliveryHeaderLabel")
        delivery_background = window.findChild(QQuickItem, "deliveryHeaderBackground")
        assert contrast(delivery_label.property("color"), delivery_background.property("color")) >= 4.5
        for object_name in ("tableHeadingLabel", "navigatorHeadingLabel"):
            headings = [item for item in visual_items(window.contentItem())
                        if item.objectName() == object_name and item.isVisible()]
            assert headings, object_name
            for heading in headings:
                assert contrast(heading.property("color"), heading.parentItem().property("color")) >= 4.5
        assert window.grabWindow().save(str(tmp_path / ("package-" + theme + ".png")))
    backend.themeMode = "system"
    package = backend.package
    backend.editor.setField(package.key(next(package.iter_kind("dossier"))), "titel", "Audited native edit")
    assert backend.save()
    tabs = window.findChild(QObject, "actionTabs")
    tabs.setProperty("currentIndex", 5)
    app.processEvents()
    assert window.findChild(QObject, "historyView") is not None
    assert [row["eventType"] for row in backend.historyTable.records()] == [
        "package registration",
        "package draft staging", "package draft staging", "package draft staging",
        "package commit preparation", "package operation", "metadata modification", "package commit"]
    assert "Audited native edit" in backend.historyDetails(5)
    preferences = window.findChild(QObject, "preferencesDialog")
    assert QMetaObject.invokeMethod(preferences, "open")
    app.processEvents()
    assert preferences.findChild(QObject, "auditOperatorField").property("text") == backend.auditOperator
    assert preferences.findChild(QObject, "workspaceLimit").property("value") == backend.workspaceLimitGiB
    assert preferences.findChild(QObject, "retentionCopies").property("value") == backend.retentionCopies
    assert preferences.findChild(QObject, "retentionAge").property("value") == backend.retentionAgeDays
    incoming_references_check = preferences.findChild(QObject, "showIncomingFileReferencesCheck")
    assert incoming_references_check is not None
    assert incoming_references_check.property("checked") is False
    preferences_scrollbar = preferences.findChild(QQuickItem, "preferencesVerticalScrollBar")
    assert preferences_scrollbar is not None and preferences_scrollbar.isVisible()
    scroll_left = preferences_scrollbar.parentItem().mapToScene(QPointF(0, 0)).x()
    scroll_right = scroll_left + preferences_scrollbar.parentItem().width()
    scrollbar_right = preferences_scrollbar.mapToScene(QPointF(preferences_scrollbar.width(), 0)).x()
    assert abs(scrollbar_right - scroll_right) <= 1
    theme_box = preferences.findChild(QQuickItem, "themeModeBox")
    appearance_group = preferences.findChild(QQuickItem, "appearancePreferencesGroup")
    references_group = preferences.findChild(QQuickItem, "incomingReferencesPreferencesGroup")
    history_group = preferences.findChild(QQuickItem, "metadataHistoryPreferencesGroup")
    appearance_bottom = appearance_group.mapToScene(QPointF(0, appearance_group.height())).y()
    references_top = references_group.mapToScene(QPointF(0, 0)).y()
    references_bottom = references_group.mapToScene(QPointF(0, references_group.height())).y()
    history_top = history_group.mapToScene(QPointF(0, 0)).y()
    assert references_top >= appearance_bottom - 1
    assert history_top >= references_bottom - 1
    assert incoming_references_check.isVisible()
    preferences_scroll = preferences.findChild(QQuickItem, "preferencesScrollView")
    assert preferences_scroll.property("contentHeight") > preferences_scroll.height()
    scroll_content = preferences_scroll.property("contentItem")
    scroll_content.setProperty("contentY", scroll_content.property("contentHeight") - scroll_content.height())
    app.processEvents()
    language_box = preferences.findChild(QQuickItem, "languageBox")
    language_top = language_box.mapToScene(QPointF(0, 0)).y()
    scroll_top = preferences_scroll.mapToScene(QPointF(0, 0)).y()
    assert scroll_top <= language_top < scroll_top + preferences_scroll.height()
    scroll_content.setProperty("contentY", 0)
    app.processEvents()
    incoming_references_check.setProperty("checked", True)
    theme_choices = preferences.findChild(QObject, "themeModeBox")
    assert theme_choices.property("count") == 3
    assert theme_choices.property("currentIndex") == 0
    theme_choices.setProperty("currentIndex", 2)
    assert QMetaObject.invokeMethod(preferences, "accept")
    app.processEvents()
    assert backend.themeMode == "dark"
    assert backend.showIncomingFileReferences is True
    assert window.property("darkMode") is True
    backend.themeMode = "system"
    app.processEvents()
    assert window.property("darkMode") == (backend.systemTheme == "dark")
    assert window.grabWindow().save(str(tmp_path / "metadata-history.png"))
    content = next(element for element in package.iter_kind("ordner") if package.text(element, "name") == "content")
    FileController(backend).newFolder(package.key(content), "NativeStaged")
    app.processEvents()
    assert backend.dirty and not (sip_dir / "content/NativeStaged").exists()
    assert (package.file_root / "content/NativeStaged").is_dir()
    history_item = window.findChild(QObject, "historyView")
    history_item.forceActiveFocus()
    combination = QKeySequence(QKeySequence.StandardKey.Undo)[0]
    QTest.keyClick(window, combination.key(), combination.keyboardModifiers())
    app.processEvents()
    assert not (package.file_root / "content/NativeStaged").exists()
    combination = QKeySequence(QKeySequence.StandardKey.Redo)[0]
    QTest.keyClick(window, combination.key(), combination.keyboardModifiers())
    app.processEvents()
    assert (package.file_root / "content/NativeStaged").is_dir()
    assert window.grabWindow().save(str(tmp_path / "staged-history.png"))
    undo_button = window.findChild(QObject, "packageUndoButton")
    redo_button = window.findChild(QObject, "packageRedoButton")
    assert undo_button.property("enabled") is True
    assert QMetaObject.invokeMethod(undo_button, "clicked")
    app.processEvents()
    assert not (package.file_root / "content/NativeStaged").exists()
    assert redo_button.property("enabled") is True
    assert QMetaObject.invokeMethod(redo_button, "clicked")
    app.processEvents()
    assert (package.file_root / "content/NativeStaged").is_dir()
    assert window.grabWindow().save(str(tmp_path / "undo-redo-history.png"))
    text_component = QQmlComponent(engine)
    text_component.setData(b'import QtQuick; import QtQuick.Controls; TextField { width: 200; height: 32; text: "Initial" }', QUrl())
    text_probe = text_component.create()
    assert text_probe is not None
    text_probe.setParent(window)
    text_probe.setParentItem(window.contentItem())
    text_probe.setProperty("cursorPosition", 7)
    text_probe.forceActiveFocus()
    QTest.keyClick(window, Qt.Key_X)
    assert text_probe.property("text") == "Initialx"
    position = backend._undo_history.position
    combination = QKeySequence(QKeySequence.StandardKey.Undo)[0]
    QTest.keyClick(window, combination.key(), combination.keyboardModifiers())
    app.processEvents()
    assert text_probe.property("text") == "Initial"
    assert backend._undo_history.position == position
    text_probe.setParentItem(None)
    assert backend.discardChanges()
    assert not (sip_dir / "content/NativeStaged").exists()
    import threading
    from PySide6.QtCore import QTimer
    import ph_backend.processing as processing

    entered, released = threading.Event(), threading.Event()
    copy_bytes = processing._copy_bytes
    cancel_button = window.findChild(QObject, "cancelTaskButton")
    previewed = []

    def copy_with_barrier(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert released.wait(3)
        return copy_bytes(*args, **kwargs)

    def cancel_from_ui():
        if entered.is_set() and not released.is_set():
            previewed.append(cancel_button.property("enabled"))
            assert window.grabWindow().save(str(tmp_path / "background-progress.png"))
            assert QMetaObject.invokeMethod(cancel_button, "clicked")
            released.set()

    monkeypatch.setattr(processing, "_copy_bytes", copy_with_barrier)
    timer = QTimer()
    timer.setInterval(1)
    timer.timeout.connect(cancel_from_ui)
    timer.start()
    current = backend.package
    content = next(element for element in current.iter_kind("ordner") if current.text(element, "name") == "content")
    try:
        FileController(backend).newFolder(current.key(content), "CancelledNative")
    finally:
        timer.stop()
        released.set()
    assert previewed == [True] and not backend.busy and not backend.dirty
    assert not (sip_dir / "content/CancelledNative").exists()
    current = backend.package
    backend.editor.setField(current.key(next(current.iter_kind("dossier"))), "titel", "Native protected save")
    workspace = backend._file_workspace
    finish = workspace._finish
    protected = []

    def commit_preview(*args, **kwargs):
        protected.append(cancel_button.property("enabled"))
        assert window.grabWindow().save(str(tmp_path / "protected-commit.png"))
        return finish(*args, **kwargs)

    monkeypatch.setattr(workspace, "_finish", commit_preview)
    assert backend.save() and protected == [False]
    from ph_backend.file_workspace import manifest

    before_cleanup = manifest(backend.package.root_dir)
    backend.retentionCopies = 1
    backend.retentionAgeDays = 0
    cleanup_button = window.findChild(QObject, "cleanupPreviewButton")
    assert QMetaObject.invokeMethod(cleanup_button, "clicked")
    app.processEvents()
    cleanup_dialog = window.findChild(QObject, "storageCleanupDialog")
    assert cleanup_dialog.property("visible")
    assert backend.retentionCandidates and backend.retentionBytes > 0
    assert window.grabWindow().save(str(tmp_path / "retention-preview.png"))
    apply_button = cleanup_dialog.findChild(QObject, "applyCleanupButton")
    assert apply_button.property("enabled")
    assert QMetaObject.invokeMethod(apply_button, "clicked")
    app.processEvents()
    assert manifest(backend.package.root_dir) == before_cleanup
    assert not backend.retentionCandidates
    assert backend.canUndo
    from ph_backend import files, structure as structure_ops
    from ph_backend.package_factory import create_package

    modern = create_package(tmp_path, "SIP_20261105_Test_NativeFields", "Test")
    position = next(modern.iter_kind("ordnungssystemposition"))
    dossier = structure_ops.add_objects(modern, position, "dossier")[0]
    document = structure_ops.add_objects(modern, dossier, "dokument")[0]
    modern.set_repeated_texts(document, "autor", ["Author one", "Author two"])
    content = next(element for element in modern.iter_kind("ordner") if modern.text(element, "name") == "content")
    reference_source = tmp_path / "native-reference.txt"
    reference_source.write_bytes(b"native reference")
    unused_source = tmp_path / "native-unreferenced.txt"
    unused_source.write_bytes(b"unreferenced file")
    files.import_paths(modern, content, [reference_source, unused_source])
    file_element = next(file_element for file_element in modern.children(content, "datei")
                        if modern.text(file_element, "name") == reference_source.name)
    unused_file_element = next(file_element for file_element in modern.children(content, "datei")
                                if modern.text(file_element, "name") == unused_source.name)
    structure_ops.assign_files(modern, document, [file_element])
    modern.save()
    assert backend.set_package(modern)
    app.processEvents()
    backend.select(modern.key(document))
    app.processEvents()
    assert backend.editor.currentTab == "dokument", backend.editor.currentTab

    def visual_item(parent, name):
        if parent.objectName() == name:
            return parent
        for child in parent.childItems():
            found = visual_item(child, name)
            if found is not None:
                return found
        return None

    def visible_visual_item(parent, name):
        if parent.objectName() == name and parent.isVisible():
            return parent
        for child in parent.childItems():
            found = visible_visual_item(child, name)
            if found is not None:
                return found
        return None

    window.grabWindow()
    more = visual_item(window.contentItem(), "moreFields-" + str(modern.key(document)))
    assert more is not None
    more.setProperty("checked", True)
    app.processEvents()
    author = visual_item(window.contentItem(), "repeatedValue-autor-0")
    assert author is not None and not author.property("readOnly")
    author.setProperty("text", "Native edited author")
    assert QMetaObject.invokeMethod(author, "editingFinished")
    app.processEvents()
    assert modern.repeated_texts(document, "autor") == ["Native edited author", "Author two"]
    assert visual_item(window.contentItem(), "references-" + str(modern.key(document))) is None
    assert modern.children(document, "dateiRef")[0].get("version") is None
    backend.select(modern.key(unused_file_element))
    app.processEvents()
    empty_message = visible_visual_item(window.contentItem(), "incomingReferencesEmptyMessage")
    assert empty_message is not None
    assert window.grabWindow().save(str(tmp_path / "incoming-reference-empty-state.png"))
    assert empty_message.isVisible(), (
        empty_message.property("visible"), empty_message.parentItem().isVisible(), backend.editor.currentTab,
        backend.showIncomingFileReferences, backend.editor.incomingReferenceAttributes(modern.key(unused_file_element)))
    target_options = backend.editor.incomingReferenceTargets(modern.key(unused_file_element))
    document_option = next(option for option in target_options if option["ownerKey"] == modern.key(document))
    target_picker = visual_item(window.contentItem(), "incomingReferenceTarget-" + str(modern.key(unused_file_element)))
    add_reference_button = visual_item(window.contentItem(), "addIncomingReferenceButton-"
                                       + str(modern.key(unused_file_element)))
    assert target_picker is not None and add_reference_button is not None
    assert target_picker.property("currentIndex") == 0
    assert add_reference_button.property("enabled") is False
    target_picker.setProperty("currentIndex", target_options.index(document_option) + 1)
    assert add_reference_button.property("enabled") is True
    assert QMetaObject.invokeMethod(add_reference_button, "clicked")
    app.processEvents()
    document_references = modern.children(document, "dateiRef")
    assert [reference.text for reference in document_references] == [
        file_element.get("id"), unused_file_element.get("id")]
    additional_target = next(option for option in backend.editor.incomingReferenceTargets(
        modern.key(unused_file_element)) if option["ownerKey"] == modern.key(document))
    assert additional_target["hasReference"] is True
    target_picker = visual_item(window.contentItem(),
                                "incomingReferenceTarget-" + str(modern.key(unused_file_element)))
    add_reference_button = visual_item(window.contentItem(),
                                       "addIncomingReferenceButton-" + str(modern.key(unused_file_element)))
    assert target_picker.property("currentIndex") == 0
    target_picker.setProperty("currentIndex", 1)
    assert add_reference_button.property("text") == "Weitere Referenz hinzufügen"
    assert QMetaObject.invokeMethod(add_reference_button, "clicked")
    app.processEvents()
    document_references = modern.children(document, "dateiRef")
    assert [reference.text for reference in document_references] == [
        file_element.get("id"), unused_file_element.get("id"), unused_file_element.get("id")]
    second_version = visual_item(window.contentItem(),
                                  "referenceAttribute-version-2-owner-" + str(modern.key(document)))
    assert second_version is not None
    second_version.setProperty("text", "2")
    assert QMetaObject.invokeMethod(second_version, "editingFinished")
    app.processEvents()
    assert document_references[1].get("version", "") == ""
    assert document_references[2].get("version") == "2"
    backend.select(modern.key(file_element))
    app.processEvents()
    incoming_group = visual_item(window.contentItem(), "incomingReferences-" + str(modern.key(file_element)))
    assert incoming_group is not None
    owner_label = visual_item(window.contentItem(),
                              "incomingReferenceOwner-" + str(modern.key(document)) + "-0")
    assert owner_label is not None and "Dokument" in owner_label.property("text")
    incoming_version = visual_item(window.contentItem(),
                                   "referenceAttribute-version-0-owner-" + str(modern.key(document)))
    assert incoming_version is not None and incoming_version.property("text") == ""
    incoming_version.setProperty("text", "3")
    assert QMetaObject.invokeMethod(incoming_version, "editingFinished")
    app.processEvents()
    assert modern.children(document, "dateiRef")[0].get("version") == "3"
    assert window.grabWindow().save(str(tmp_path / "incoming-file-references.png"))
    backend.select(modern.key(document))
    app.processEvents()
    assert visual_item(window.contentItem(), "references-" + str(modern.key(document))) is None
    assert modern.children(document, "dateiRef")[0].get("version") == "3"
    backend.showIncomingFileReferences = False
    backend.select(modern.key(file_element))
    app.processEvents()
    incoming_group = visual_item(window.contentItem(), "incomingReferences-" + str(modern.key(file_element)))
    assert incoming_group is not None and not incoming_group.isVisible()
    backend.showIncomingFileReferences = True
    backend.select(modern.key(document))
    app.processEvents()
    assert visual_item(window.contentItem(), "repeatedValue-autor-0") is not None
    window.setProperty("maximized", "editor")
    app.processEvents()
    assert window.grabWindow().save(str(tmp_path / "standards-metadata-fields.png"))
    window.setProperty("maximized", "")
    assert backend.save()
    structure_controller = StructureController(backend)
    process_key = structure_controller.addObjects(modern.key(dossier), "vorgang", 1)
    assert process_key
    activity_key = structure_controller.addObjects(process_key, "aktivitaet", 1)
    assert activity_key
    backend.select(activity_key)
    app.processEvents()
    assert backend.editor.sections[0]["readOnly"] is False
    instruction = visual_item(window.contentItem(), "metadataField-vorschreibung")
    assert instruction is not None and not instruction.property("readOnly")
    instruction.setProperty("text", "Native activity instruction")
    assert QMetaObject.invokeMethod(instruction, "editingFinished")
    app.processEvents()
    assert modern.text(modern.element(activity_key), "vorschreibung") == "Native activity instruction"
    instruction = visual_item(window.contentItem(), "metadataField-vorschreibung")
    instruction.forceActiveFocus()
    instruction.setProperty("text", "Saved while field focused")
    save_button = window.findChild(QObject, "savePackageButton")
    assert QMetaObject.invokeMethod(save_button, "clicked")
    app.processEvents()
    assert b"Saved while field focused" in modern.metadata_path.read_bytes()
    assert window.grabWindow().save(str(tmp_path / "standards-activity.png"))
    assert backend.discardChanges()
    window.hide()
    del choices, dialog, tabs, preferences, undo_button, redo_button, history_item, text_probe, text_component, cleanup_button, cleanup_dialog, apply_button, window, engine


def test_invalid_date_is_reported(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.editor.setTimeSpan(pkg.key(dossier), "entstehungszeitraum", "2001-02", "")
    assert opened.messages and not opened.dirty


def test_metadata_history_survives_save_close_reopen(opened, sip_dir):
    backend = opened
    pkg = backend.package
    dossier = next(pkg.iter_kind("dossier"))
    backend.editor.setField(pkg.key(dossier), "titel", "Preserved title")
    assert backend.save()
    assert backend.changesTable.total == 0
    rows = backend.historyTable.records()
    assert any(row["eventType"] == "metadata modification" and row["newValue"] == "Preserved title" for row in rows)
    count = backend.historyTable.total
    backend.closePackage()
    backend.openPackage(QUrl.fromLocalFile(str(sip_dir)), False)
    assert backend.historyTable.total == count


def test_history_filters_preserve_records_and_reapply_after_refresh(opened):
    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "HistoryFilterToken")
    assert opened.save()
    all_records = opened.historyTable.records()

    opened.setHistoryEventFilter("metadata modification")
    opened.setHistoryOutcomeFilter("success")
    opened.setHistorySearch("historyfiltertoken")
    visible = opened.historyTable.visible_records()
    assert len(visible) == 1
    assert visible[0]["newValue"] == "HistoryFilterToken"
    assert opened.historyTable.records() == all_records

    opened._refresh_history()
    assert len(opened.historyTable.visible_records()) == 1
    opened.setHistorySearch("no matching event")
    assert opened.historyTable.visibleCount() == 0
    assert opened.historyTable.records() == all_records
    opened.setHistorySearch("")
    opened.setHistoryEventFilter("")
    opened.setHistoryOutcomeFilter("")


def test_history_details_summarize_deleted_metadata_and_files(opened):
    import json
    from pathlib import Path
    from ph_backend.audit import AuditJournal

    journal = AuditJournal(Path(opened.auditCompanion) / "journal.sqlite3")
    event = journal.append("package operation", agent_identifier="operator:test", software_version="0.1.0",
                           detail={"changes": [
                               {"path": "/paket/ablieferung/dossier[2]/@id",
                                "oldValue": "_dossier-2", "newValue": None},
                               {"path": "/paket/ablieferung/dossier[2]/titel/text()",
                                "oldValue": "Deleted dossier", "newValue": None},
                           ], "fileChanges": [
                               {"path": "content/deleted.pdf",
                                "before": {"type": "file", "size": 12, "sha256": "a" * 64},
                                "after": None},
                           ]})
    opened._refresh_history()
    row = next(index for index, record in enumerate(opened.historyTable.records())
               if record["eventIdentifier"] == event["payload"]["eventIdentifier"])

    details = json.loads(opened.historyDetails(row))
    assert details["deletedObjects"] == [
        {"kind": "dossier", "identifier": "_dossier-2", "label": "Deleted dossier",
         "path": "/paket/ablieferung/dossier[2]"},
        {"kind": "file", "label": "deleted.pdf", "path": "content/deleted.pdf"},
    ]
    assert {change["path"]: (change["before"], change["after"])
            for change in details["changeSummary"]} == {
                "/paket/ablieferung/dossier[2]/@id": ("_dossier-2", None),
                "/paket/ablieferung/dossier[2]/titel/text()": ("Deleted dossier", None),
                "content/deleted.pdf": ({"type": "file", "size": 12, "sha256": "a" * 64}, None),
            }


def test_native_history_export_offers_privacy_and_mets_choices(backend, app, sip_dir, tmp_path):
    from PySide6.QtCore import QMetaObject, QObject, QPointF, QUrl
    from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtTest import QTest
    from main import create_engine

    pkg = backend.openPackage(QUrl.fromLocalFile(str(sip_dir)), False)
    pkg = backend.package
    assert not backend.dirty
    backend.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Export UI event")
    assert backend.save()
    QQuickStyle.setStyle("Fusion")
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
    engine = create_engine(backend)
    window = engine.rootObjects()[0]
    window.setWidth(1280)
    window.setHeight(800)
    window.show()
    assert QTest.qWaitForWindowExposed(window, 2000)

    tabs = window.findChild(QObject, "actionTabs")
    tabs.setProperty("currentIndex", 5)
    app.processEvents()
    export_button = window.findChild(QObject, "preservationExportButton")
    assert export_button is not None and export_button.property("enabled")
    assert QMetaObject.invokeMethod(export_button, "clicked")
    app.processEvents()

    dialog = window.findChild(QObject, "auditExportDialog")
    assert dialog is not None and dialog.property("visible")
    full_choice = window.findChild(QObject, "fullPremisChoice")
    redacted_choice = window.findChild(QObject, "redactedPremisChoice")
    mets_version = window.findChild(QObject, "metsVersionChoice")
    assert full_choice.property("checked")
    assert not redacted_choice.property("checked")
    assert mets_version.property("count") == 2
    assert mets_version.property("currentIndex") == 0
    for theme in ("light", "dark"):
        backend.themeMode = theme
        for width in (1280, 980):
            window.setWidth(width)
            QTest.qWait(50)
            label = redacted_choice.property("contentItem")
            assert label.property("lineCount") > 1
            assert not label.property("truncated")
            assert label.property("paintedWidth") <= label.width()
            assert label.property("paintedHeight") <= label.height()
            background = dialog.property("background")
            left = background.mapToScene(QPointF(0, 0)).x()
            right = left + background.width()
            for name in ("fullPremisChoice", "redactedPremisChoice", "metsVersionChoice",
                         "exportPremisOnlyButton", "exportSipMetsButton"):
                control = window.findChild(QObject, name)
                control_left = control.mapToScene(QPointF(0, 0)).x()
                assert left <= control_left and control_left + control.width() <= right, (theme, width, name)
            assert window.grabWindow().save(str(tmp_path / f"export-{theme}-{width}.png"))
    backend.themeMode = "system"
    redacted_choice.setProperty("checked", True)
    mets_version.setProperty("currentIndex", 1)
    assert redacted_choice.property("checked")
    assert mets_version.property("currentText") == "METS 1.12.1"

    premis_button = window.findChild(QObject, "exportPremisOnlyButton")
    assert QMetaObject.invokeMethod(premis_button, "clicked")
    app.processEvents()
    premis_file_dialog = window.findChild(QObject, "auditPremisFileDialog")
    assert window.property("auditExportRedacted")
    assert premis_file_dialog.property("visible")
    premis_file_dialog.close()
    app.processEvents()

    assert QMetaObject.invokeMethod(export_button, "clicked")
    app.processEvents()
    dialog = window.findChild(QObject, "auditExportDialog")
    mets_version = window.findChild(QObject, "metsVersionChoice")
    mets_version.setProperty("currentIndex", 1)
    bundle_button = window.findChild(QObject, "exportSipMetsButton")
    assert QMetaObject.invokeMethod(bundle_button, "clicked")
    app.processEvents()
    bundle_folder_dialog = window.findChild(QObject, "auditBundleFolderDialog")
    assert window.property("auditExportMetsVersion") == "1.12.1"
    assert bundle_folder_dialog.property("visible")
    bundle_folder_dialog.close()
    app.processEvents()
    QMetaObject.invokeMethod(dialog, "close")
    window.close()
    engine.deleteLater()


@pytest.mark.parametrize("redact_values", [False, True])
def test_premis_export_ui_backend_respects_privacy_choice(opened, tmp_path, redact_values):
    import xml.etree.ElementTree as ET
    from pathlib import Path

    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Private export detail")
    assert opened.save()
    journal_path = Path(opened.auditCompanion) / "journal.sqlite3"
    from ph_backend.audit import AuditJournal

    journal_before = AuditJournal(journal_path, read_only=True).records()
    destination = tmp_path / ("redacted.xml" if redact_values else "full.xml")

    opened.exportPremis(QUrl.fromLocalFile(str(destination)), redact_values)

    xml = destination.read_bytes()
    premis_root = ET.fromstring(xml)
    assert (b"Private export detail" in xml) is not redact_values
    assert len(premis_root.findall("{http://www.loc.gov/premis/v3}event")) == len(journal_before)
    journal_after = AuditJournal(journal_path, read_only=True).records()
    assert journal_after[-1]["payload"]["eventType"] == "preservation export"
    assert journal_after[-1]["payload"]["detail"]["sourceSequence"] == len(journal_before)
    assert journal_after[-1]["payload"]["detail"]["redacted"] is redact_values


def test_premis_export_refuses_dirty_or_in_package_destination(opened, tmp_path):
    pkg = opened.package
    destination = tmp_path / "premis.xml"
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Unsaved change")
    opened.exportPremis(QUrl.fromLocalFile(str(destination)), False)
    assert not destination.exists()
    assert any("speichern" in text.lower() for _, text in opened.messages)

    assert opened.save()
    inside_sip = pkg.root_dir / "premis.xml"
    opened.exportPremis(QUrl.fromLocalFile(str(inside_sip)), False)
    assert not inside_sip.exists()
    assert any("SIP" in text for _, text in opened.messages)


@pytest.mark.parametrize(("redact_values", "mets_version"), [(False, "2"), (True, "1.12.1")])
def test_audit_bundle_export_hashes_actual_zip_and_references_sidecars(
        opened, tmp_path, redact_values, mets_version):
    import hashlib
    import xml.etree.ElementTree as ET
    import zipfile
    from pathlib import Path
    from ph_backend.audit import AuditJournal

    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Private bundle detail")
    assert opened.save()
    destination = tmp_path / "exports"
    destination.mkdir()

    opened.exportAuditBundle(QUrl.fromLocalFile(str(destination)), redact_values, mets_version)

    bundle = destination / f"{pkg.name}.package-turbo-export"
    archive = bundle / f"{pkg.name}.zip"
    premis = bundle / f"{pkg.name}.premis.xml"
    mets = ET.parse(bundle / f"{pkg.name}.mets.xml").getroot()
    premis_root = ET.parse(premis).getroot()
    archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.is_file() and premis.is_file()
    with zipfile.ZipFile(archive) as sip:
        assert f"{pkg.name}/header/metadata.xml" in sip.namelist()
    sip_file = next(element for element in mets.iter() if element.tag.endswith("}file") and element.get("ID") == "sip")
    md_reference = next(element for element in mets.iter() if element.tag.endswith("}mdRef"))
    location = next(element for element in mets.iter() if element.tag.endswith("}FLocat"))
    assert sip_file.get("CHECKSUM") == archive_digest
    assert md_reference.get("CHECKSUM") == hashlib.sha256(premis.read_bytes()).hexdigest()
    assert location.get("LOCREF") == archive.name or location.get("{http://www.w3.org/1999/xlink}href") == archive.name
    assert "has part" in [element.text for element in premis_root.iter()
                           if element.tag.endswith("}relationshipSubType")]
    assert (b"Private bundle detail" in premis.read_bytes()) is not redact_values
    journal = AuditJournal(Path(opened.auditCompanion) / "journal.sqlite3", read_only=True)
    events = journal.records()
    export_event = events[-1]["payload"]
    assert export_event["eventType"] == "preservation export"
    assert export_event["detail"]["sourceSequence"] == len(events) - 1
    assert export_event["detail"]["sipSha256"] == archive_digest
    assert export_event["detail"]["metsVersion"] == mets_version
    assert export_event["detail"]["redacted"] is redact_values
    assert len(premis_root.findall("{http://www.loc.gov/premis/v3}event")) == len(events) - 1


def test_premis_export_links_deleted_sip_entity_by_stable_id(opened):
    import hashlib
    from pathlib import Path
    from lxml import etree
    from ph_backend.audit import AuditJournal, PREMIS_NS

    pkg = opened.package
    dossier = list(pkg.iter_kind("dossier"))[-1]
    identifier = dossier.get("id")
    opened.stage_file_operation(lambda package: package.remove(dossier))
    assert opened.save()

    journal = AuditJournal(Path(opened.auditCompanion) / "journal.sqlite3", read_only=True)
    root = etree.fromstring(journal.premis_xml())
    expected = "urn:package-turbo:xml:" + hashlib.sha256(
        (journal.package_identifier + "\0xml\0id:" + identifier).encode("utf-8")).hexdigest()
    namespaces = {"p": PREMIS_NS}
    object_ids = root.xpath("p:object/p:objectIdentifier/p:objectIdentifierValue/text()", namespaces=namespaces)
    source_links = root.xpath("p:event/p:linkingObjectIdentifier[p:linkingObjectRole='source']"
                              "/p:linkingObjectIdentifierValue/text()", namespaces=namespaces)
    assert expected in object_ids and expected in source_links
    assert b"/dossier[" not in journal.premis_xml(redact_values=True)


def test_missing_audit_operator_blocks_edit_without_creating_companion(opened):
    from pathlib import Path

    opened.auditOperator = ""
    required = []
    opened.auditOperatorRequired.connect(lambda: required.append(True))
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    before = pkg.text(dossier, "titel")
    opened.editor.setField(pkg.key(dossier), "titel", "Unaudited")
    assert pkg.text(dossier, "titel") == before
    assert not opened.dirty and required
    assert not Path(opened.auditCompanion).exists()


def test_external_edit_before_first_application_edit_is_blocked(opened):
    pkg = opened.package
    original = pkg.metadata_path.read_bytes()
    pkg.metadata_path.write_bytes(original.replace(b"Testamt", b"External office"))
    dossier = next(pkg.iter_kind("dossier"))
    old = pkg.text(dossier, "titel")
    opened.editor.setField(pkg.key(dossier), "titel", "Stale overwrite")
    assert pkg.text(dossier, "titel") == old
    assert not opened.dirty and opened.messages


def test_discard_is_documented_without_saving(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    old = pkg.text(dossier, "titel")
    opened.editor.setField(pkg.key(dossier), "titel", "Discarded title")
    assert opened.discardChanges()
    assert not opened.dirty
    assert opened.package.text(next(opened.package.iter_kind("dossier")), "titel") == old
    assert any(row["outcome"] == "discarded" for row in opened.historyTable.records())


def test_read_only_reopen_reads_history_without_writing(opened, sip_dir):
    from pathlib import Path

    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Read-only history")
    assert opened.save()
    path = Path(opened.auditCompanion) / "journal.sqlite3"
    before = path.read_bytes()
    opened.closePackage()
    opened.openPackage(QUrl.fromLocalFile(str(sip_dir)), True)
    assert opened.hasHistory
    assert path.read_bytes() == before


def test_failed_audit_completion_keeps_dirty_and_can_recover(opened, monkeypatch):
    from ph_backend.audit import AuditError

    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.editor.setField(pkg.key(dossier), "titel", "Recovered application edit")
    workspace = opened._file_workspace
    finish = workspace._finish

    def fail(*args, **kwargs):
        raise AuditError("Injected completion error")

    monkeypatch.setattr(workspace, "_finish", fail)
    assert not opened.save()
    assert opened.dirty and opened.changesTable.total == 1
    assert not opened.discardChanges()
    monkeypatch.setattr(workspace, "_finish", finish)
    assert opened.recoverMetadata()
    assert not opened.dirty
    assert opened.package.text(next(opened.package.iter_kind("dossier")), "titel") == "Recovered application edit"
    assert any(row["eventType"] == "package commit recovery" for row in opened.historyTable.records())


def test_busy_validation_blocks_metadata_edits(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    old = pkg.text(dossier, "titel")
    opened._set_busy(True)
    try:
        opened.editor.setField(pkg.key(dossier), "titel", "Concurrent edit")
        assert pkg.text(dossier, "titel") == old
        assert not opened.dirty
    finally:
        opened._set_busy(False)


def test_package_metadata_undo_redo_and_audit_link(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    original = pkg.text(dossier, "titel")
    opened.editor.setField(pkg.key(dossier), "titel", "Undoable title")
    assert opened.canUndo and not opened.canRedo
    operation = opened._pending_audit[-1]["detail"]["operationIdentifier"]
    assert opened.undo()
    assert opened.package.text(next(opened.package.iter_kind("dossier")), "titel") == original
    assert opened.canRedo
    assert opened.redo()
    assert opened.package.text(next(opened.package.iter_kind("dossier")), "titel") == "Undoable title"
    assert opened.save()
    records = opened._workspace.journal.records()
    reversals = [record["payload"] for record in records if record["payload"]["eventType"] in ("undo", "redo")]
    assert [event["eventType"] for event in reversals] == ["undo", "redo"]
    assert all(event["detail"]["reversesOperationIdentifier"] == operation for event in reversals)


def test_undo_after_save_stages_reversal_until_saved(opened, sip_dir):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    original = pkg.text(dossier, "titel")
    opened.editor.setField(pkg.key(dossier), "titel", "Committed undo title")
    assert opened.save()
    saved = pkg.metadata_path.read_bytes()
    assert opened.undo()
    assert pkg.metadata_path.read_bytes() == saved
    assert pkg.text(next(pkg.iter_kind("dossier")), "titel") == original
    assert opened.save()
    assert b"Committed undo title" not in pkg.metadata_path.read_bytes()


def test_file_import_undo_redo(opened, tmp_path):
    pkg = opened.package
    content = next(element for element in pkg.iter_kind("ordner") if pkg.text(element, "name") == "content")
    source = tmp_path / "undo-file.txt"
    source.write_bytes(b"undo bytes")
    FileController(opened).importUrls(pkg.key(content), [QUrl.fromLocalFile(str(source)).toString()], True, False)
    assert (pkg.file_root / "content/undo-file.txt").is_file()
    assert opened.undo()
    assert not (pkg.file_root / "content/undo-file.txt").exists()
    assert opened.redo()
    assert (pkg.file_root / "content/undo-file.txt").read_bytes() == b"undo bytes"


def test_new_edit_abandons_redo_without_erasing_audit(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.editor.setField(pkg.key(dossier), "titel", "First title")
    assert opened.undo()
    dossier = next(pkg.iter_kind("dossier"))
    opened.editor.setField(pkg.key(dossier), "titel", "Branch title")
    assert not opened.canRedo
    assert any(event["event_type"] == "undo" for event in opened._pending_audit)


def test_noop_operation_creates_no_undo_or_staged_draft(opened):
    pkg = opened.package
    assert opened.stage_file_operation(lambda package: None) is None
    assert not opened.canUndo and not opened.dirty
    assert pkg.file_root == pkg.root_dir


def test_noop_rename_does_not_mark_package_dirty(opened):
    pkg = opened.package
    file_element = pkg.file_by_id("_file1")
    FileController(opened).rename(pkg.key(file_element), pkg.text(file_element, "name"))
    assert not opened.dirty and not opened.canUndo
    assert pkg.file_root == pkg.root_dir


def test_undo_restores_deleted_file_and_references(opened):
    pkg = opened.package
    file_element = pkg.file_by_id("_file1")
    original = pkg.fs_path(file_element).read_bytes()
    FileController(opened).deleteEntries([pkg.key(file_element)])
    assert pkg.file_by_id("_file1") is None
    assert opened.undo()
    restored = pkg.file_by_id("_file1")
    assert pkg.fs_path(restored).read_bytes() == original
    assert "_file1" in pkg.referenced_ids()
    assert opened.redo()
    assert pkg.file_by_id("_file1") is None


def test_undo_structure_and_notes(opened):
    pkg = opened.package
    position = next(pkg.iter_kind("ordnungssystemposition"))
    before = len(list(pkg.iter_kind("dossier")))
    StructureController(opened).addObjects(pkg.key(position), "dossier", 1)
    assert len(list(pkg.iter_kind("dossier"))) == before + 1
    assert opened.undo()
    assert len(list(pkg.iter_kind("dossier"))) == before
    dossier = next(pkg.iter_kind("dossier"))
    NoteController(opened).addNote([pkg.key(dossier)], "undo this note")
    assert opened.notesTable.total == 1
    assert opened.undo()
    assert opened.notesTable.total == 0


def test_undo_rejects_snapshot_tampering_and_external_changes(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.editor.setField(pkg.key(dossier), "titel", "Protected title")
    entry = opened._undo_history.entries[-1]
    (entry.before.directory / "header/metadata.xml").chmod(0o600)
    (entry.before.directory / "header/metadata.xml").write_bytes(b"tampered")
    assert not opened.undo()
    assert pkg.text(next(pkg.iter_kind("dossier")), "titel") == "Protected title"
    pkg.metadata_path.write_bytes(b"external metadata")
    assert not opened.undo()


def test_after_snapshot_failure_rolls_back_operation(opened, monkeypatch):
    from ph_backend.audit import AuditError

    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.editor.setField(pkg.key(dossier), "titel", "Earlier edit")
    history = opened._undo_history
    capture = history.capture
    calls = []

    def fail_after(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise AuditError("Injected after-snapshot failure")
        return capture(*args, **kwargs)

    monkeypatch.setattr(history, "capture", fail_after)
    opened.editor.setField(pkg.key(dossier), "titel", "Must roll back")
    assert pkg.text(next(pkg.iter_kind("dossier")), "titel") == "Earlier edit"
    assert len(history.entries) == 1
    assert opened.changesTable.total == 1


def test_busy_and_read_only_disable_undo(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.editor.setField(pkg.key(dossier), "titel", "Before busy")
    opened._set_busy(True)
    assert not opened.canUndo and not opened.undo()
    opened._set_busy(False)
    pkg.read_only = True
    assert not opened.canUndo and not opened.undo()


def test_clear_undo_keeps_preservation_events(opened):
    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Keep events")
    assert opened.save()
    records = opened._workspace.journal.records()
    opened.clearUndoHistory()
    assert not opened.canUndo and not opened.canRedo
    assert opened._workspace.journal.records() == records


def test_session_shutdown_clears_undo_but_retains_draft_and_journal(opened):
    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Recoverable draft")
    directory = opened._undo_history.directory
    before = opened._workspace.journal.records()
    stage = pkg.file_root
    opened.shutdown()
    assert not directory.exists()
    assert stage.exists()
    assert opened._workspace.journal.records() == before


def test_switch_package_clears_undo_state(opened, sip_dir):
    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Session only")
    assert opened.canUndo
    assert opened.discardChanges()
    assert not opened.canUndo and not opened.canRedo


def test_draft_persists_operation_provenance_before_field_signal(opened):
    import json
    from datetime import datetime, timezone

    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.stage_file_operation(lambda package: package.set_text(dossier, "titel", "Before signal"))
    with opened._workspace.journal._connection("ro") as connection:
        events = json.loads(connection.execute("SELECT events FROM package_draft WHERE id=1").fetchone()[0])
    assert events[-1]["event_type"] == "package operation"
    assert events[-1]["detail"]["operationIdentifier"]
    stamp = datetime.fromisoformat(events[-1]["detail"]["operationDateTime"])
    assert stamp.utcoffset() == timezone.utc.utcoffset(stamp)
    assert any(change["newValue"] == "Before signal" for change in events[-1]["detail"]["xmlChanges"])


def test_undo_keeps_selected_xml_object(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    identifier = dossier.get("id")
    opened.select(pkg.key(dossier))
    opened.editor.setField(pkg.key(dossier), "titel", "Keep selection")
    assert opened.undo()
    selected = pkg.element(opened.editor.currentKey)
    assert selected is not None and selected.get("id") == identifier


def test_undo_invalidates_previous_full_validation(opened):
    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Validate then undo")
    opened.validate(True)
    opened._worker.wait()
    QGuiApplication.processEvents()
    assert opened._had_full_run
    assert opened.undo()
    assert not opened._had_full_run and opened._full_issues == []


def test_gui_remains_responsive_during_snapshot_copy(opened, app, monkeypatch):
    import threading
    from PySide6.QtCore import QThread, QTimer
    import ph_backend.processing as processing

    entered = threading.Event()
    released = threading.Event()
    observed = []
    copy_bytes = processing._copy_bytes

    def copy_with_barrier(*args, **kwargs):
        assert QThread.currentThread() != app.thread()
        if not entered.is_set():
            entered.set()
            assert released.wait(3)
        return copy_bytes(*args, **kwargs)

    def heartbeat():
        if entered.is_set():
            observed.append((QThread.currentThread() == app.thread(), opened.busy))
            released.set()

    monkeypatch.setattr(processing, "_copy_bytes", copy_with_barrier)
    timer = QTimer()
    timer.setInterval(1)
    timer.timeout.connect(heartbeat)
    timer.start()
    try:
        pkg = opened.package
        opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Responsive edit")
    finally:
        timer.stop()
        released.set()
    assert observed and all(gui and busy for gui, busy in observed)
    assert opened.dirty and not opened.busy


def test_cancel_copy_is_nonblocking_and_preserves_original(opened, monkeypatch):
    import threading
    import time
    from PySide6.QtCore import QTimer
    import ph_backend.processing as processing
    from ph_backend.file_workspace import manifest

    pkg = opened.package
    before = manifest(pkg.root_dir)
    entered, released = threading.Event(), threading.Event()
    copy_bytes = processing._copy_bytes
    timings = []

    def copy_with_barrier(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert released.wait(3)
        return copy_bytes(*args, **kwargs)

    def cancel():
        if entered.is_set() and not released.is_set():
            start = time.monotonic()
            opened.cancelTask()
            timings.append(time.monotonic() - start)
            released.set()

    monkeypatch.setattr(processing, "_copy_bytes", copy_with_barrier)
    timer = QTimer()
    timer.setInterval(1)
    timer.timeout.connect(cancel)
    timer.start()
    try:
        content = next(element for element in pkg.iter_kind("ordner") if pkg.text(element, "name") == "content")
        FileController(opened).newFolder(pkg.key(content), "CancelledFolder")
    finally:
        timer.stop()
        released.set()
    assert timings and max(timings) < 0.5
    assert manifest(pkg.root_dir) == before
    assert not opened.dirty and not opened.canUndo and not opened.busy
    assert not (pkg.root_dir / "content/CancelledFolder").exists()


def test_prepared_commit_rejects_gui_cancellation(opened, monkeypatch):
    from ph_backend.processing import current_control

    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Protected commit")
    workspace = opened._file_workspace
    finish = workspace._finish
    observed = []

    def protected_finish(*args, **kwargs):
        control = current_control()
        observed.append((opened.canCancelTask, control.cancel()))
        return finish(*args, **kwargs)

    monkeypatch.setattr(workspace, "_finish", protected_finish)
    assert opened.save()
    assert observed == [(False, False)]
    assert b"Protected commit" in pkg.metadata_path.read_bytes()


def test_worker_events_cannot_reenter_package_mutations(opened, monkeypatch):
    from PySide6.QtCore import QTimer
    import ph_backend.processing as processing
    import threading

    entered, released = threading.Event(), threading.Event()
    copy_bytes = processing._copy_bytes
    results = []

    def copy_with_barrier(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            assert released.wait(3)
        return copy_bytes(*args, **kwargs)

    def reenter():
        if entered.is_set() and not released.is_set():
            results.append(opened.save())
            results.append(opened.set_package(None))
            opened.closePackage()
            released.set()

    monkeypatch.setattr(processing, "_copy_bytes", copy_with_barrier)
    timer = QTimer()
    timer.setInterval(1)
    timer.timeout.connect(reenter)
    timer.start()
    try:
        pkg = opened.package
        opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Guarded edit")
    finally:
        timer.stop()
        released.set()
    assert results == [False, False] and opened.package is pkg


def test_cancel_before_metadata_edit_has_no_failure_dialog(opened, monkeypatch):
    import ph_backend.processing as processing

    read = processing.read_bytes

    def cancel_read(path):
        processing.current_control().cancel()
        return read(path)

    monkeypatch.setattr("ph_backend.backend.read_bytes", cancel_read)
    pkg = opened.package
    old = pkg.text(next(pkg.iter_kind("dossier")), "titel")
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Cancelled edit")
    assert not opened.messages and not opened.dirty
    assert pkg.text(next(pkg.iter_kind("dossier")), "titel") == old


def test_stale_package_object_is_not_published(opened, tmp_path):
    from ph_backend.package_factory import create_package

    current = opened.package
    stale = create_package(tmp_path, "SIP_20261105_Test_Stale", "Test")
    data = stale.metadata_path.read_bytes()
    stale.metadata_path.write_bytes(data.replace(b"<ablieferndeStelle>Test", b"<ablieferndeStelle>External"))
    assert not opened.set_package(stale)
    assert opened.package is current


def test_validation_uses_isolated_xml_and_maps_issue_keys(opened):
    pkg = opened.package
    opened.validate(True)
    worker = opened._worker
    worker.wait()
    assert worker._validator.pkg.root is not pkg.root
    QGuiApplication.processEvents()
    issues = opened.validationTable.records()
    assert any(issue["key"] for issue in issues)
    assert all(not issue["key"] or pkg.element(issue["key"]) is not None for issue in issues)


def test_validation_event_records_only_summary_and_snapshot_hash(opened):
    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Sensitive validation title")
    assert opened.save()

    opened.validate(True)
    worker = opened._worker
    worker.wait()
    QGuiApplication.processEvents()

    event = next(row for row in opened.historyTable.records() if row["eventType"] == "validation")
    detail = event["detail"]
    assert detail["scope"] == "package-validation" and detail["mode"] == "full"
    assert len(detail["metadataSha256"]) == 64
    assert isinstance(detail["issueCounts"], dict)
    assert "Sensitive validation title" not in str(detail)


def test_read_only_validation_is_recorded_only_in_external_companion(opened, sip_dir):
    from pathlib import Path

    pkg = opened.package
    opened.editor.setField(pkg.key(next(pkg.iter_kind("dossier"))), "titel", "Saved before validation")
    assert opened.save()
    metadata_before = pkg.metadata_path.read_bytes()
    companion = Path(opened.auditCompanion)
    opened.closePackage()
    opened.openPackage(QUrl.fromLocalFile(str(sip_dir)), True)
    journal_path = companion / "journal.sqlite3"
    journal_before = journal_path.read_bytes()

    opened.validate(True)
    worker = opened._worker
    worker.wait()
    QGuiApplication.processEvents()

    assert (sip_dir / "header" / "metadata.xml").read_bytes() == metadata_before
    assert journal_path.read_bytes() != journal_before
    assert any(row["eventType"] == "validation" for row in opened.historyTable.records())


def test_validation_hash_cancellation_does_not_publish_success(opened, monkeypatch):
    import threading
    from PySide6.QtCore import QEventLoop, QTimer
    import ph_backend.processing as processing

    entered, released = threading.Event(), threading.Event()
    digest = processing.digest_file

    def blocked_digest(*args, **kwargs):
        entered.set()
        assert released.wait(3)
        return digest(*args, **kwargs)

    def cancel():
        if entered.is_set() and not released.is_set():
            opened.cancelTask()
            released.set()

    monkeypatch.setattr("ph_backend.sip.digest_file", blocked_digest)
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(1)
    timer.timeout.connect(cancel)
    timer.start()
    opened.validate(True)
    worker = opened._worker
    worker.finished.connect(loop.quit)
    try:
        loop.exec()
        QGuiApplication.processEvents()
    finally:
        timer.stop()
        released.set()
    assert not opened.busy and not opened._had_full_run
    assert entered.is_set() and worker.cancelled
    assert not opened.messages


def test_repeated_chunk_import_keeps_gui_alive_and_source_unchanged(opened, tmp_path):
    import hashlib
    from PySide6.QtCore import QTimer
    from ph_backend.file_workspace import manifest
    from ph_backend.processing import CHUNK_SIZE

    pkg = opened.package
    before = manifest(pkg.root_dir)
    source = tmp_path / "large.bin"
    block = b"x" * CHUNK_SIZE
    digest = hashlib.sha256()
    with source.open("wb") as stream:
        for index in range(16):
            stream.write(block)
            digest.update(block)
    heartbeats = []
    timer = QTimer()
    timer.setInterval(1)
    timer.timeout.connect(lambda: heartbeats.append(opened.busy))
    timer.start()
    try:
        content = next(element for element in pkg.iter_kind("ordner") if pkg.text(element, "name") == "content")
        FileController(opened).importUrls(pkg.key(content), [QUrl.fromLocalFile(str(source)).toString()], True, False)
    finally:
        timer.stop()
    assert len(heartbeats) > 2 and all(heartbeats)
    assert manifest(pkg.root_dir) == before
    staged = pkg.file_root / "content/large.bin"
    assert hashlib.sha256(staged.read_bytes()).hexdigest() == digest.hexdigest()
    assert opened.dirty and not opened.busy


def test_retention_settings_change_requires_new_preview(opened):
    assert opened.previewRetentionCleanup()
    opened.retentionAgeDays += 1
    assert not opened.applyRetentionCleanup()
    assert opened.messages


def test_read_only_session_cannot_apply_retention(opened):
    assert opened.previewRetentionCleanup()
    opened.package.read_only = True
    assert not opened.applyRetentionCleanup()


def test_repeated_values_and_reference_attributes_are_audited_and_undoable(opened, tmp_path):
    from ph_backend.package_factory import create_package
    from ph_backend import files, structure

    pkg = create_package(tmp_path, "SIP_20261105_Test_UndoFields", "Test")
    dossier = structure.add_objects(pkg, next(pkg.iter_kind("ordnungssystemposition")), "dossier")[0]
    document = structure.add_objects(pkg, dossier, "dokument")[0]
    pkg.set_repeated_texts(document, "autor", ["Before one", "Before two"])
    content = next(element for element in pkg.iter_kind("ordner") if pkg.text(element, "name") == "content")
    source = tmp_path / "audit-reference.txt"
    source.write_bytes(b"audit reference")
    files.import_paths(pkg, content, [source])
    structure.assign_files(pkg, document, pkg.children(content, "datei"))
    pkg.save()
    assert opened.set_package(pkg)
    original = pkg.metadata_path.read_bytes()
    opened.editor.setRepeatedField(pkg.key(document), "autor", ["After one", "After two"])
    opened.editor.setReferenceAttribute(pkg.key(document), 0, "version", "3")
    assert pkg.metadata_path.read_bytes() == original
    assert opened.undo()
    document = next(pkg.iter_kind("dokument"))
    assert pkg.children(document, "dateiRef")[0].get("version") is None
    assert opened.redo() and opened.save()
    events = opened._workspace.journal.records()
    from ph_backend import schema

    assert any(event["payload"]["detail"].get("field") == schema.label_for("dateiRef[1]/@version") for event in events)
    assert any(event["payload"]["detail"].get("field") == "Autor" for event in events)
    assert pkg.metadata_path.read_bytes() != original


def test_process_creation_controller_is_schema_gated(opened, tmp_path):
    from ph_backend.package_factory import create_package

    for version in ("1.0", "1.1", "1.2", "1.3"):
        pkg = create_package(tmp_path, "SIP_20261105_Test_Process" + version, "Test", version=version)
        assert opened.set_package(pkg)
        controller = StructureController(opened)
        dossier_key = controller.addObjects(pkg.key(next(pkg.iter_kind("ordnungssystemposition"))), "dossier", 1)
        allowed = controller.allowedChildren(dossier_key)
        assert ("vorgang" in allowed) is (version != "1.0")
        if version != "1.0":
            process_key = controller.addObjects(dossier_key, "vorgang", 1)
            assert process_key and "aktivitaet" in controller.allowedChildren(process_key)
            activity_key = controller.addObjects(process_key, "aktivitaet", 1)
            assert activity_key and opened.undo() and opened.redo()
        assert opened.discardChanges()


def test_editor_offers_choices_and_errors(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.select(pkg.key(dossier))
    fields = {f["tag"]: f for s in opened.editor.sections for f in s["primary"] + s["more"]}
    assert fields["erscheinungsform"]["type"] == "choice"
    assert "gemischt" in fields["erscheinungsform"]["choices"]
    assert fields["datenschutz"]["choices"] == ["", "true", "false"]
    assert fields["eroeffnungsdatum"]["type"] == "timepoint"
    opened.editor.setField(pkg.key(dossier), "titel", "Kurz")
    fields = {f["tag"]: f for s in opened.editor.sections for f in s["primary"]}
    assert "5 Zeichen" in fields["titel"]["error"]


def test_read_only_blocks_edits(backend, sip_dir):
    backend.openPackage(QUrl.fromLocalFile(str(sip_dir)), True)
    pkg = backend.package
    dossier = next(pkg.iter_kind("dossier"))
    backend.editor.setField(pkg.key(dossier), "titel", "x")
    assert not backend.dirty and not backend.save()
    StructureController(backend).deleteObjects([pkg.key(dossier)])
    assert next(pkg.iter_kind("dossier")) is dossier


def test_search_controller(opened):
    ctl = SearchController(opened)
    assert ctl.simpleSearch("bericht") >= 2
    assert opened.searchTable.columnLabels() == ["Objekt", "Objektname", "Metadatum", "Wert"]
    assert ctl.advancedSearch([{"kind": "dossier", "tag": "titel", "value": "leer"}]) == 1
    assert opened.searchTable.columnLabels()[-1] == "Titel"
    assert ctl.advancedSearch([{"kind": "dossier", "tag": "titel", "value": ""}]) == -1
    opened.sampleSize = 1
    ctl.drawSample()
    assert opened.sampleTable.total == 1


def test_structure_controller(opened):
    pkg = opened.package
    ctl = StructureController(opened)
    position = next(pkg.iter_kind("ordnungssystemposition"))
    assert "ordnungssystemposition" not in ctl.allowedChildren(pkg.key(position))
    key = ctl.addObjects(pkg.key(position), "dossier", 2)
    assert key and opened.dirty and opened.changesTable.total == 1
    new_dossier = pkg.element(key)
    file_el = pkg.file_by_id("_file2")
    assert ctl.assignFiles([pkg.key(file_el)], key) == 1
    ctl.cut([key])
    target = next(d for d in pkg.iter_kind("dossier") if pkg.text(d, "titel") == "Leer")
    ctl.paste(pkg.key(target))
    assert new_dossier.getparent() is target
    ctl.deleteObjects([key])
    assert new_dossier.getparent() is None
    ctl.renumber("decimal")
    assert pkg.text(position, "nummer") == "0"
    kinds = [k["kind"] for k in ctl.massEditKinds(pkg.key(pkg.classification_system))]
    assert "dossier" in kinds
    ctl.massEdit(pkg.key(pkg.classification_system), "dossier", "inhalt", "x", "")
    assert all(pkg.text(d, "inhalt") == "x" for d in pkg.iter_kind("dossier"))
    ctl.addObjects(pkg.key(position), "ordnungssystemposition", 1)
    assert opened.messages


def test_file_controller_and_fixes(opened, sip_dir, tmp_path):
    pkg = opened.package
    ctl = FileController(opened)
    content = next(o for o in pkg.iter_kind("ordner") if pkg.text(o, "name") == "content")
    source = tmp_path / "neu.pdf"
    source.write_bytes(b"%PDF-1.4")
    url = QUrl.fromLocalFile(str(source)).toString()
    assert ctl.importConflicts(pkg.key(content), [url]) == []
    ctl.importUrls(pkg.key(content), [url], True, False)
    assert not (sip_dir / "content" / "neu.pdf").exists() and opened.dirty
    assert (pkg.file_root / "content" / "neu.pdf").is_file()
    assert ctl.importConflicts(pkg.key(content), [url]) == ["neu.pdf"]
    assert opened.save()
    assert (sip_dir / "content" / "neu.pdf").is_file() and not opened.dirty

    (sip_dir / "content" / "d0001" / "p000001.pdf").write_bytes(b"new content")
    opened.validate(True)
    opened._worker.wait()
    QGuiApplication.processEvents()
    rows = [i for i, r in enumerate(opened.validationTable.visible_records()) if r["checkId"] == "checksum"]
    assert rows and ctl.fixActions(rows[0])[0]["id"] == "recompute_checksum"
    ctl.applyFix("recompute_checksum", rows)
    assert not [r for r in opened.validationTable.records() if r["checkId"] == "checksum"]
    assert opened.save()

    (sip_dir / "stray.txt").write_text("x")
    opened.validate(True)
    opened._worker.wait()
    QGuiApplication.processEvents()
    rows = [i for i, r in enumerate(opened.validationTable.visible_records()) if r["checkId"] == "illegal_entries"]
    ctl.applyFix("delete_fs", rows)
    assert (sip_dir / "stray.txt").exists()
    assert not (pkg.file_root / "stray.txt").exists()
    assert not [r for r in opened.validationTable.records() if r["checkId"] == "illegal_entries"]
    assert opened.save()
    assert not (sip_dir / "stray.txt").exists()


def test_staged_file_discard_preserves_original_bytes(opened):
    from ph_backend.file_workspace import manifest

    pkg = opened.package
    before = manifest(pkg.root_dir)
    file_el = pkg.file_by_id("_file1")
    FileController(opened).deleteEntries([pkg.key(file_el)])
    assert opened.dirty
    assert not pkg.fs_path(file_el)
    assert manifest(pkg.root_dir) == before
    assert opened.discardChanges()
    assert manifest(opened.package.root_dir) == before
    assert not opened.dirty


def test_saved_file_draft_can_be_resumed_after_restart(opened, backend, sip_dir, tmp_path):
    from ph_backend.backend import Backend

    pkg = opened.package
    content = next(element for element in pkg.iter_kind("ordner") if pkg.text(element, "name") == "content")
    FileController(opened).newFolder(pkg.key(content), "Resumable")
    assert not (sip_dir / "content/Resumable").exists()
    replacement = Backend(QSettings(str(tmp_path / "resumed.ini"), QSettings.Format.IniFormat))
    replacement.auditOperator = "resuming-operator"
    replacement.openPackage(QUrl.fromLocalFile(str(sip_dir)), False)
    assert replacement.recoverMetadata()
    assert replacement.dirty
    assert replacement.changesTable.total > 0
    assert (replacement.package.file_root / "content/Resumable").is_dir()
    assert replacement.save()
    assert (sip_dir / "content/Resumable").is_dir()


def test_failed_initial_file_operation_does_not_block_metadata_save(opened):
    pkg = opened.package
    dossier = next(pkg.iter_kind("dossier"))
    opened.editor.setField(pkg.key(dossier), "titel", "Keep earlier edit")
    content = next(element for element in pkg.iter_kind("ordner") if pkg.text(element, "name") == "content")
    FileController(opened).newFolder(pkg.key(content), "not&allowed")
    assert opened.messages
    assert opened.save()
    assert "Keep earlier edit" in pkg.metadata_path.read_text(encoding="utf-8")


def test_replacement_and_rename_are_staged_until_save(opened, sip_dir, tmp_path):
    pkg = opened.package
    file_el = pkg.file_by_id("_file1")
    source = tmp_path / "replacement.pdf"
    source.write_bytes(b"%PDF-1.4 replacement")
    original = sip_dir / "content/d0001/p000001.pdf"
    before = original.read_bytes()
    controller = FileController(opened)
    controller.replaceFile(pkg.key(file_el), QUrl.fromLocalFile(str(source)))
    controller.rename(pkg.key(file_el), "renamed.pdf")
    assert original.read_bytes() == before
    assert not (original.parent / "renamed.pdf").exists()
    assert pkg.fs_path(file_el).read_bytes() == source.read_bytes()
    assert opened.save()
    assert not original.exists()
    assert (original.parent / "renamed.pdf").read_bytes() == source.read_bytes()


def test_notes_controller(opened):
    pkg = opened.package
    ctl = NoteController(opened)
    dossier = next(pkg.iter_kind("dossier"))
    assert ctl.canHaveNotes(pkg.key(dossier))
    ctl.addNote([pkg.key(dossier)], "prüfen")
    assert opened.notesTable.total == 1
    note_key = opened.notesTable.recordAt(0)["noteKey"]
    ctl.editNote(note_key, "ok")
    assert opened.notesTable.recordAt(0)["comment"] == "ok"
    index = opened.classificationModel.indexOfKey(pkg.key(dossier))
    from ph_backend.navigators import NOTE_ROLE
    assert index.data(NOTE_ROLE) is True
    ctl.deleteNotes([note_key])
    assert opened.notesTable.total == 0


def test_package_controller(backend, tmp_path):
    ctl = PackageController(backend, [])
    name = ctl.suggestedName("Testamt", "R1")
    assert ctl.nameError(name) == "" and ctl.nameError("x y")
    assert ctl.createPackage(QUrl.fromLocalFile(str(tmp_path)), name, "Testamt", "GEVER", "", "Plan", QUrl())
    assert backend.hasPackage and backend.packageName == name
    ctl.savePerspective("Breit", {"left": 500, "bottom": 200})
    assert ctl.perspectives == ["Breit"] and ctl.perspective("Breit")["left"] == 500
    ctl.deletePerspective("Breit")
    assert ctl.perspectives == []


def test_accumulate_time_spans(opened):
    opened.accumulateTimeSpans()
    pkg = opened.package
    assert pkg.time_span(pkg.delivery, "entstehungszeitraum") == ("2007", "2008")
