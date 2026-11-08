import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Sortable table for the action views; double click navigates to the referenced object.
ColumnLayout {
    id: root

    property var tableModel: null
    property var columnRatios: []
    property var selectedRows: []
    property int anchorRow: -1
    property int columnsRevision: 0
    property int sortRevision: 0

    signal rowActivated(int row)
    signal rowContextMenu(int row)

    spacing: 0

    function selectedKeys() {
        return selectedRows.map(r => tableModel.recordAt(r).key).filter(k => !!k)
    }

    function copySelection() {
        const rows = selectedRows.length > 0 ? selectedRows : [...Array(tableModel.visibleCount()).keys()]
        backend.copyToClipboard(tableModel.rowsToTsv(rows))
    }

    function selectRowWithKey(key) {
        const row = tableModel.rowOfKey(key)
        if (row < 0)
            return
        selectedRows = [row]
        table.positionViewAtRow(row, TableView.Contain)
    }

    Connections {
        target: root.tableModel
        function onModelReset() { root.selectedRows = [] }
        function onColumnsChanged() { root.columnsRevision++; table.forceLayout() }
        function onSortChanged() { root.sortRevision++ }
        function onLayoutChanged() { root.selectedRows = [] }
    }

    Shortcut {
        sequences: [StandardKey.Copy]
        enabled: table.activeFocus
        onActivated: root.copySelection()
    }

    HorizontalHeaderView {
        id: header
        Layout.fillWidth: true
        Layout.preferredHeight: 38
        syncView: table
        clip: true

        delegate: Rectangle {
            id: headerCell
            required property int index
            required property var display

            implicitHeight: 38
            implicitWidth: 80
            color: palette.button
            border.color: palette.mid

            Label {
                id: headingLabel
                objectName: "tableHeadingLabel"
                anchors.fill: parent
                anchors.margins: 4
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.WrapAnywhere
                maximumLineCount: 2
                font.pixelSize: 10
                elide: Text.ElideRight
                font.bold: true
                text: (headerCell.display ?? "") + " " + (root.sortRevision >= 0 ? root.tableModel.sortIndicator(headerCell.index) : "")
            }

            TapHandler {
                acceptedButtons: Qt.LeftButton
                onTapped: {
                    const m = point.modifiers
                    const mode = (m & Qt.AltModifier) ? "alt" : (m & Qt.ControlModifier) ? "ctrl"
                               : (m & Qt.ShiftModifier) ? "shift" : ""
                    root.tableModel.sortClick(headerCell.index, mode)
                }
            }
            TapHandler {
                acceptedButtons: Qt.RightButton
                onTapped: columnMenu.popup()
            }

            ToolTip.visible: headerHover.hovered
            ToolTip.delay: 800
            ToolTip.text: headingLabel.truncated ? headerCell.display
                           : qsTr("Klick: sortieren / Richtung wechseln, Ctrl/Shift+Klick: Priorität ändern, Alt+Klick: Sortierung aufheben, Rechtsklick: Spalten")
            HoverHandler { id: headerHover }
        }
    }

    TableView {
        id: table

        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: root.tableModel
        boundsBehavior: Flickable.StopAtBounds
        columnSpacing: 0
        rowSpacing: 0
        focus: true

        columnWidthProvider: function (column) {
            if (root.columnsRevision >= 0 && !root.tableModel.isColumnVisible(column))
                return 0
            const ratio = column < root.columnRatios.length ? root.columnRatios[column] : 0.1
            return Math.max(40, table.width * ratio)
        }
        onWidthChanged: forceLayout()

        ScrollBar.vertical: ScrollBar {}
        ScrollBar.horizontal: ScrollBar {}

        delegate: Rectangle {
            id: cell

            required property int row
            required property int column
            required property var display
            required property var severity

            readonly property bool isSelected: root.selectedRows.indexOf(row) >= 0

            implicitHeight: 24
            color: isSelected ? palette.highlight : (row % 2 ? Qt.tint(palette.base, Qt.alpha(palette.text, 0.05)) : palette.base)

            Label {
                id: cellLabel
                anchors.fill: parent
                anchors.leftMargin: 6
                anchors.rightMargin: 4
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                text: cell.display ?? ""
                font.bold: cell.column === 0 && cell.severity === "error"
                color: cell.isSelected ? palette.highlightedText
                     : (cell.column === 0 && cell.severity === "error") ? palette.brightText
                     : (cell.column === 0 && cell.severity === "warning") ? palette.link
                     : palette.text
            }

            ToolTip.visible: hover.hovered && cellLabel.truncated
            ToolTip.text: cell.display ?? ""
            ToolTip.delay: 600

            HoverHandler { id: hover }

            TapHandler {
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onTapped: function (eventPoint, button) {
                    table.forceActiveFocus()
                    const ctrl = (point.modifiers & Qt.ControlModifier) !== 0
                    const shift = (point.modifiers & Qt.ShiftModifier) !== 0
                    if (button === Qt.RightButton) {
                        if (!cell.isSelected)
                            root.selectedRows = [cell.row]
                        root.rowContextMenu(cell.row)
                        return
                    }
                    if (shift && root.anchorRow >= 0) {
                        const rows = []
                        for (let r = Math.min(root.anchorRow, cell.row); r <= Math.max(root.anchorRow, cell.row); ++r)
                            rows.push(r)
                        root.selectedRows = rows
                    } else if (ctrl) {
                        const rows = root.selectedRows.slice()
                        const i = rows.indexOf(cell.row)
                        if (i >= 0) rows.splice(i, 1); else rows.push(cell.row)
                        root.selectedRows = rows
                        root.anchorRow = cell.row
                    } else {
                        root.selectedRows = [cell.row]
                        root.anchorRow = cell.row
                    }
                }
                onDoubleTapped: root.rowActivated(cell.row)
            }
        }
    }

    Menu {
        id: columnMenu

        MenuItem {
            text: qsTr("Die selektierten Zeilen in die Zwischenablage kopieren")
            onTriggered: root.copySelection()
        }
        MenuSeparator {}

        Instantiator {
            model: root.columnsRevision >= 0 && root.tableModel ? root.tableModel.columnLabels() : []
            delegate: MenuItem {
                required property var modelData
                required property int index
                text: modelData
                checkable: true
                checked: root.columnsRevision >= 0 && root.tableModel.isColumnVisible(index)
                onTriggered: root.tableModel.setColumnVisible(index, checked)
            }
            // The first two entries are the copy command and the separator.
            onObjectAdded: function (index, object) { columnMenu.insertItem(index + 2, object) }
            onObjectRemoved: function (index, object) { columnMenu.removeItem(object) }
        }
    }
}
