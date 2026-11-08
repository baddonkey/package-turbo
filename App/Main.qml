import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtCore

ApplicationWindow {
    id: window

    width: 1500
    height: 950
    minimumWidth: 980
    minimumHeight: 680
    visible: true
    title: "Package Turbo" + (backend.hasPackage ? " \u2013 " + backend.packageName : "")
           + (backend.readOnly ? qsTr(" (schreibgeschützt)") : "") + (backend.dirty ? " *" : "")
        readonly property bool darkMode: backend.themeMode === "dark"
                            || (backend.themeMode === "system" && backend.systemTheme === "dark")
        readonly property color secondaryTextColor: darkMode ? "#a9bcb6" : "#586c66"
        readonly property color errorTextColor: darkMode ? "#ff9288" : "#b42318"
        readonly property color warningTextColor: darkMode ? "#ffc078" : "#a75b16"
        color: darkMode ? "#111a18" : "#f1f5f3"
        palette.window: darkMode ? "#111a18" : "#f1f5f3"
        palette.base: darkMode ? "#1a2724" : "#ffffff"
        palette.alternateBase: darkMode ? "#202f2b" : "#f7faf8"
        palette.active.text: darkMode ? "#e5eeeb" : "#1c2d2a"
        palette.inactive.text: darkMode ? "#e5eeeb" : "#1c2d2a"
        palette.active.windowText: darkMode ? "#e5eeeb" : "#1c2d2a"
        palette.inactive.windowText: darkMode ? "#e5eeeb" : "#1c2d2a"
        palette.disabled.text: darkMode ? "#82948e" : "#899791"
        palette.disabled.windowText: darkMode ? "#82948e" : "#899791"
        palette.disabled.buttonText: darkMode ? "#82948e" : "#899791"
        palette.button: darkMode ? "#293a35" : "#e4eeea"
        palette.active.buttonText: darkMode ? "#e6f1ed" : "#173e37"
        palette.inactive.buttonText: darkMode ? "#e6f1ed" : "#173e37"
        palette.highlight: darkMode ? "#39a99c" : "#16796f"
        palette.highlightedText: darkMode ? "#10201d" : "#ffffff"
        palette.brightText: errorTextColor
        palette.mid: darkMode ? "#40544e" : "#c6d5d0"
        palette.dark: darkMode ? "#0b1210" : "#71867f"
        palette.light: darkMode ? "#344640" : "#fbfdfc"
        palette.link: darkMode ? "#70d6c8" : "#126b63"
        palette.placeholderText: darkMode ? "#a9bcb6" : "#586c66"

    property var pendingAction: null
    property bool closeConfirmed: false
    property string exportTarget: ""
    property string reportTarget: ""
    property bool auditExportRedacted: false
    property string auditExportMetsVersion: "2"
    property string maximized: ""
    property var eventDetailData: ({})
    property bool showRawEventDetails: false

    readonly property var defaultLayout: ({ leftWidth: 460, classificationHeight: 420, actionsHeight: 300 })

    // ---------------------------------------------------------------- helpers

    function guarded(action) {
        if (backend.busy)
            return
        window.contentItem.forceActiveFocus()
        Qt.callLater(() => guardedReady(action))
    }

    function guardedReady(action) {
        if (backend.busy)
            return
        pendingAction = action
        if (backend.dirty)
            unsavedDialog.open()
        else
            proceedAfterSave()
    }

    function savePackage() {
        if (backend.busy)
            return
        window.contentItem.forceActiveFocus()
        Qt.callLater(() => backend.save())
    }

    function openNewPackageDialog() {
        if (backend.auditOperator.trim().length > 0) {
            newPackageDialog.open()
            return
        }
        inputDialog.ask(qsTr("Identität bestätigen"), qsTr("Erstellt durch"), "", name => {
            if (!name.trim())
                return
            backend.auditOperator = name.trim()
            newPackageDialog.open()
        })
    }

    function proceedAfterSave() {
        if (backend.hasPackage && backend.errorCount > 0 && !backend.readOnly)
            errorsOnCloseDialog.open()
        else
            runPending()
    }

    function runPending() {
        const action = pendingAction
        pendingAction = null
        if (action)
            action()
    }

    function revealInNavigators(key) {
        if (classificationNavigator.revealKey(key))
            return
        if (dossierNavigator.revealKey(key)) {
            navigatorTabs.currentIndex = 0
            return
        }
        if (packageNavigator.revealKey(key))
            navigatorTabs.currentIndex = 1
    }

    function toggleMaximized(pane) {
        maximized = maximized === pane ? "" : pane
    }

    function applyLayout(state) {
        maximized = ""
        leftPane.SplitView.preferredWidth = state.leftWidth || defaultLayout.leftWidth
        classificationNavigator.SplitView.preferredHeight = state.classificationHeight || defaultLayout.classificationHeight
        actionPane.SplitView.preferredHeight = state.actionsHeight || defaultLayout.actionsHeight
    }

    function currentLayout() {
        return { leftWidth: leftPane.width, classificationHeight: classificationNavigator.height,
                 actionsHeight: actionPane.height }
    }

    function askNote(keys) {
        inputDialog.ask(qsTr("Neue Notiz"), qsTr("Notiz zu %1 Objekt(en):").arg(keys.length), "",
                        text => notesCtl.addNote(keys, text), { multiline: true })
    }

    function showNotes(key) {
        actionTabs.currentIndex = 1
        notesView.highlightOwner(key)
    }

    function confirm(text, action) {
        confirmDialog.message = text
        confirmDialog.action = action
        confirmDialog.open()
    }

    function textTarget() {
        const item = window.activeFocusItem
        return item && typeof item.cut === "function" && typeof item.paste === "function" ? item : null
    }

    function auditValueText(value) {
        if (value === null || value === undefined)
            return qsTr("(leer)")
        return typeof value === "object" ? JSON.stringify(value) : String(value)
    }

    onClosing: function (close) {
        if (backend.busy) {
            close.accepted = false
            backend.cancelTask()
            return
        }
        layoutSettings.leftWidth = leftPane.width
        layoutSettings.classificationHeight = classificationNavigator.height
        layoutSettings.actionsHeight = actionPane.height
        if (closeConfirmed || !backend.hasPackage)
            return
        close.accepted = false
        guarded(function () { window.closeConfirmed = true; Qt.quit() })
    }

    Component.onCompleted: applyLayout({ leftWidth: layoutSettings.leftWidth,
                                         classificationHeight: layoutSettings.classificationHeight,
                                         actionsHeight: layoutSettings.actionsHeight })

    Settings {
        id: layoutSettings
        category: "layout"
        property real leftWidth: window.defaultLayout.leftWidth
        property real classificationHeight: window.defaultLayout.classificationHeight
        property real actionsHeight: window.defaultLayout.actionsHeight
    }

    Shortcut { sequence: "F1"; onActivated: packageCtl.openUserManual() }

    // ---------------------------------------------------------------- menus

    menuBar: MenuBar {
        Menu {
            id: packageMenu
            objectName: "packageMenu"
            title: qsTr("&Paket")
            width: Math.min(window.width - 24, Math.max(implicitWidth, 300,
                ...backend.recentPackages.map((path, index) => packageMenuFontMetrics.advanceWidth(
                    (index + 1) + "  " + path.replace(/[\\/]+$/, "").split(/[\\/]/).pop()) + 24)))
            FontMetrics { id: packageMenuFontMetrics; font: packageMenu.font }
            Action { text: qsTr("Neues Paket erstellen..."); shortcut: StandardKey.New; onTriggered: guarded(() => window.openNewPackageDialog()) }
            Action { text: qsTr("Paket öffnen..."); shortcut: StandardKey.Open; onTriggered: guarded(() => { openFolderDialog.readOnly = false; openFolderDialog.open() }) }
            Action { text: qsTr("Paket schreibgeschützt öffnen..."); onTriggered: guarded(() => { openFolderDialog.readOnly = true; openFolderDialog.open() }) }
            Action { text: qsTr("metadata.xml öffnen..."); onTriggered: guarded(() => openMetadataDialog.open()) }
            MenuSeparator {}
            Action { text: qsTr("Speichern"); shortcut: StandardKey.Save; enabled: backend.hasPackage && !backend.readOnly && !backend.busy; onTriggered: window.savePackage() }
            Action { text: qsTr("Paket zippen..."); enabled: backend.hasSip; onTriggered: zipDialog.open() }
            Action { text: qsTr("metadata.xml exportieren..."); enabled: backend.hasPackage; onTriggered: exportXmlDialog.open() }
            Action {
                text: qsTr("PREMIS/METS exportieren...")
                enabled: backend.hasSip && backend.hasHistory && !backend.busy && !backend.dirty
                onTriggered: auditExportDialog.open()
            }
            MenuSeparator {}
            Menu {
                id: reportsSubMenu
                title: qsTr("Reports")
                enabled: backend.hasPackage
                Instantiator {
                    model: packageCtl.reportTypes
                    delegate: MenuItem {
                        required property var modelData
                        text: modelData.label + "..."
                        onTriggered: { window.reportTarget = modelData.id; reportDialog.open() }
                    }
                    onObjectAdded: function (index, object) { reportsSubMenu.insertItem(index, object) }
                    onObjectRemoved: function (index, object) { reportsSubMenu.removeItem(object) }
                }
            }
            MenuSeparator {}
            Action { text: qsTr("Paket schliessen"); shortcut: StandardKey.Close; enabled: backend.hasPackage; onTriggered: guarded(() => backend.closePackage()) }
            MenuSeparator {}
            Instantiator {
                model: backend.recentPackages
                delegate: MenuItem {
                    required property var modelData
                    required property int index
                    objectName: "recentPackage-" + index
                    text: (index + 1) + "  " + modelData.replace(/[\\/]+$/, "").split(/[\\/]/).pop()
                    contentItem: Label {
                        text: parent.text
                        font: parent.font
                        color: parent.highlighted ? parent.palette.highlightedText : parent.palette.text
                        wrapMode: Text.WrapAnywhere
                        verticalAlignment: Text.AlignVCenter
                    }
                    ToolTip.visible: hovered
                    ToolTip.text: modelData
                    onTriggered: { const path = modelData; guarded(() => backend.openRecent(path)) }
                }
                // Recent packages follow the separator after "Paket schliessen" (item 12).
                onObjectAdded: function (index, object) { packageMenu.insertItem(13 + index, object) }
                onObjectRemoved: function (index, object) { packageMenu.removeItem(object) }
            }
            MenuSeparator {}
            Action { text: qsTr("Beenden"); shortcut: StandardKey.Quit; onTriggered: window.close() }
        }
        Menu {
            title: qsTr("&Bearbeiten")
            Action {
                id: undoAction
                objectName: "undoAction"
                text: qsTr("Rückgängig")
                shortcut: StandardKey.Undo
                enabled: backend.canUndo || !!(window.textTarget() && window.textTarget().canUndo)
                onTriggered: {
                    const target = window.textTarget()
                    if (target && target.canUndo)
                        target.undo()
                    else
                        backend.undo()
                }
            }
            Action {
                id: redoAction
                objectName: "redoAction"
                text: qsTr("Wiederholen")
                shortcut: StandardKey.Redo
                enabled: backend.canRedo || !!(window.textTarget() && window.textTarget().canRedo)
                onTriggered: {
                    const target = window.textTarget()
                    if (target && target.canRedo)
                        target.redo()
                    else
                        backend.redo()
                }
            }
            Action {
                text: qsTr("Paket-Verlauf leeren...")
                enabled: backend.canUndo || backend.canRedo
                onTriggered: window.confirm(qsTr("Undo/Redo-Schnappschüsse für dieses Paket entfernen?"), () => backend.clearUndoHistory())
            }
            MenuSeparator {}
            Action { text: qsTr("Ausschneiden"); shortcut: StandardKey.Cut; onTriggered: { const t = window.textTarget(); if (t) t.cut() } }
            Action { text: qsTr("Kopieren"); shortcut: StandardKey.Copy; onTriggered: { const t = window.textTarget(); if (t) t.copy() } }
            Action { text: qsTr("Einfügen"); shortcut: StandardKey.Paste; onTriggered: { const t = window.textTarget(); if (t) t.paste() } }
        }
        Menu {
            id: viewMenu
            title: qsTr("&Ansicht")
            Action { text: qsTr("Perspektive speichern als..."); onTriggered: inputDialog.ask(qsTr("Perspektive speichern"), qsTr("Name"), "", name => packageCtl.savePerspective(name, window.currentLayout())) }
            Menu {
                id: perspectiveMenu
                title: qsTr("Perspektive öffnen")
                enabled: packageCtl.perspectives.length > 0
                Instantiator {
                    model: packageCtl.perspectives
                    delegate: MenuItem {
                        required property var modelData
                        text: modelData
                        onTriggered: window.applyLayout(packageCtl.perspective(modelData))
                    }
                    onObjectAdded: function (index, object) { perspectiveMenu.insertItem(index, object) }
                    onObjectRemoved: function (index, object) { perspectiveMenu.removeItem(object) }
                }
            }
            Menu {
                id: perspectiveDeleteMenu
                title: qsTr("Perspektive löschen")
                enabled: packageCtl.perspectives.length > 0
                Instantiator {
                    model: packageCtl.perspectives
                    delegate: MenuItem {
                        required property var modelData
                        text: modelData
                        onTriggered: packageCtl.deletePerspective(modelData)
                    }
                    onObjectAdded: function (index, object) { perspectiveDeleteMenu.insertItem(index, object) }
                    onObjectRemoved: function (index, object) { perspectiveDeleteMenu.removeItem(object) }
                }
            }
            Action { text: qsTr("Perspektive zurücksetzen"); onTriggered: window.applyLayout(window.defaultLayout) }
            Action { text: qsTr("Maximierung aufheben"); enabled: window.maximized !== ""; onTriggered: window.maximized = "" }
        }
        Menu {
            title: qsTr("&Extras")
            Action { text: qsTr("Suche..."); shortcut: StandardKey.Find; enabled: backend.hasPackage; onTriggered: { actionTabs.currentIndex = 3; searchView.focusSimple() } }
            Action { text: qsTr("Paket vollständig validieren"); shortcut: "F5"; enabled: backend.hasPackage && !backend.busy; onTriggered: backend.validate(true) }
            Action { text: qsTr("Zeiträume auf Ablieferung kumulieren"); enabled: backend.hasPackage && !backend.readOnly; onTriggered: backend.accumulateTimeSpans() }
            Menu {
                title: qsTr("Normalisierung")
                enabled: backend.hasSip && !backend.readOnly
                Action { text: qsTr("Datei- und Ordnernamen normalisieren..."); onTriggered: window.confirm(qsTr("Unerlaubte Zeichen in allen Datei- und Ordnernamen der Arbeitskopie ersetzen?"), () => fileOps.normalize("names")) }
                Action { text: qsTr("Pfadlängen bereinigen..."); onTriggered: window.confirm(qsTr("Alle Ordner (O1, O2, ...) und Dateien (P1, P2, ...) umbenennen? Die Originalnamen bleiben in den Metadaten erhalten."), () => fileOps.normalize("paths")) }
                Action { text: qsTr("Datei- und Ordnernamen denormalisieren..."); onTriggered: window.confirm(qsTr("Alle Datei- und Ordnernamen auf die Originalnamen zurücksetzen?"), () => fileOps.normalize("undo")) }
            }
            Action { text: qsTr("Stichprobe: Neue Auswahl"); enabled: backend.hasPackage; onTriggered: { actionTabs.currentIndex = 2; searchCtl.drawSample() } }
            MenuSeparator {}
            Action { text: qsTr("Benutzervorgaben..."); onTriggered: preferencesDialog.open() }
        }
        Menu {
            title: qsTr("&Hilfe")
            Action { text: qsTr("Benutzerdokumentation"); shortcut: "F1"; onTriggered: packageCtl.openUserManual() }
            Action { text: qsTr("Hilfe für die Tastenbelegung anzeigen"); onTriggered: shortcutsDialog.open() }
            Action { text: qsTr("Über Package Turbo"); onTriggered: aboutDialog.open() }
        }
    }

    header: ToolBar {
        id: appHeader
        padding: 10
        implicitHeight: headerContent.implicitHeight + topPadding + bottomPadding
        background: Rectangle {
            color: palette.base
            border.color: palette.mid
            border.width: 1
        }

        ColumnLayout {
            id: headerContent
            anchors.fill: parent
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                Image {
                    source: "icons/app.svg"
                    sourceSize.width: 34
                    sourceSize.height: 34
                    Layout.preferredWidth: 34
                    Layout.preferredHeight: 34
                    fillMode: Image.PreserveAspectFit
                }
                ColumnLayout {
                    spacing: 0
                    Label { text: qsTr("Package Turbo"); font.pixelSize: 18; font.bold: true; color: palette.text }
                    Label { text: qsTr("eCH-0160 SIP workspace"); font.pixelSize: 11; color: secondaryTextColor }
                }
                Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 34; color: palette.mid }
                Label {
                    id: packageIdentity
                    Layout.fillWidth: true
                    Layout.minimumWidth: 130
                    text: backend.hasPackage ? backend.packageName : qsTr("Kein SIP geöffnet")
                    font.pixelSize: 14
                    font.bold: backend.hasPackage
                    color: backend.hasPackage ? palette.text : palette.placeholderText
                    elide: Text.ElideRight
                    ToolTip.visible: identityHover.hovered && truncated
                    ToolTip.text: text
                    HoverHandler { id: identityHover }
                }
                Rectangle {
                    visible: backend.readOnly
                    radius: 9
                    color: darkMode ? "#293956" : "#e8eefb"
                    implicitWidth: readOnlyLabel.implicitWidth + 18
                    implicitHeight: 26
                    Label {
                        id: readOnlyLabel
                        anchors.centerIn: parent
                        text: qsTr("Nur Lesen")
                        color: darkMode ? "#dce8ff" : "#3d5f9a"
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
                Rectangle {
                    visible: backend.dirty
                    radius: 9
                    color: darkMode ? "#49351f" : "#fff1dc"
                    implicitWidth: dirtyLabel.implicitWidth + 18
                    implicitHeight: 26
                    Label {
                        id: dirtyLabel
                        anchors.centerIn: parent
                        text: qsTr("Ungespeichert")
                        color: darkMode ? "#ffd49a" : "#96501c"
                        font.pixelSize: 11
                        font.bold: true
                    }
                }
                TextField {
                    id: quickSearch
                    Layout.preferredWidth: 250
                    Layout.minimumWidth: 150
                    rightPadding: 36
                    placeholderText: qsTr("Metadaten suchen")
                    enabled: backend.hasPackage
                    selectByMouse: true
                    onAccepted: {
                        actionTabs.currentIndex = 3
                        searchView.focusSimple(text)
                    }
                    ToolButton {
                        anchors.right: parent.right
                        anchors.rightMargin: 3
                        anchors.verticalCenter: parent.verticalCenter
                        width: 30
                        height: 30
                        padding: 0
                        icon.source: "icons/search.svg"
                        icon.color: palette.buttonText
                        icon.width: 16
                        icon.height: 16
                        display: AbstractButton.IconOnly
                        ToolTip.visible: hovered
                        ToolTip.text: qsTr("Suche starten")
                        onClicked: {
                            actionTabs.currentIndex = 3
                            searchView.focusSimple(quickSearch.text)
                        }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: palette.mid }

            Flow {
                Layout.fillWidth: true
                spacing: 6

                ToolButton {
                    text: qsTr("Neues Paket")
                    icon.source: "icons/file-plus.svg"
                    icon.color: palette.buttonText
                    display: AbstractButton.TextBesideIcon
                    onClicked: guarded(() => window.openNewPackageDialog())
                }
                ToolButton {
                    text: qsTr("Öffnen")
                    icon.source: "icons/folder-open.svg"
                    icon.color: palette.buttonText
                    display: AbstractButton.TextBesideIcon
                    onClicked: guarded(() => { openFolderDialog.readOnly = false; openFolderDialog.open() })
                }
                ToolButton {
                    objectName: "savePackageButton"
                    text: qsTr("Speichern")
                    icon.source: "icons/save.svg"
                    icon.color: palette.buttonText
                    display: AbstractButton.TextBesideIcon
                    enabled: backend.hasPackage && !backend.readOnly && !backend.busy
                    onClicked: window.savePackage()
                }
                ToolButton {
                    objectName: "packageUndoButton"
                    icon.source: "icons/undo-2.svg"
                    icon.color: palette.buttonText
                    enabled: backend.canUndo
                    ToolTip.visible: hovered
                    ToolTip.text: qsTr("Paket rückgängig: %1").arg(backend.undoLabel)
                    onClicked: backend.undo()
                }
                ToolButton {
                    objectName: "packageRedoButton"
                    icon.source: "icons/redo-2.svg"
                    icon.color: palette.buttonText
                    enabled: backend.canRedo
                    ToolTip.visible: hovered
                    ToolTip.text: qsTr("Paket wiederholen: %1").arg(backend.redoLabel)
                    onClicked: backend.redo()
                }
                ToolButton {
                    text: qsTr("Schliessen")
                    icon.source: "icons/x.svg"
                    icon.color: palette.buttonText
                    display: AbstractButton.TextBesideIcon
                    enabled: backend.hasPackage
                    onClicked: guarded(() => backend.closePackage())
                }
                ToolSeparator {}
                ToolButton {
                    text: qsTr("Vollständig validieren")
                    icon.source: "icons/shield-check.svg"
                    icon.color: palette.buttonText
                    display: AbstractButton.TextBesideIcon
                    enabled: backend.hasPackage && !backend.busy
                    onClicked: backend.validate(true)
                }
                ToolButton {
                    text: qsTr("Reports")
                    icon.source: "icons/chart-column-increasing.svg"
                    icon.color: palette.buttonText
                    display: AbstractButton.TextBesideIcon
                    enabled: backend.hasPackage
                    onClicked: reportMenu.popup()
                    Menu {
                        id: reportMenu
                        Instantiator {
                            model: packageCtl.reportTypes
                            delegate: MenuItem {
                                required property var modelData
                                text: modelData.label + "..."
                                onTriggered: { window.reportTarget = modelData.id; reportDialog.open() }
                            }
                            onObjectAdded: function (index, object) { reportMenu.insertItem(index, object) }
                            onObjectRemoved: function (index, object) { reportMenu.removeItem(object) }
                        }
                    }
                }
                ToolButton {
                    text: qsTr("Neue Notiz")
                    icon.source: "icons/sticky-note.svg"
                    icon.color: palette.buttonText
                    display: AbstractButton.TextBesideIcon
                    enabled: backend.hasPackage && !backend.readOnly && editor.currentKey > 0
                    onClicked: window.askNote([editor.currentKey])
                }
                ToolButton {
                    text: qsTr("Stichprobe")
                    icon.source: "icons/scan-search.svg"
                    icon.color: palette.buttonText
                    display: AbstractButton.TextBesideIcon
                    enabled: backend.hasPackage
                    onClicked: { actionTabs.currentIndex = 2; searchCtl.drawSample() }
                }
                ToolButton {
                    icon.source: "icons/rotate-ccw.svg"
                    icon.color: palette.buttonText
                    ToolTip.visible: hovered
                    ToolTip.text: qsTr("Perspektive zurücksetzen")
                    onClicked: window.applyLayout(window.defaultLayout)
                }
            }
        }
    }

    footer: ToolBar {
        RowLayout {
            anchors.fill: parent
            Label {
                id: footerStatus
                text: backend.status
                leftPadding: 8
                Layout.fillWidth: true
                elide: Text.ElideRight
                ToolTip.visible: footerStatusHover.hovered && truncated
                ToolTip.text: text
                HoverHandler { id: footerStatusHover }
            }
            Label {
                visible: structure.cutCount > 0
                text: qsTr("%1 Objekt(e) ausgeschnitten").arg(structure.cutCount)
                color: palette.link
            }
            Label {
                visible: backend.hasPackage
                rightPadding: 8
                text: qsTr("%1 Fehler, %2 Warnungen").arg(backend.errorCount).arg(backend.warningCount)
                color: backend.errorCount > 0 ? errorTextColor : palette.text
            }
        }
    }

    // ---------------------------------------------------------------- layout

    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal

        SplitView {
            id: leftPane
            SplitView.minimumWidth: 220
            orientation: Qt.Vertical
            visible: window.maximized === "" || window.maximized === "classification" || window.maximized === "lowerNav"
            SplitView.fillWidth: window.maximized !== ""

            NavigatorView {
                id: classificationNavigator; objectName: "classificationNavigator"
                visible: window.maximized === "" || window.maximized === "classification"
                SplitView.fillHeight: window.maximized === "classification"
                title: qsTr("Ordnungssystem-Navigator")
                treeModel: classificationModel
                currentFilter: backend.classificationFilter
                contextMenu: classificationMenu
                filters: [
                    { mode: "main_groups", label: "HG", tip: qsTr("Nur Hauptgruppen") },
                    { mode: "positions", label: "OSP", tip: qsTr("Nur Ordnungssystempositionen") },
                    { mode: "positions_with_dossiers", label: "OSP+D", tip: qsTr("Nur Ordnungssystempositionen mit untergeordneten Dossiers") },
                    { mode: "empty_dossiers", label: qsTr("leer"), tip: qsTr("Nur leere Dossiers") }
                ]
                onFilterRequested: function (mode) { backend.setClassificationFilter(mode) }
                onTitleDoubleClicked: window.toggleMaximized("classification")
                onDeleteRequested: classificationMenu.deleteSelection()
            }

            ColumnLayout {
                spacing: 0
                visible: window.maximized === "" || window.maximized === "lowerNav"
                SplitView.fillHeight: true

                TabBar {
                    id: navigatorTabs; objectName: "navigatorTabs"
                    Layout.fillWidth: true
                    TabButton {
                        text: qsTr("Dossiers")
                        ToolTip.visible: hovered
                        ToolTip.text: qsTr("Dossier-Navigator")
                    }
                    TabButton {
                        text: qsTr("Paketinhalt")
                        icon.source: "icons/folder-open.svg"
                        icon.color: palette.buttonText
                        ToolTip.visible: hovered
                        ToolTip.text: qsTr("Paket-Navigator")
                    }
                }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: navigatorTabs.currentIndex

                    NavigatorView {
                        id: dossierNavigator
                        title: qsTr("Dossiers")
                        treeModel: dossierModel
                        columnRatios: [0.38, 0.18, 0.24, 0.20]
                        contextMenu: dossierMenu
                        onTitleDoubleClicked: window.toggleMaximized("lowerNav")
                    }

                    NavigatorView {
                        id: packageNavigator; objectName: "packageNavigator"
                        title: qsTr("Paket")
                        treeModel: packageModel
                        currentFilter: backend.packageFilter
                        contextMenu: packageNavMenu
                        acceptsFileDrops: backend.hasSip && !backend.readOnly
                        filters: [
                            { mode: "unassigned", label: qsTr("nicht zugewiesen"), tip: qsTr("Nur nicht zugewiesene Dateien") }
                        ]
                        onFilterRequested: function (mode) { backend.setPackageFilter(mode) }
                        onTitleDoubleClicked: window.toggleMaximized("lowerNav")
                        onDeleteRequested: packageNavMenu.deleteSelection()
                        onFilesDropped: function (targetKey, urls) { packageNavMenu.importInto(targetKey, urls) }
                    }
                }
            }
        }

        SplitView {
            orientation: Qt.Vertical
            SplitView.fillWidth: true
            visible: window.maximized === "" || window.maximized === "editor" || window.maximized === "actions"

            MetadataEditor {
                visible: window.maximized === "" || window.maximized === "editor"
                SplitView.fillHeight: true
                SplitView.minimumHeight: 200
                onNewNoteRequested: function (key) { window.askNote([key]) }
                onShowNotesRequested: function (key) { window.showNotes(key) }
                onTitleDoubleClicked: window.toggleMaximized("editor")
                onNewPackageRequested: window.guarded(() => window.openNewPackageDialog())
                onOpenPackageRequested: window.guarded(() => { openFolderDialog.readOnly = false; openFolderDialog.open() })

                DropArea {
                    anchors.fill: parent
                    enabled: !backend.hasPackage
                    onDropped: function (drop) {
                        if (drop.hasUrls) {
                            const url = drop.urls[0]
                            guarded(() => backend.openPackage(url, false))
                        }
                    }
                }
            }

            ColumnLayout {
                id: actionPane
                SplitView.minimumHeight: 120
                SplitView.fillHeight: window.maximized === "actions"
                visible: window.maximized === "" || window.maximized === "actions"
                spacing: 0

                TabBar {
                    id: actionTabs; objectName: "actionTabs"
                    Layout.fillWidth: true
                    contentItem: ListView {
                        id: actionTabList
                        objectName: "actionTabList"
                        model: actionTabs.contentModel
                        currentIndex: actionTabs.currentIndex
                        orientation: ListView.Horizontal
                        spacing: actionTabs.spacing
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        flickableDirection: Flickable.HorizontalFlick
                        interactive: contentWidth > width
                        highlightRangeMode: ListView.ApplyRange
                        highlightMoveDuration: 0
                        onCurrentIndexChanged: {
                            if (currentIndex >= 0 && currentIndex < count)
                                positionViewAtIndex(currentIndex, ListView.Contain)
                        }
                        ScrollBar.horizontal: actionTabScrollBar
                    }
                    TabButton {
                        width: actionPane.width < 760 ? 48 : Math.max(132, implicitWidth)
                        text: qsTr("Validierungshilfe") + (backend.errorCount > 0 ? "  \u2716 " + backend.errorCount : "  \u2714")
                        icon.source: "icons/shield-check.svg"
                        icon.color: palette.buttonText
                        display: actionPane.width < 760 ? AbstractButton.IconOnly : AbstractButton.TextBesideIcon
                        ToolTip.visible: hovered
                        ToolTip.text: qsTr("Validierungshilfe: %1 Fehler, %2 Warnungen")
                                      .arg(backend.errorCount).arg(backend.warningCount)
                        TapHandler { onDoubleTapped: window.toggleMaximized("actions") }
                    }
                    TabButton {
                        objectName: "notesActionTab"
                        width: actionPane.width < 760 ? 48 : Math.max(112, implicitWidth)
                        text: qsTr("Notiz") + (notesTable.total > 0 ? " (" + notesTable.total + ")" : "")
                        icon.source: "icons/sticky-note.svg"
                        icon.color: palette.buttonText
                        display: actionPane.width < 760 ? AbstractButton.IconOnly : AbstractButton.TextBesideIcon
                        ToolTip.visible: hovered
                        ToolTip.text: qsTr("Notizen (%1)").arg(notesTable.total)
                    }
                    TabButton {
                        objectName: "sampleActionTab"
                        width: actionPane.width < 760 ? 48 : Math.max(118, implicitWidth)
                        text: qsTr("Stichprobe")
                        icon.source: "icons/scan-search.svg"
                        icon.color: palette.buttonText
                        display: actionPane.width < 760 ? AbstractButton.IconOnly : AbstractButton.TextBesideIcon
                        ToolTip.visible: hovered
                        ToolTip.text: qsTr("Stichprobe")
                    }
                    TabButton {
                        width: actionPane.width < 760 ? 48 : Math.max(100, implicitWidth)
                        text: qsTr("Suche")
                        icon.source: "icons/search.svg"
                        icon.color: palette.buttonText
                        display: actionPane.width < 760 ? AbstractButton.IconOnly : AbstractButton.TextBesideIcon
                        ToolTip.visible: hovered
                        ToolTip.text: qsTr("Suche")
                    }
                    TabButton {
                        width: actionPane.width < 760 ? 48 : Math.max(132, implicitWidth)
                        text: qsTr("Änderungen") + (changesTable.total > 0 ? " (" + changesTable.total + ")" : "")
                        icon.source: "icons/file-text.svg"
                        icon.color: palette.buttonText
                        display: actionPane.width < 760 ? AbstractButton.IconOnly : AbstractButton.TextBesideIcon
                        ToolTip.visible: hovered
                        ToolTip.text: qsTr("Änderungen (%1)").arg(changesTable.total)
                    }
                    TabButton {
                        width: actionPane.width < 760 ? 48 : Math.max(172, implicitWidth)
                        text: qsTr("Metadaten-Historie") + (historyTable.total > 0 ? " (" + historyTable.total + ")" : "")
                        icon.source: "icons/clock.svg"
                        icon.color: palette.buttonText
                        display: actionPane.width < 760 ? AbstractButton.IconOnly : AbstractButton.TextBesideIcon
                        ToolTip.visible: hovered
                        ToolTip.text: qsTr("Metadaten-Historie (%1)").arg(historyTable.total)
                    }
                }

                ScrollBar {
                    id: actionTabScrollBar
                    objectName: "actionTabScrollBar"
                    Layout.fillWidth: true
                    visible: actionTabList.contentWidth > actionTabList.width
                    policy: ScrollBar.AlwaysOn
                    orientation: Qt.Horizontal
                }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: actionTabs.currentIndex

                    ValidationView {
                        onExportRequested: { window.exportTarget = "validation"; exportTableDialog.open() }
                    }
                    NotesView {
                        id: notesView
                        onExportRequested: { window.exportTarget = "notes"; exportTableDialog.open() }
                        onEditRequested: function (noteKey, text) {
                            inputDialog.ask(qsTr("Notiz bearbeiten"), qsTr("Notiz"), text,
                                            value => notesCtl.editNote(noteKey, value), { multiline: true })
                        }
                    }
                    SampleView {
                        onExportRequested: { window.exportTarget = "sample"; exportTableDialog.open() }
                    }
                    SearchView {
                        id: searchView
                        onExportRequested: { window.exportTarget = "search"; exportTableDialog.open() }
                    }
                    ColumnLayout {
                        spacing: 0
                        ToolBar {
                            Layout.fillWidth: true
                            RowLayout {
                                anchors.fill: parent
                                Label { leftPadding: 6; text: qsTr("%1 Änderungen seit dem letzten Speichern").arg(changesTable.total); Layout.fillWidth: true }
                                ToolButton { text: qsTr("Kopieren"); onClicked: changesView.copySelection() }
                                ToolButton { text: qsTr("Export"); onClicked: { window.exportTarget = "changes"; exportTableDialog.open() } }
                            }
                        }
                        DataTable {
                            id: changesView
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            tableModel: changesTable
                            columnRatios: [0.13, 0.1, 0.2, 0.15, 0.21, 0.21]
                            onRowActivated: function (row) { backend.reveal(changesTable.recordAt(row).key) }
                        }
                    }
                    HistoryView {
                        onCleanupRequested: storageCleanupDialog.open()
                        onExportRequested: auditExportDialog.open()
                        onDetailsRequested: function(text) {
                            eventDetails.text = text
                            try { window.eventDetailData = JSON.parse(text) }
                            catch (error) { window.eventDetailData = ({}) }
                            window.showRawEventDetails = false
                            eventDialog.open()
                        }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- context menus

    Menu {
        id: classificationMenu; objectName: "classificationMenu"
        width: Math.min(window.width - 24, Math.max(implicitWidth, 450))

        readonly property int key: classificationNavigator.currentKey
        readonly property string kind: classificationNavigator.currentKind
        readonly property int owner: classificationNavigator.currentOwner
        readonly property bool writable: backend.hasPackage && !backend.readOnly
        property var allowed: []

        onAboutToShow: allowed = structure.allowedChildren(key)

        function create(tag, many) {
            const target = key
            const label = { ordnungssystemposition: qsTr("Ordnungssystempositionen"), dossier: qsTr("Dossiers"),
                            dokument: qsTr("Dokumente"), mappe: qsTr("Mappen"), vorgang: qsTr("Vorgänge"),
                            aktivitaet: qsTr("Aktivitäten") }[tag]
            if (many)
                inputDialog.ask(qsTr("Mehrere neue %1").arg(label), qsTr("Anzahl"), "", n => structure.addObjects(target, tag, n), { numeric: true, number: 2 })
            else
                structure.addObjects(target, tag, 1)
        }

        function deleteSelection() {
            const keys = classificationNavigator.selectedKeys()
            if (classificationNavigator.currentKind === "datei" && classificationNavigator.currentOwner) {
                const owner = classificationNavigator.currentOwner, file = classificationNavigator.currentKey
                window.confirm(qsTr("Zuweisung der Datei zum Objekt löschen?"), () => structure.unassignFile(owner, file))
                return
            }
            window.confirm(qsTr("%1 Objekt(e) mit allen darunterliegenden Elementen löschen?").arg(keys.length),
                           () => structure.deleteObjects(keys))
        }

        MenuItem { text: qsTr("Neue Ordnungssystemposition"); enabled: classificationMenu.writable && classificationMenu.allowed.indexOf("ordnungssystemposition") >= 0; onTriggered: classificationMenu.create("ordnungssystemposition", false) }
        MenuItem { text: qsTr("Mehrere neue Ordnungssystempositionen..."); enabled: classificationMenu.writable && classificationMenu.allowed.indexOf("ordnungssystemposition") >= 0; onTriggered: classificationMenu.create("ordnungssystemposition", true) }
        MenuItem { text: qsTr("Neues Dossier"); enabled: classificationMenu.writable && classificationMenu.allowed.indexOf("dossier") >= 0; onTriggered: classificationMenu.create("dossier", false) }
        MenuItem { text: qsTr("Mehrere neue Dossiers..."); enabled: classificationMenu.writable && classificationMenu.allowed.indexOf("dossier") >= 0; onTriggered: classificationMenu.create("dossier", true) }
        MenuItem { text: qsTr("Neues Dokument"); enabled: classificationMenu.writable && classificationMenu.allowed.indexOf("dokument") >= 0; onTriggered: classificationMenu.create("dokument", false) }
        MenuItem { text: qsTr("Mehrere neue Dokumente..."); enabled: classificationMenu.writable && classificationMenu.allowed.indexOf("dokument") >= 0; onTriggered: classificationMenu.create("dokument", true) }
        MenuItem { text: qsTr("Neue Mappe"); enabled: classificationMenu.writable && classificationMenu.allowed.indexOf("mappe") >= 0; onTriggered: classificationMenu.create("mappe", false) }
        MenuItem { objectName: "newProcessAction"; text: qsTr("Neuer Vorgang"); enabled: classificationMenu.writable && classificationMenu.allowed.indexOf("vorgang") >= 0; onTriggered: classificationMenu.create("vorgang", false) }
        MenuItem { objectName: "newActivityAction"; text: qsTr("Neue Aktivität"); enabled: classificationMenu.writable && classificationMenu.allowed.indexOf("aktivitaet") >= 0; onTriggered: classificationMenu.create("aktivitaet", false) }
        MenuSeparator {}
        MenuItem { text: qsTr("Neues Dokument für diese Datei"); enabled: classificationMenu.writable && classificationMenu.kind === "datei" && classificationMenu.owner > 0; onTriggered: structure.documentForFile(classificationMenu.owner, classificationMenu.key) }
        MenuItem { text: qsTr("Neue Dokumente für die enthaltenen Dateien"); enabled: classificationMenu.writable && (classificationMenu.kind === "dossier" || classificationMenu.kind === "subdossier"); onTriggered: structure.documentsForFiles(classificationMenu.key) }
        MenuItem {
            text: qsTr("Im Paket-Navigator gewählte Dateien zuweisen")
            enabled: classificationMenu.writable && ["dossier", "subdossier", "dokument", "mappe"].indexOf(classificationMenu.kind) >= 0
            onTriggered: structure.assignFiles(packageNavigator.selectedKeys(), classificationMenu.key)
        }
        MenuItem {
            text: qsTr("Massenzuweisung der im Paket-Navigator gewählten Ordner...")
            enabled: classificationMenu.writable && ["ordnungssystem", "ordnungssystemposition", "dossier", "subdossier"].indexOf(classificationMenu.kind) >= 0
            onTriggered: massAssignDialog.start(packageNavigator.selectedKeys(), classificationMenu.key, classificationMenu.kind,
                                                editor.breadcrumb.length ? editor.breadcrumb[editor.breadcrumb.length - 1].label : "")
        }
        MenuItem { text: qsTr("Zuweisung löschen"); enabled: classificationMenu.writable && classificationMenu.kind === "datei" && classificationMenu.owner > 0; onTriggered: classificationMenu.deleteSelection() }
        MenuSeparator {}
        MenuItem { text: qsTr("Ausschneiden (Verschieben)"); enabled: classificationMenu.writable && ["ordnungssystemposition", "dossier", "subdossier", "dokument", "mappe", "vorgang", "aktivitaet"].indexOf(classificationMenu.kind) >= 0; onTriggered: structure.cut(classificationNavigator.selectedKeys()) }
        MenuItem { text: qsTr("Einfügen (%1 Objekt(e))").arg(structure.cutCount); enabled: classificationMenu.writable && structure.cutCount > 0; onTriggered: structure.paste(classificationMenu.key) }
        MenuItem { text: qsTr("Nach oben"); enabled: classificationMenu.writable && classificationMenu.kind !== "ordnungssystem" && classificationMenu.kind !== "datei"; onTriggered: structure.moveRelative(classificationMenu.key, -1) }
        MenuItem { text: qsTr("Nach unten"); enabled: classificationMenu.writable && classificationMenu.kind !== "ordnungssystem" && classificationMenu.kind !== "datei"; onTriggered: structure.moveRelative(classificationMenu.key, 1) }
        MenuSeparator {}
        MenuItem { text: qsTr("Massenmutation..."); enabled: classificationMenu.writable && classificationMenu.kind !== "datei"; onTriggered: massEditDialog.start(classificationMenu.key, editor.breadcrumb.length ? editor.breadcrumb[editor.breadcrumb.length - 1].label : "") }
        MenuItem { text: qsTr("Zeiträume kumulieren"); enabled: classificationMenu.writable && (classificationMenu.kind === "dossier" || classificationMenu.kind === "subdossier"); onTriggered: structure.accumulateTimeSpans(classificationMenu.key) }
        MenuItem { text: qsTr("Ordnungssystem neu nummerieren..."); enabled: classificationMenu.writable && classificationMenu.kind === "ordnungssystem"; onTriggered: renumberDialog.open() }
        MenuSeparator {}
        MenuItem { text: qsTr("Neue Notiz..."); enabled: classificationMenu.writable && notesCtl.canHaveNotes(classificationMenu.key); onTriggered: window.askNote(classificationNavigator.selectedKeys()) }
        MenuItem { text: qsTr("Gehe zu Notiz"); enabled: notesTable.rowOfKey(classificationMenu.key) >= 0; onTriggered: window.showNotes(classificationMenu.key) }
        MenuItem { text: qsTr("Datei zeigen"); enabled: classificationMenu.kind === "datei"; onTriggered: backend.openFile(classificationMenu.key) }
        MenuItem { text: qsTr("Kopieren"); onTriggered: classificationNavigator.copySelection() }
        MenuItem { text: qsTr("Löschen"); enabled: classificationMenu.writable && classificationMenu.kind !== "ordnungssystem"; onTriggered: classificationMenu.deleteSelection() }
    }

    Menu {
        id: dossierMenu
        readonly property int key: dossierNavigator.currentKey
        readonly property string kind: dossierNavigator.currentKind
        MenuItem { text: qsTr("Im Ordnungssystem anzeigen"); onTriggered: classificationNavigator.revealKey(dossierMenu.key) }
        MenuItem { text: qsTr("Datei zeigen"); enabled: dossierMenu.kind === "datei"; onTriggered: backend.openFile(dossierMenu.key) }
        MenuItem { text: qsTr("Neue Notiz..."); enabled: !backend.readOnly && notesCtl.canHaveNotes(dossierMenu.key); onTriggered: window.askNote(dossierNavigator.selectedKeys()) }
        MenuItem { text: qsTr("Gehe zu Notiz"); enabled: notesTable.rowOfKey(dossierMenu.key) >= 0; onTriggered: window.showNotes(dossierMenu.key) }
        MenuItem { text: qsTr("Die selektierten Zeilen in die Zwischenablage kopieren"); onTriggered: dossierNavigator.copySelection() }
    }

    Menu {
        id: packageNavMenu; objectName: "packageNavMenu"
        width: Math.min(window.width - 24, Math.max(implicitWidth, 450))
        readonly property int key: packageNavigator.currentKey
        readonly property string kind: packageNavigator.currentKind
        readonly property bool writable: backend.hasSip && !backend.readOnly
        property int importTarget: 0
        property var importUrls: []

        function deleteSelection() {
            const keys = packageNavigator.selectedKeys()
            window.confirm(qsTr("%1 Ordner/Datei(en) aus der Arbeitskopie entfernen?").arg(keys.length),
                           () => fileOps.deleteEntries(keys))
        }

        function importInto(target, urls) {
            importTarget = target
            importUrls = urls
            const conflicts = fileOps.importConflicts(target, urls)
            if (conflicts.length > 0) {
                mergeDialog.text = qsTr("Folgende Objekte existieren bereits: %1\nZusammenführen und gleichnamige Dateien ersetzen?").arg(conflicts.join(", "))
                mergeDialog.open()
            } else {
                fileOps.importUrls(target, urls, true, false)
            }
        }

        MenuItem { text: qsTr("Neuer Ordner..."); enabled: packageNavMenu.writable && packageNavMenu.kind === "ordner"; onTriggered: { const parent = packageNavMenu.key; inputDialog.ask(qsTr("Neuer Ordner"), qsTr("Name (ASCII-Buchstaben, Ziffern, ! # $ % ( ) + , - . = @ [ ] { } ~ _ und Leerzeichen)"), "", name => fileOps.newFolder(parent, name)) } }
        MenuItem { text: qsTr("Dateien importieren..."); enabled: packageNavMenu.writable && packageNavMenu.kind === "ordner"; onTriggered: importFilesDialog.open() }
        MenuItem { text: qsTr("Ordner importieren..."); enabled: packageNavMenu.writable && packageNavMenu.kind === "ordner"; onTriggered: importFolderDialog.open() }
        MenuItem { text: qsTr("Umbenennen..."); enabled: packageNavMenu.writable && (packageNavMenu.kind === "ordner" || packageNavMenu.kind === "datei"); onTriggered: { const target = packageNavMenu.key; inputDialog.ask(qsTr("Umbenennen"), qsTr("Neuer Name (der Originalname bleibt erhalten)"), "", name => fileOps.rename(target, name)) } }
        MenuItem { text: qsTr("Datei ersetzen..."); enabled: packageNavMenu.writable && packageNavMenu.kind === "datei"; onTriggered: replaceFileDialog.open() }
        MenuItem { text: qsTr("Dateien ersetzen..."); enabled: packageNavMenu.writable && packageNavMenu.kind === "paket"; onTriggered: replaceFilesDialog.open() }
        MenuSeparator {}
        MenuItem { text: qsTr("Dem im Ordnungssystem gewählten Objekt zuweisen"); enabled: packageNavMenu.writable && packageNavMenu.kind === "datei" && classificationNavigator.currentKey > 0; onTriggered: structure.assignFiles(packageNavigator.selectedKeys(), classificationNavigator.currentKey) }
        MenuItem {
            text: qsTr("Massenzuweisung auf das im Ordnungssystem gewählte Objekt...")
            enabled: packageNavMenu.writable && packageNavMenu.kind === "ordner" && classificationNavigator.currentKey > 0
            onTriggered: massAssignDialog.start(packageNavigator.selectedKeys(), classificationNavigator.currentKey,
                                                classificationNavigator.currentKind, qsTr("Auswahl im Ordnungssystem-Navigator"))
        }
        MenuSeparator {}
        MenuItem { text: qsTr("Neue Notiz..."); enabled: packageNavMenu.writable && packageNavMenu.kind === "datei"; onTriggered: window.askNote(packageNavigator.selectedKeys()) }
        MenuItem { text: qsTr("Gehe zu Notiz"); enabled: notesTable.rowOfKey(packageNavMenu.key) >= 0; onTriggered: window.showNotes(packageNavMenu.key) }
        MenuItem { text: qsTr("Datei zeigen"); enabled: packageNavMenu.kind === "datei"; onTriggered: backend.openFile(packageNavMenu.key) }
        MenuItem { text: qsTr("Im Ordnungssystem anzeigen"); enabled: packageNavMenu.kind === "datei"; onTriggered: classificationNavigator.revealKey(packageNavMenu.key) }
        MenuItem { text: qsTr("Löschen"); enabled: packageNavMenu.writable && (packageNavMenu.kind === "ordner" || packageNavMenu.kind === "datei"); onTriggered: packageNavMenu.deleteSelection() }
    }

    // ---------------------------------------------------------------- backend signals

    Connections {
        target: backend
        function onMessage(title, text) {
            messageDialog.title = title
            messageDialog.message = text
            messageDialog.open()
        }
        function onPackageOpened() {
            if (backend.errorCount > 0)
                invalidOnOpenDialog.open()
            else
                fullValidationDialog.open()
        }
        function onRevealElement(key) {
            Qt.callLater(window.revealInNavigators, key)
        }
        function onBusyChanged() {
            if (backend.busy) progressDialog.open(); else progressDialog.close()
        }
        function onValidityPrompt() {
            validityDialog.open()
        }
        function onAuditOperatorRequired() {
            inputDialog.ask(qsTr("Identität bestätigen"), qsTr("Bearbeitet durch"), backend.auditOperator,
                            name => { backend.auditOperator = name })
        }
    }

    // ---------------------------------------------------------------- dialogs

    FolderDialog {
        id: openFolderDialog
        property bool readOnly: false
        title: readOnly ? qsTr("Paket schreibgeschützt öffnen") : qsTr("Toplevel-Ordner des SIP auswählen")
        onAccepted: backend.openPackage(selectedFolder, readOnly)
    }
    FileDialog {
        id: openMetadataDialog
        title: qsTr("metadata.xml öffnen")
        nameFilters: [qsTr("Metadaten (*.xml)")]
        onAccepted: backend.openMetadata(selectedFile)
    }
    FileDialog {
        id: zipDialog
        title: qsTr("Paket zippen")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "zip"
        nameFilters: [qsTr("ZIP-Archiv (*.zip)")]
        onAccepted: backend.zipPackage(selectedFile)
    }
    FileDialog {
        id: exportXmlDialog
        title: qsTr("metadata.xml exportieren")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "xml"
        nameFilters: [qsTr("Metadaten (*.xml)")]
        onAccepted: backend.exportMetadata(selectedFile)
    }
    FileDialog {
        id: exportPremisDialog
        objectName: "auditPremisFileDialog"
        title: qsTr("PREMIS XML exportieren")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "xml"
        nameFilters: [qsTr("PREMIS XML (*.xml)")]
        onAccepted: backend.exportPremis(selectedFile, window.auditExportRedacted)
    }
    FolderDialog {
        id: exportAuditBundleDialog
        objectName: "auditBundleFolderDialog"
        title: qsTr("Ordner für SIP/METS/PREMIS-Export auswählen")
        onAccepted: backend.exportAuditBundle(selectedFolder, window.auditExportRedacted,
                                              window.auditExportMetsVersion)
    }
    FileDialog {
        id: exportTableDialog
        title: qsTr("Tabelle exportieren")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "csv"
        nameFilters: [qsTr("CSV für Excel (*.csv)")]
        onAccepted: backend.exportTable(window.exportTarget, selectedFile)
    }
    FileDialog {
        id: reportDialog
        title: qsTr("Bericht speichern")
        fileMode: FileDialog.SaveFile
        defaultSuffix: "pdf"
        nameFilters: [qsTr("PDF (*.pdf)")]
        onAccepted: packageCtl.createReport(window.reportTarget, selectedFile)
    }
    FileDialog {
        id: importFilesDialog
        title: qsTr("Dateien importieren")
        fileMode: FileDialog.OpenFiles
        onAccepted: packageNavMenu.importInto(packageNavigator.currentKey, selectedFiles)
    }
    FolderDialog {
        id: importFolderDialog
        title: qsTr("Ordner importieren")
        onAccepted: packageNavMenu.importInto(packageNavigator.currentKey, [selectedFolder])
    }
    FileDialog {
        id: replaceFileDialog
        title: qsTr("Datei ersetzen")
        onAccepted: fileOps.replaceFile(packageNavigator.currentKey, selectedFile)
    }
    FolderDialog {
        id: replaceFilesDialog
        title: qsTr("Ordner mit den Ersatzdateien")
        onAccepted: {
            const found = fileOps.replacementCandidates(selectedFolder)
            if (found.length === 0) {
                messageDialog.title = qsTr("Dateien ersetzen")
                messageDialog.message = qsTr("Es wurden keine gleichnamigen Dateien gefunden.")
                messageDialog.open()
                return
            }
            const folder = selectedFolder
            window.confirm(qsTr("Für folgende Dateien wurde ein Ersatz gefunden:\n%1\n\nDateien ersetzen?").arg(found.join("\n")),
                           () => fileOps.replaceFiles(folder))
        }
    }

    InputDialog { id: inputDialog; objectName: "inputDialog" }
    AuditExportDialog {
        id: auditExportDialog
        objectName: "auditExportDialog"
        onPremisExportRequested: function(redactValues) {
            window.auditExportRedacted = redactValues
            exportPremisDialog.open()
        }
        onBundleExportRequested: function(redactValues, metsVersion) {
            window.auditExportRedacted = redactValues
            window.auditExportMetsVersion = metsVersion
            exportAuditBundleDialog.open()
        }
    }
    NewPackageDialog { id: newPackageDialog; objectName: "newPackageDialog" }
    MassAssignDialog { id: massAssignDialog; objectName: "massAssignDialog" }
    MassEditDialog { id: massEditDialog; objectName: "massEditDialog" }
    PreferencesDialog { id: preferencesDialog; objectName: "preferencesDialog" }
    StorageCleanupDialog { id: storageCleanupDialog; objectName: "storageCleanupDialog" }

    Dialog {
        id: eventDialog
        objectName: "eventDialog"
        title: qsTr("Ereignisdetails")
        anchors.centerIn: Overlay.overlay
        width: Math.min(720, window.width - 40)
        height: Math.min(520, window.height - 40)
        modal: true
        standardButtons: Dialog.Close
        ScrollView {
            anchors.fill: parent
            ColumnLayout {
                width: eventDialog.availableWidth
                spacing: 8

                Label {
                    Layout.fillWidth: true
                    visible: (window.eventDetailData.changeSummary || []).length > 0
                    text: qsTr("Änderungen")
                    font.bold: true
                }
                Repeater {
                    model: window.eventDetailData.changeSummary || []
                    delegate: ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 3
                        Label {
                            Layout.fillWidth: true
                            text: modelData.field ? modelData.field + "  ·  " + modelData.path : modelData.path
                            font.bold: true
                            wrapMode: Text.WrapAnywhere
                        }
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            Label { text: qsTr("Vorher") }
                            Label {
                                Layout.fillWidth: true
                                text: window.auditValueText(modelData.before)
                                wrapMode: Text.WrapAnywhere
                            }
                            Label { text: qsTr("Nachher") }
                            Label {
                                Layout.fillWidth: true
                                text: window.auditValueText(modelData.after)
                                wrapMode: Text.WrapAnywhere
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: palette.mid }
                    }
                }
                Label {
                    Layout.fillWidth: true
                    visible: (window.eventDetailData.deletedObjects || []).length > 0
                    text: qsTr("Gelöschte Objekte")
                    font.bold: true
                }
                Repeater {
                    model: window.eventDetailData.deletedObjects || []
                    delegate: Label {
                        required property var modelData
                        Layout.fillWidth: true
                        text: modelData.kind + ": " + modelData.label + "  ·  " + modelData.path
                              + (modelData.identifier ? "  ·  " + modelData.identifier : "")
                        wrapMode: Text.WrapAnywhere
                    }
                }
                ToolButton {
                    text: window.showRawEventDetails ? qsTr("Rohdaten ausblenden") : qsTr("Rohdaten anzeigen")
                    onClicked: window.showRawEventDetails = !window.showRawEventDetails
                }
                TextArea {
                    id: eventDetails
                    Layout.fillWidth: true
                    Layout.preferredHeight: 240
                    visible: window.showRawEventDetails
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                }
            }
        }
    }

    Dialog {
        id: renumberDialog; objectName: "renumberDialog"
        title: qsTr("Ordnungssystem neu nummerieren")
        anchors.centerIn: parent
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        ColumnLayout {
            Label { text: qsTr("Gliederungsvariante") }
            ComboBox { id: schemeBox; model: [qsTr("Freie Zehnergliederung"), qsTr("Gliederung mit 1 bis 100 Positionen")]; Layout.preferredWidth: 320 }
        }
        onAccepted: structure.renumber(schemeBox.currentIndex === 0 ? "decimal" : "hundred")
    }

    MessageBox { id: messageDialog; objectName: "messageDialog"; buttonSet: "ok" }

    MessageBox {
        id: confirmDialog
        property var action: null
        title: qsTr("Bestätigen")
        buttonSet: "okCancel"
        onAccepted: if (action) action()
    }

    MessageBox {
        id: mergeDialog
        title: qsTr("Ordner zusammenführen")
        buttonSet: "yesNoCancel"
        onActionChosen: function (action) {
            if (action === "yes")
                fileOps.importUrls(packageNavMenu.importTarget, packageNavMenu.importUrls, true, true)
            else if (action === "no")
                fileOps.importUrls(packageNavMenu.importTarget, packageNavMenu.importUrls, false, false)
        }
    }

    MessageBox {
        id: invalidOnOpenDialog
        title: qsTr("Gültigkeitsprüfung fehlgeschlagen")
        message: qsTr("Das Paket entspricht noch nicht allen Anforderungen. Die Details sind in der Validierungshilfe ersichtlich.")
        buttonSet: "ok"
        onAccepted: fullValidationDialog.open()
    }

    MessageBox {
        id: fullValidationDialog
        objectName: "fullValidationDialog"
        title: qsTr("Paket vollständig validieren")
        message: qsTr("Soll das Paket vollständig validiert werden?")
        informativeText: qsTr("Die Validierung kann bei grösseren Paketen einige Zeit in Anspruch nehmen.")
        buttonSet: "okCancel"
        onAccepted: backend.validate(true)
    }

    MessageBox {
        id: validityDialog
        title: qsTr("Gültigkeitsprüfung fehlgeschlagen")
        message: qsTr("Alle Fehler sind behoben. Soll das Paket gespeichert und erneut vollständig validiert werden?")
        buttonSet: "okCancel"
        onAccepted: {
            if (!backend.readOnly && !backend.save())
                return
            backend.validate(true)
        }
    }

    MessageBox {
        id: unsavedDialog
        title: qsTr("Änderungen speichern")
        message: qsTr("Die Metadaten wurden geändert. Sollen die Änderungen gespeichert werden?")
        buttonSet: "saveDiscardCancel"
        onActionChosen: function (action) {
            if (action === "save") {
                if (backend.save())
                    window.proceedAfterSave()
            } else if (action === "discard") {
                if (backend.discardChanges())
                    window.proceedAfterSave()
            } else if (action === "cancel") {
                window.pendingAction = null
            }
        }
    }

    MessageBox {
        id: errorsOnCloseDialog
        title: qsTr("Paket schliessen")
        message: qsTr("Das Paket entspricht noch nicht vollständig den Anforderungen des Archivs. Trotzdem schliessen?")
        buttonSet: "okCancel"
        onAccepted: window.runPending()
        onRejected: window.pendingAction = null
    }

    Dialog {
        id: progressDialog
        title: qsTr("Bitte warten")
        anchors.centerIn: parent
        width: 380
        modal: true
        closePolicy: Popup.NoAutoClose

        ColumnLayout {
            anchors.fill: parent
            spacing: 12
            Label { text: backend.status; Layout.fillWidth: true; wrapMode: Text.Wrap }
            ProgressBar { Layout.fillWidth: true; from: 0; to: 100; value: backend.progress; indeterminate: backend.totalBytes === 0 && backend.busy }
            Label {
                Layout.fillWidth: true
                visible: backend.totalBytes > 0
                text: qsTr("%1 / %2 Byte").arg(backend.completedBytes).arg(backend.totalBytes)
                elide: Text.ElideRight
                ToolTip.visible: byteCountHover.hovered && truncated
                ToolTip.text: text
                HoverHandler { id: byteCountHover }
            }
            Button { objectName: "cancelTaskButton"; text: qsTr("Abbrechen"); enabled: backend.canCancelTask; Layout.alignment: Qt.AlignHCenter; onClicked: backend.cancelTask() }
        }
    }

    Dialog {
        id: shortcutsDialog; objectName: "shortcutsDialog"
        title: qsTr("Tastenbelegung")
        anchors.centerIn: parent
        modal: true
        standardButtons: Dialog.Close

        GridLayout {
            columns: 2
            columnSpacing: 24
            Label { text: "Ctrl+N" } Label { text: qsTr("Neues Paket erstellen") }
            Label { text: "Ctrl+O" } Label { text: qsTr("Paket öffnen") }
            Label { text: "Ctrl+S" } Label { text: qsTr("Speichern") }
            Label { text: "Ctrl+W" } Label { text: qsTr("Paket schliessen") }
            Label { text: "Ctrl+F" } Label { text: qsTr("Suche") }
            Label { text: "Ctrl+C" } Label { text: qsTr("Kopieren (Text oder selektierte Zeilen)") }
            Label { text: "Entf" } Label { text: qsTr("Selektierte Objekte im Navigator löschen") }
            Label { text: "F1" } Label { text: qsTr("Benutzerdokumentation") }
            Label { text: "F5" } Label { text: qsTr("Paket vollständig validieren") }
        }
    }

    Dialog {
        id: aboutDialog; objectName: "aboutDialog"
        title: qsTr("Über Package Turbo")
        anchors.centerIn: parent
        modal: true
        standardButtons: Dialog.Close

        Label {
            text: qsTr("Package Turbo %1\nErstellen, Bearbeiten und Prüfen von digitalen Ablieferungen\n(SIP gemäss eCH-0160, %2).\n\nDateiformate gemäss KOST-CECO Katalog archivischer Dateiformate (KaD).")
                  .arg(appVersion).arg(packageCtl.xsdVersion)
        }
    }
}
