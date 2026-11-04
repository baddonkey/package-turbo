import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

// Action view "Validierungshilfe" with filter and fix-up commands.
ColumnLayout {
    id: root

    signal exportRequested()

    property var actions: []

    spacing: 0

    ToolBar {
        Layout.fillWidth: true

        RowLayout {
            anchors.fill: parent
            spacing: 6

            Label {
                leftPadding: 6
                text: backend.validationFilter === ""
                      ? qsTr("%1 Fehler, %2 Warnungen").arg(backend.errorCount).arg(backend.warningCount)
                      : qsTr("%1 von %2 Einträgen").arg(backend.visibleIssueCount).arg(backend.errorCount + backend.warningCount)
            }

            Item { Layout.fillWidth: true }

            ComboBox {
                Layout.preferredWidth: 280
                model: [qsTr("Alle anzeigen")].concat(backend.checkNames)
                currentIndex: backend.validationFilter === "" ? 0 : backend.checkNames.indexOf(backend.validationFilter) + 1
                onActivated: function (index) {
                    backend.setValidationFilter(index === 0 ? "" : backend.checkNames[index - 1])
                }
            }

            ToolButton {
                text: qsTr("Kopieren")
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Die selektierten Zeilen in die Zwischenablage kopieren")
                onClicked: table.copySelection()
            }

            ToolButton {
                text: qsTr("Export")
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Tabelle nach Excel (CSV) exportieren")
                onClicked: root.exportRequested()
            }
        }
    }

    DataTable {
        id: table
        Layout.fillWidth: true
        Layout.fillHeight: true
        tableModel: validationTable
        columnRatios: [0.06, 0.1, 0.16, 0.14, 0.32, 0.1, 0.12]

        onRowActivated: function (row) { backend.reveal(validationTable.recordAt(row).key) }
        onRowContextMenu: function (row) {
            root.actions = fileOps.fixActions(row)
            issueMenu.popup()
        }
    }

    Menu {
        id: issueMenu

        MenuItem {
            text: qsTr("Im Editor anzeigen")
            enabled: table.selectedKeys().length > 0
            onTriggered: backend.reveal(table.selectedKeys()[0])
        }
        MenuSeparator { visible: root.actions.length > 0 }

        Instantiator {
            model: root.actions
            delegate: MenuItem {
                required property var modelData
                text: modelData.label
                onTriggered: {
                    if (modelData.confirm) {
                        confirmFix.action = modelData.id
                        confirmFix.rows = table.selectedRows.slice()
                        confirmFix.text = qsTr("«%1» ausführen? Diese Aktion verändert das Paket im Dateisystem bzw. löscht Daten.")
                                          .arg(modelData.label)
                        confirmFix.open()
                    } else {
                        fileOps.applyFix(modelData.id, table.selectedRows)
                    }
                }
            }
            onObjectAdded: function (index, object) { issueMenu.insertItem(index + 2, object) }
            onObjectRemoved: function (index, object) { issueMenu.removeItem(object) }
        }
    }

    MessageDialog {
        id: confirmFix
        property string action: ""
        property var rows: []
        title: qsTr("Bestätigen")
        buttons: MessageDialog.Ok | MessageDialog.Cancel
        onAccepted: fileOps.applyFix(action, rows)
    }
}
