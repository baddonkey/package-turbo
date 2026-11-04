import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One navigator (Ordnungssystem, Dossier or Paket): view menu, tree with multi-selection and context menu.
Pane {
    id: root

    property string title: ""
    property bool showTitleBar: true
    property var treeModel: null
    property var filters: []
    property string currentFilter: "all"
    property var columnRatios: [1.0]
    property Menu contextMenu: null
    property bool acceptsFileDrops: false
    property bool acceptsFolderDrops: false
    property bool draggableFolders: false
    property var draggedFolderKeys: []

    readonly property int currentKey: treeView.selectionModel.currentIndex.valid
                                      ? treeModel.keyAt(treeView.selectionModel.currentIndex) : 0
    readonly property string currentKind: treeView.selectionModel.currentIndex.valid
                                          ? treeModel.kindAt(treeView.selectionModel.currentIndex) : ""
    readonly property int currentOwner: treeView.selectionModel.currentIndex.valid
                                        ? treeModel.ownerAt(treeView.selectionModel.currentIndex) : 0
    property var expandedKeys: []

    signal filterRequested(string mode)
    signal titleDoubleClicked()
    signal filesDropped(int targetKey, var urls)
    signal foldersDropped(var folderKeys, int targetKey)
    signal deleteRequested()

    padding: 0

    function selectedKeys() {
        const rows = treeView.selectionModel.selectedRows(0)
        const keys = []
        for (let i = 0; i < rows.length; ++i) {
            const key = treeModel.keyAt(rows[i])
            if (key && keys.indexOf(key) < 0)
                keys.push(key)
        }
        if (keys.length === 0 && currentKey)
            keys.push(currentKey)
        return keys
    }

    function selectedKinds() {
        const rows = treeView.selectionModel.selectedRows(0)
        const kinds = []
        for (let i = 0; i < rows.length; ++i)
            kinds.push(treeModel.kindAt(rows[i]))
        if (kinds.length === 0 && currentKind)
            kinds.push(currentKind)
        return kinds
    }

    function selectedFolderKeys() {
        const rows = treeView.selectionModel.selectedRows(0)
        const keys = []
        for (const index of rows) {
            if (treeModel.kindAt(index) === "ordner") {
                const key = treeModel.keyAt(index)
                if (key && keys.indexOf(key) < 0)
                    keys.push(key)
            }
        }
        if (keys.length === 0 && currentKind === "ordner")
            keys.push(currentKey)
        return keys
    }

    function beginFolderDrag(row, key) {
        const index = treeView.index(row, 0)
        if (!treeView.selectionModel.isRowSelected(row, index.parent))
            treeView.selectionModel.setCurrentIndex(index, ItemSelectionModel.ClearAndSelect | ItemSelectionModel.Rows)
        draggedFolderKeys = selectedFolderKeys()
        if (draggedFolderKeys.length === 0)
            draggedFolderKeys = [key]
    }

    function copySelection() {
        backend.copyToClipboard(treeModel.rowsToTsv(treeView.selectionModel.selectedRows(0)))
    }

    function revealKey(key) {
        const index = treeModel.indexOfKey(key)
        if (!index.valid)
            return false
        treeView.expandToIndex(index)
        treeView.forceLayout()
        const row = treeView.rowAtIndex(index)
        if (row >= 0)
            treeView.positionViewAtRow(row, TableView.Contain)
        treeView.selectionModel.setCurrentIndex(index, ItemSelectionModel.ClearAndSelect | ItemSelectionModel.Rows)
        return true
    }

    function rememberExpansion() {
        const keys = []
        for (let row = 0; row < treeView.rows; ++row) {
            if (treeView.isExpanded(row))
                keys.push(treeModel.keyAt(treeView.index(row, 0)))
        }
        expandedKeys = keys
    }

    function restoreExpansion() {
        if (treeView.rows === 0 && treeModel && treeModel.itemCount() > 0 && restoreTimer.attempts < 20) {
            restoreTimer.attempts++
            restoreTimer.start()
            return
        }
        restoreTimer.attempts = 0
        for (const key of expandedKeys) {
            const index = treeModel.indexOfKey(key)
            if (!index.valid)
                continue
            treeView.expandToIndex(index)
            const row = treeView.rowAtIndex(index)
            if (row >= 0)
                treeView.expand(row)
        }
        if (expandedKeys.length === 0 && treeView.rows > 0)
            treeView.expand(0)
    }

    Connections {
        target: root.treeModel
        function onModelAboutToBeReset() { root.rememberExpansion() }
        function onRebuilt() { Qt.callLater(root.restoreExpansion) }
    }

    // TreeView populates its rows asynchronously after a model reset.
    Timer { id: restoreTimer; property int attempts: 0; interval: 50; onTriggered: root.restoreExpansion() }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ToolBar {
            Layout.fillWidth: true
            visible: root.showTitleBar

            RowLayout {
                anchors.fill: parent
                spacing: 2

                Label {
                    text: root.title
                    font.bold: true
                    leftPadding: 6
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                    TapHandler { onDoubleTapped: root.titleDoubleClicked() }
                    ToolTip.visible: titleHover.hovered
                    ToolTip.delay: 800
                    ToolTip.text: qsTr("Doppelklick: Ansicht maximieren / wiederherstellen")
                    HoverHandler { id: titleHover }
                }

                Repeater {
                    model: root.filters

                    ToolButton {
                        required property var modelData
                        text: modelData.label
                        checkable: true
                        checked: root.currentFilter === modelData.mode
                        font.pixelSize: 11
                        ToolTip.visible: hovered
                        ToolTip.text: modelData.tip
                        onClicked: root.filterRequested(checked ? modelData.mode : "all")
                    }
                }

                ToolButton {
                    text: "+"
                    font.bold: true
                    enabled: root.treeModel && root.treeModel.itemCount() <= backend.expandThreshold
                    ToolTip.visible: hovered
                    ToolTip.text: enabled ? qsTr("Alles aufklappen")
                                          : qsTr("Alles aufklappen ist deaktiviert (Schwellwert überschritten)")
                    onClicked: treeView.expandRecursively()
                }

                ToolButton {
                    text: "\u2212"
                    font.bold: true
                    ToolTip.visible: hovered
                    ToolTip.text: qsTr("Alles zuklappen")
                    onClicked: treeView.collapseRecursively()
                }
            }
        }

        HorizontalHeaderView {
            id: header
            Layout.fillWidth: true
            syncView: treeView
            clip: true
            visible: root.columnRatios.length > 1
        }

        TreeView {
            id: treeView

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.treeModel
            alternatingRows: false
            boundsBehavior: Flickable.StopAtBounds
            selectionBehavior: TableView.SelectRows
            selectionMode: TableView.ExtendedSelection
            focus: true

            selectionModel: ItemSelectionModel {
                model: treeView.model
                onCurrentChanged: function (current, previous) {
                    if (current.valid)
                        backend.select(root.treeModel.keyAt(current))
                }
            }

            columnWidthProvider: function (column) {
                if (column >= root.columnRatios.length)
                    return 0
                return Math.max(80, treeView.width * root.columnRatios[column])
            }
            onWidthChanged: forceLayout()

            Keys.onDeletePressed: root.deleteRequested()
            Keys.onPressed: function (event) {
                if (event.matches(StandardKey.Copy)) {
                    root.copySelection()
                    event.accepted = true
                }
            }

            ScrollBar.vertical: ScrollBar {}
            ScrollBar.horizontal: ScrollBar {}

            delegate: TreeViewDelegate {
                id: cell

                required property var kind
                required property var elementKey
                required property var flag
                required property var label
                required property var hasNote

                // The style declares row/column/current itself; they are not reachable via the id.
                readonly property int columnIndex: column
                readonly property int rowIndex: row
                readonly property bool isCurrent: current
                readonly property bool isSelected: selected

                implicitHeight: 24

                contentItem: RowLayout {
                    spacing: 6

                    KindBadge {
                        visible: cell.columnIndex === 0 && !!cell.kind
                        kind: cell.kind || ""
                        assigned: cell.flag === "assigned"
                    }

                    Label {
                        Layout.fillWidth: true
                        text: cell.label ?? ""
                        elide: Text.ElideRight
                        color: cell.flag === "unassigned" ? "#c62828"
                             : (cell.isCurrent || cell.isSelected) ? palette.highlightedText : palette.text
                        font.italic: cell.flag === "unassigned"
                    }

                    Label {
                        visible: cell.columnIndex === 0 && cell.hasNote === true
                        text: "N"
                        font.bold: true
                        color: "#ef6c00"
                        ToolTip.visible: noteHover.hovered
                        ToolTip.text: qsTr("Zu diesem Objekt ist eine Notiz erfasst")
                        HoverHandler { id: noteHover }
                    }
                }

                DragHandler {
                    id: folderDrag
                    enabled: root.draggableFolders && cell.kind === "ordner"
                    target: null
                    onActiveChanged: {
                        if (active)
                            root.beginFolderDrag(cell.rowIndex, cell.elementKey)
                        else
                            root.draggedFolderKeys = []
                    }
                }

                Drag.active: folderDrag.active && root.draggedFolderKeys.length > 0
                Drag.source: cell
                Drag.keys: ["package-folder"]
                Drag.mimeData: ({ "application/x-package-folder-keys": root.draggedFolderKeys.join(",") })

                property bool folderDropHover: false
                DropArea {
                    anchors.fill: parent
                    z: 1
                    enabled: root.acceptsFolderDrops && cell.columnIndex === 0
                    keys: ["package-folder"]
                    onEntered: cell.folderDropHover = true
                    onExited: cell.folderDropHover = false
                    onDropped: function (drop) {
                        const folderKeys = drop.getDataAsString("application/x-package-folder-keys")
                                                .split(",").map(Number)
                                                .filter(key => Number.isInteger(key) && key > 0)
                        if (folderKeys.length > 0) {
                            const targetIndex = treeView.index(cell.rowIndex, 0)
                            treeView.selectionModel.setCurrentIndex(
                                targetIndex, ItemSelectionModel.ClearAndSelect | ItemSelectionModel.Rows
                            )
                            root.foldersDropped(folderKeys, cell.elementKey)
                            drop.acceptProposedAction()
                        }
                    }
                    Rectangle {
                        anchors.fill: parent
                        visible: cell.folderDropHover
                        color: "transparent"
                        border.color: palette.highlight
                    }
                }

                onDoubleClicked: {
                    if (cell.kind === "datei")
                        backend.openFile(cell.elementKey)
                }

                TapHandler {
                    acceptedButtons: Qt.RightButton
                    onTapped: {
                        const index = treeView.index(cell.rowIndex, 0)
                        if (!treeView.selectionModel.isRowSelected(cell.rowIndex, index.parent))
                            treeView.selectionModel.setCurrentIndex(index, ItemSelectionModel.ClearAndSelect | ItemSelectionModel.Rows)
                        else
                            treeView.selectionModel.setCurrentIndex(index, ItemSelectionModel.NoUpdate)
                        if (root.contextMenu)
                            root.contextMenu.popup()
                    }
                }
            }
        }
    }

    DropArea {
        anchors.fill: parent
        enabled: root.acceptsFileDrops
        keys: ["text/uri-list"]
        onDropped: function (drop) {
            if (drop.hasUrls) {
                root.filesDropped(root.currentKey, drop.urls)
                drop.acceptProposedAction()
            }
        }
    }
}
