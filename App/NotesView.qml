import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

// Action view "Notiz" (14.1): list, edit and delete notes.
ColumnLayout {
    id: root

    signal exportRequested()
    signal editRequested(int noteKey, string text)

    spacing: 0

    function highlightOwner(key) {
        table.selectRowWithKey(key)
    }

    ToolBar {
        Layout.fillWidth: true
        RowLayout {
            anchors.fill: parent
            Label { leftPadding: 6; text: qsTr("%1 Notizen").arg(notesTable.total); Layout.fillWidth: true }
            ToolButton {
                text: qsTr("Notiz löschen")
                enabled: table.selectedRows.length > 0 && !backend.readOnly
                onClicked: confirmDelete.open()
            }
            ToolButton { text: qsTr("Kopieren"); onClicked: table.copySelection() }
            ToolButton { text: qsTr("Export"); onClicked: root.exportRequested() }
        }
    }

    DataTable {
        id: table
        Layout.fillWidth: true
        Layout.fillHeight: true
        tableModel: notesTable
        columnRatios: [0.12, 0.25, 0.38, 0.12, 0.13]
        onRowActivated: function (row) { backend.reveal(notesTable.recordAt(row).key) }
        onRowContextMenu: function (row) { noteMenu.popup() }
    }

    Menu {
        id: noteMenu
        MenuItem {
            text: qsTr("Notiz bearbeiten...")
            enabled: table.selectedRows.length === 1 && !backend.readOnly
            onTriggered: {
                const record = notesTable.recordAt(table.selectedRows[0])
                root.editRequested(record.noteKey, record.comment)
            }
        }
        MenuItem {
            text: qsTr("Notiz löschen")
            enabled: table.selectedRows.length > 0 && !backend.readOnly
            onTriggered: confirmDelete.open()
        }
        MenuItem {
            text: qsTr("Objekt anzeigen")
            onTriggered: backend.reveal(notesTable.recordAt(table.selectedRows[0]).key)
        }
    }

    MessageBox {
        id: confirmDelete
        title: qsTr("Notizen löschen")
        message: qsTr("Sollen die ausgewählten Notizen gelöscht werden?")
        buttonSet: "yesNo"
        onActionChosen: function (action) {
            if (action === "yes")
                notesCtl.deleteNotes(table.selectedRows.map(r => notesTable.recordAt(r).noteKey))
        }
    }
}
