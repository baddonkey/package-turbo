import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtCore

ApplicationWindow {
    id: window

    width: 1500
    height: 950
    visible: true
    title: "Package Turbo" + (backend.hasPackage ? " \u2013 " + backend.packageName : "")
           + (backend.readOnly ? qsTr(" (schreibgeschützt)") : "") + (backend.dirty ? " *" : "")

    property var pendingAction: null
    property bool closeConfirmed: false
    property string exportTarget: ""
    property string reportTarget: ""
    property string maximized: ""

    readonly property var defaultLayout: ({ leftWidth: 460, classificationHeight: 420, actionsHeight: 300 })

    // ---------------------------------------------------------------- helpers

    function guarded(action) {
        pendingAction = action
        if (backend.dirty)
            unsavedDialog.open()
        else
            proceedAfterSave()
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
        classificationDock.SplitView.preferredHeight = state.classificationHeight || defaultLayout.classificationHeight
        actionDock.SplitView.preferredHeight = state.actionsHeight || defaultLayout.actionsHeight
    }

    function resetLayout() {
        classificationDock.dockInto(leftPane)
        lowerNavDock.dockInto(leftPane)
        editorDock.dockInto(rightPane)
        actionDock.dockInto(rightPane)
        classificationDock.SplitView.preferredHeight = defaultLayout.classificationHeight
        actionDock.SplitView.preferredHeight = defaultLayout.actionsHeight
        leftPane.SplitView.preferredWidth = defaultLayout.leftWidth
        maximized = ""
    }

    function currentLayout() {
        return { leftWidth: leftPane.width, classificationHeight: classificationDock.height,
                 actionsHeight: actionDock.height }
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
        confirmDialog.text = text
        confirmDialog.action = action
        confirmDialog.open()
    }

    function textTarget() {
        const item = window.activeFocusItem
        return item && typeof item.cut === "function" && typeof item.paste === "function" ? item : null
    }

    onClosing: function (close) {
        layoutSettings.leftWidth = leftPane.width
        layoutSettings.classificationHeight = classificationDock.height
        layoutSettings.actionsHeight = actionDock.height
        layoutSettings.classificationOpen = classificationDock.open
        layoutSettings.lowerNavOpen = lowerNavDock.open
        layoutSettings.editorOpen = editorDock.open
        layoutSettings.actionsOpen = actionDock.open
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
        property bool classificationOpen: true
        property bool lowerNavOpen: true
        property bool editorOpen: true
        property bool actionsOpen: true
    }

    Shortcut { sequence: "F1"; onActivated: packageCtl.openUserManual() }

    // ---------------------------------------------------------------- menus

    menuBar: MenuBar {
        Menu {
            id: packageMenu
            title: qsTr("&Paket")
            Action { text: qsTr("Neues Paket erstellen..."); shortcut: StandardKey.New; onTriggered: guarded(() => newPackageDialog.open()) }
            Action { text: qsTr("Paket öffnen..."); shortcut: StandardKey.Open; onTriggered: guarded(() => { openFolderDialog.readOnly = false; openFolderDialog.open() }) }
            Action { text: qsTr("Paket schreibgeschützt öffnen..."); onTriggered: guarded(() => { openFolderDialog.readOnly = true; openFolderDialog.open() }) }
            Action { text: qsTr("metadata.xml öffnen..."); onTriggered: guarded(() => openMetadataDialog.open()) }
            MenuSeparator {}
            Action { text: qsTr("Speichern"); shortcut: StandardKey.Save; enabled: backend.dirty && !backend.readOnly; onTriggered: backend.save() }
            Action { text: qsTr("Paket zippen..."); enabled: backend.hasSip; onTriggered: zipDialog.open() }
            Action { text: qsTr("metadata.xml exportieren..."); enabled: backend.hasPackage; onTriggered: exportXmlDialog.open() }
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
                    text: (index + 1) + "  " + modelData
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
            Action { text: qsTr("Rückgängig"); shortcut: StandardKey.Undo; onTriggered: { const t = window.textTarget(); if (t) t.undo() } }
            MenuSeparator {}
            Action { text: qsTr("Ausschneiden"); shortcut: StandardKey.Cut; onTriggered: { const t = window.textTarget(); if (t) t.cut() } }
            Action { text: qsTr("Kopieren"); shortcut: StandardKey.Copy; onTriggered: { const t = window.textTarget(); if (t) t.copy() } }
            Action { text: qsTr("Einfügen"); shortcut: StandardKey.Paste; onTriggered: { const t = window.textTarget(); if (t) t.paste() } }
        }
        Menu {
            id: viewMenu
            title: qsTr("&Ansicht")
            Menu {
                title: qsTr("Ansichten")
                MenuItem { text: qsTr("Ordnungssystem-Navigator"); checkable: true; checked: classificationDock.open; onTriggered: checked ? classificationDock.open = true : classificationDock.closePanel() }
                MenuItem { text: qsTr("Dossier- und Paket-Navigator"); checkable: true; checked: lowerNavDock.open; onTriggered: checked ? lowerNavDock.open = true : lowerNavDock.closePanel() }
                MenuItem { text: qsTr("Editor"); checkable: true; checked: editorDock.open; onTriggered: checked ? editorDock.open = true : editorDock.closePanel() }
                MenuItem { text: qsTr("Aktionsviews"); checkable: true; checked: actionDock.open; onTriggered: checked ? actionDock.open = true : actionDock.closePanel() }
            }
            MenuSeparator {}
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
            Action { text: qsTr("Perspektive zurücksetzen"); onTriggered: window.resetLayout() }
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
                Action { text: qsTr("Datei- und Ordnernamen normalisieren..."); onTriggered: window.confirm(qsTr("Unerlaubte Zeichen in allen Datei- und Ordnernamen ersetzen? Das Paket wird anschliessend gespeichert."), () => fileOps.normalize("names")) }
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
        RowLayout {
            anchors.fill: parent
            spacing: 2

            ToolButton { text: qsTr("Neues Paket"); onClicked: guarded(() => newPackageDialog.open()) }
            ToolButton { text: qsTr("Paket öffnen"); onClicked: guarded(() => { openFolderDialog.readOnly = false; openFolderDialog.open() }) }
            ToolButton { text: qsTr("Speichern"); enabled: backend.dirty && !backend.readOnly; onClicked: backend.save() }
            ToolButton { text: qsTr("Paket schliessen"); enabled: backend.hasPackage; onClicked: guarded(() => backend.closePackage()) }
            ToolSeparator {}
            ToolButton {
                text: qsTr("Paket vollständig validieren")
                enabled: backend.hasPackage && !backend.busy
                onClicked: backend.validate(true)
            }
            ToolButton {
                text: qsTr("Reports")
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
                enabled: backend.hasPackage && !backend.readOnly && editor.currentKey > 0
                onClicked: window.askNote([editor.currentKey])
            }
            ToolButton { text: qsTr("Stichprobe"); enabled: backend.hasPackage; onClicked: { actionTabs.currentIndex = 2; searchCtl.drawSample() } }
            ToolButton {
                text: "\u21BA"
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Perspektive zurücksetzen")
                onClicked: window.applyLayout(window.defaultLayout)
            }
            Item { Layout.fillWidth: true }
            TextField {
                Layout.preferredWidth: 260
                placeholderText: qsTr("Einfache Suche ...")
                enabled: backend.hasPackage
                onAccepted: {
                    actionTabs.currentIndex = 3
                    searchView.focusSimple(text)
                }
            }
        }
    }

    footer: ToolBar {
        RowLayout {
            anchors.fill: parent
            Label { text: backend.status; leftPadding: 8; Layout.fillWidth: true; elide: Text.ElideRight }
            Label {
                visible: structure.cutCount > 0
                text: qsTr("%1 Objekt(e) ausgeschnitten").arg(structure.cutCount)
                color: palette.link
            }
            Label {
                visible: backend.hasPackage
                rightPadding: 8
                text: qsTr("%1 Fehler, %2 Warnungen").arg(backend.errorCount).arg(backend.warningCount)
                color: backend.errorCount > 0 ? "#c62828" : palette.text
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
            visible: ((classificationDock.open && classificationDock.parent === leftPane)
                      || (lowerNavDock.open && lowerNavDock.parent === leftPane))
                     && (window.maximized === "" || window.maximized === "classification" || window.maximized === "lowerNav")
            SplitView.fillWidth: window.maximized !== ""

            DockPanel {
                id: classificationDock; objectName: "classificationDock"
                title: qsTr("Ordnungssystem-Navigator")
                open: layoutSettings.classificationOpen
                visible: open && (floating || window.maximized === "" || window.maximized === "classification")
                SplitView.fillHeight: window.maximized === "classification"
                SplitView.minimumHeight: 160
                onTitleDoubleClicked: window.toggleMaximized("classification")

                NavigatorView {
                    id: classificationNavigator; objectName: "classificationNavigator"
                    anchors.fill: parent
                    showTitleBar: false
                    title: qsTr("Ordnungssystem-Navigator")
                    treeModel: classificationModel
                    currentFilter: backend.classificationFilter
                    contextMenu: classificationMenu
                    acceptsFolderDrops: true
                    filters: [
                        { mode: "main_groups", label: "HG", tip: qsTr("Nur Hauptgruppen") },
                        { mode: "positions", label: "OSP", tip: qsTr("Nur Ordnungssystempositionen") },
                        { mode: "positions_with_dossiers", label: "OSP+D", tip: qsTr("Nur Ordnungssystempositionen mit untergeordneten Dossiers") },
                        { mode: "empty_dossiers", label: qsTr("leer"), tip: qsTr("Nur leere Dossiers") }
                    ]
                    onFilterRequested: function (mode) { backend.setClassificationFilter(mode) }
                    onFoldersDropped: function (folderKeys, targetKey) {
                        const targetKind = classificationModel.kindAt(classificationModel.indexOfKey(targetKey))
                        massAssignDialog.start(folderKeys, targetKey, targetKind,
                                               qsTr("Auswahl im Ordnungssystem-Navigator"))
                    }
                    onDeleteRequested: classificationMenu.deleteSelection()
                }
            }

            DockPanel {
                id: lowerNavDock; objectName: "lowerNavDock"
                title: qsTr("Dossier- und Paket-Navigator")
                open: layoutSettings.lowerNavOpen
                visible: open && (floating || window.maximized === "" || window.maximized === "lowerNav")
                SplitView.fillHeight: true
                SplitView.minimumHeight: 160
                onTitleDoubleClicked: window.toggleMaximized("lowerNav")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    TabBar {
                        id: navigatorTabs; objectName: "navigatorTabs"
                        Layout.fillWidth: true
                        TabButton { text: qsTr("Dossier-Navigator") }
                        TabButton { text: qsTr("Paket-Navigator") }
                    }

                    StackLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        currentIndex: navigatorTabs.currentIndex

                        NavigatorView {
                            id: dossierNavigator
                            title: qsTr("Dossiers")
                            showTitleBar: false
                            treeModel: dossierModel
                            columnRatios: [0.45, 0.18, 0.22, 0.15]
                            contextMenu: dossierMenu
                        }

                        NavigatorView {
                            id: packageNavigator; objectName: "packageNavigator"
                            title: qsTr("Paket")
                            showTitleBar: false
                            treeModel: packageModel
                            currentFilter: backend.packageFilter
                            contextMenu: packageNavMenu
                            acceptsFileDrops: backend.hasSip && !backend.readOnly
                            draggableFolders: backend.hasPackage && !backend.readOnly
                            filters: [
                                { mode: "unassigned", label: qsTr("nicht zugewiesen"), tip: qsTr("Nur nicht zugewiesene Dateien") }
                            ]
                            onFilterRequested: function (mode) { backend.setPackageFilter(mode) }
                            onDeleteRequested: packageNavMenu.deleteSelection()
                            onFilesDropped: function (targetKey, urls) { packageNavMenu.importInto(targetKey, urls) }
                        }
                    }
                }
            }
        }

        SplitView {
            id: rightPane
            orientation: Qt.Vertical
            SplitView.fillWidth: true
            visible: ((editorDock.open && editorDock.parent === rightPane)
                      || (actionDock.open && actionDock.parent === rightPane))
                     && (window.maximized === "" || window.maximized === "editor" || window.maximized === "actions")

            DockPanel {
                id: editorDock; objectName: "editorDock"
                title: qsTr("Editor")
                open: layoutSettings.editorOpen
                visible: open && (floating || window.maximized === "" || window.maximized === "editor")
                SplitView.fillHeight: true
                SplitView.minimumHeight: 200
                onTitleDoubleClicked: window.toggleMaximized("editor")

                MetadataEditor {
                    anchors.fill: parent
                    onNewNoteRequested: function (key) { window.askNote([key]) }
                    onShowNotesRequested: function (key) { window.showNotes(key) }
                    onTitleDoubleClicked: window.toggleMaximized("editor")

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
            }

            DockPanel {
                id: actionDock; objectName: "actionDock"
                title: qsTr("Aktionsviews")
                open: layoutSettings.actionsOpen
                visible: open && (floating || window.maximized === "" || window.maximized === "actions")
                SplitView.minimumHeight: 120
                SplitView.fillHeight: window.maximized === "actions"
                onTitleDoubleClicked: window.toggleMaximized("actions")

                ColumnLayout {
                    id: actionPane
                    anchors.fill: parent
                    spacing: 0

                    TabBar {
                        id: actionTabs; objectName: "actionTabs"
                        Layout.fillWidth: true
                        TabButton {
                            text: qsTr("Validierungshilfe") + (backend.errorCount > 0 ? "  \u2716 " + backend.errorCount : "  \u2714")
                            TapHandler { onDoubleTapped: window.toggleMaximized("actions") }
                        }
                        TabButton { text: qsTr("Notiz") + (notesTable.total > 0 ? " (" + notesTable.total + ")" : "") }
                        TabButton { text: qsTr("Stichprobe") }
                        TabButton { text: qsTr("Suche") }
                        TabButton { text: qsTr("Änderungen") + (changesTable.total > 0 ? " (" + changesTable.total + ")" : "") }
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
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- context menus

    Menu {
        id: classificationMenu; objectName: "classificationMenu"

        readonly property int key: classificationNavigator.currentKey
        readonly property string kind: classificationNavigator.currentKind
        readonly property int owner: classificationNavigator.currentOwner
        readonly property bool writable: backend.hasPackage && !backend.readOnly
        property var allowed: []

        onAboutToShow: allowed = structure.allowedChildren(key)

        function create(tag, many) {
            const target = key
            const label = { ordnungssystemposition: qsTr("Ordnungssystempositionen"), dossier: qsTr("Dossiers"),
                            dokument: qsTr("Dokumente"), mappe: qsTr("Mappen") }[tag]
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
        MenuItem { text: qsTr("Ausschneiden (Verschieben)"); enabled: classificationMenu.writable && ["ordnungssystemposition", "dossier", "subdossier", "dokument", "mappe"].indexOf(classificationMenu.kind) >= 0; onTriggered: structure.cut(classificationNavigator.selectedKeys()) }
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
        readonly property int key: packageNavigator.currentKey
        readonly property string kind: packageNavigator.currentKind
        readonly property bool writable: backend.hasSip && !backend.readOnly
        property int importTarget: 0
        property var importUrls: []

        function deleteSelection() {
            const keys = packageNavigator.selectedKeys()
            window.confirm(qsTr("%1 Ordner/Datei(en) endgültig aus dem Paket und dem Dateisystem löschen?").arg(keys.length),
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

        MenuItem { text: qsTr("Neuer Ordner..."); enabled: packageNavMenu.writable && packageNavMenu.kind === "ordner"; onTriggered: { const parent = packageNavMenu.key; inputDialog.ask(qsTr("Neuer Ordner"), qsTr("Name (erlaubt: A-Z a-z 0-9 _ . -)"), "", name => fileOps.newFolder(parent, name)) } }
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
            messageDialog.text = text
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
                messageDialog.text = qsTr("Es wurden keine gleichnamigen Dateien gefunden.")
                messageDialog.open()
                return
            }
            const folder = selectedFolder
            window.confirm(qsTr("Für folgende Dateien wurde ein Ersatz gefunden:\n%1\n\nDateien ersetzen?").arg(found.join("\n")),
                           () => fileOps.replaceFiles(folder))
        }
    }

    InputDialog { id: inputDialog; objectName: "inputDialog" }
    NewPackageDialog { id: newPackageDialog; objectName: "newPackageDialog" }
    MassAssignDialog { id: massAssignDialog; objectName: "massAssignDialog" }
    MassEditDialog { id: massEditDialog; objectName: "massEditDialog" }
    PreferencesDialog { id: preferencesDialog; objectName: "preferencesDialog" }

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

    MessageDialog { id: messageDialog; buttons: MessageDialog.Ok }

    MessageDialog {
        id: confirmDialog
        property var action: null
        title: qsTr("Bestätigen")
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: if (action) action()
    }

    MessageDialog {
        id: mergeDialog
        title: qsTr("Ordner zusammenführen")
        buttons: MessageDialog.Yes | MessageDialog.No | MessageDialog.Cancel
        onButtonClicked: function (button, role) {
            if (button === MessageDialog.Yes)
                fileOps.importUrls(packageNavMenu.importTarget, packageNavMenu.importUrls, true, true)
            else if (button === MessageDialog.No)
                fileOps.importUrls(packageNavMenu.importTarget, packageNavMenu.importUrls, false, false)
        }
    }

    MessageDialog {
        id: invalidOnOpenDialog
        title: qsTr("Gültigkeitsprüfung fehlgeschlagen")
        text: qsTr("Das Paket entspricht noch nicht allen Anforderungen. Die Details sind in der Validierungshilfe ersichtlich.")
        buttons: MessageDialog.Ok
        onAccepted: fullValidationDialog.open()
    }

    MessageDialog {
        id: fullValidationDialog
        title: qsTr("Paket vollständig validieren")
        text: qsTr("Soll das Paket vollständig validiert werden?")
        informativeText: qsTr("Die Validierung kann bei grösseren Paketen einige Zeit in Anspruch nehmen.")
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: backend.validate(true)
    }

    MessageDialog {
        id: validityDialog
        title: qsTr("Gültigkeitsprüfung fehlgeschlagen")
        text: qsTr("Alle Fehler sind behoben. Soll das Paket gespeichert und erneut vollständig validiert werden?")
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: {
            if (!backend.readOnly)
                backend.save()
            backend.validate(true)
        }
    }

    MessageDialog {
        id: unsavedDialog
        title: qsTr("Änderungen speichern")
        text: qsTr("Die Metadaten wurden geändert. Sollen die Änderungen gespeichert werden?")
        buttons: MessageDialog.Save | MessageDialog.Discard | MessageDialog.Cancel
        onButtonClicked: function (button, role) {
            if (button === MessageDialog.Save) {
                if (backend.save())
                    window.proceedAfterSave()
            } else if (button === MessageDialog.Discard) {
                window.proceedAfterSave()
            } else {
                window.pendingAction = null
            }
        }
    }

    MessageDialog {
        id: errorsOnCloseDialog
        title: qsTr("Paket schliessen")
        text: qsTr("Das Paket entspricht noch nicht vollständig den Anforderungen des Archivs. Trotzdem schliessen?")
        buttons: MessageDialog.Ok | MessageDialog.Cancel
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
            ProgressBar { Layout.fillWidth: true; from: 0; to: 100; value: backend.progress }
            Button { text: qsTr("Abbrechen"); Layout.alignment: Qt.AlignHCenter; onClicked: backend.cancelTask() }
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
