import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One navigator (Ordnungssystem, Dossier or Paket): view menu, tree with multi-selection and context menu.
Pane {
    id: root

    property string title: ""
    property var treeModel: null
    property var filters: []
    property string currentFilter: "all"
    property var columnRatios: [1.0]
    property Menu contextMenu: null
    property bool acceptsFileDrops: false

    readonly property var filterOptions: [{ mode: "all", label: qsTr("Alle anzeigen") }].concat(root.filters)
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
                    ToolTip.text: qsTr("%1 — Doppelklick: Ansicht maximieren / wiederherstellen").arg(root.title)
                    HoverHandler { id: titleHover }
                }

                ComboBox {
                    visible: root.filters.length > 0
                    Layout.preferredWidth: 190
                    Layout.minimumWidth: 140
                    Layout.maximumWidth: 230
                    model: root.filterOptions
                    textRole: "label"
                    currentIndex: {
                        const index = root.filterOptions.findIndex(option =>
                            option.mode === root.currentFilter || (root.currentFilter === "" && option.mode === "all"))
                        return Math.max(0, index)
                    }
                    onActivated: function (index) { root.filterRequested(root.filterOptions[index].mode) }
                    ToolTip.visible: hovered && currentIndex >= 0
                    ToolTip.text: currentIndex >= 0 ? root.filterOptions[currentIndex].label : ""
                }

                ToolButton {
                    icon.source: "icons/plus.svg"
                    icon.color: palette.buttonText
                    enabled: root.treeModel && root.treeModel.itemCount() <= backend.expandThreshold
                    ToolTip.visible: hovered
                    ToolTip.text: enabled ? qsTr("Alles aufklappen")
                                          : qsTr("Alles aufklappen ist deaktiviert (Schwellwert überschritten)")
                    onClicked: treeView.expandRecursively()
                }

                ToolButton {
                    icon.source: "icons/minus.svg"
                    icon.color: palette.buttonText
                    ToolTip.visible: hovered
                    ToolTip.text: qsTr("Alles zuklappen")
                    onClicked: treeView.collapseRecursively()
                }
            }
        }

        HorizontalHeaderView {
            id: header
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            syncView: treeView
            clip: true
            visible: root.columnRatios.length > 1

            delegate: Rectangle {
                id: headerCell
                required property int index
                required property var display

                implicitWidth: 80
                implicitHeight: 48
                color: palette.button
                border.color: palette.mid

                Label {
                    id: headerLabel
                    objectName: "navigatorHeadingLabel"
                    anchors.fill: parent
                    anchors.margins: 3
                    text: headerCell.display ?? ""
                    font.bold: true
                    font.pixelSize: 10
                    wrapMode: Text.WrapAnywhere
                    maximumLineCount: 3
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                }

                ToolTip.visible: headerHover.hovered && headerLabel.truncated
                ToolTip.text: headerCell.display ?? ""
                HoverHandler { id: headerHover }
            }
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
                        id: treeLabel
                        Layout.fillWidth: true
                        text: cell.label ?? ""
                        elide: Text.ElideRight
                            color: (cell.isCurrent || cell.isSelected) ? palette.highlightedText
                                : cell.flag === "unassigned" ? palette.brightText : palette.text
                        font.italic: cell.flag === "unassigned"
                            ToolTip.visible: cellHover.hovered && truncated
                            ToolTip.text: text
                            HoverHandler { id: cellHover }
                    }

                    Label {
                        visible: cell.columnIndex === 0 && cell.hasNote === true
                        text: "N"
                        font.bold: true
                        color: (cell.isCurrent || cell.isSelected) ? palette.highlightedText : palette.link
                        ToolTip.visible: noteHover.hovered
                        ToolTip.text: qsTr("Zu diesem Objekt ist eine Notiz erfasst")
                        HoverHandler { id: noteHover }
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
