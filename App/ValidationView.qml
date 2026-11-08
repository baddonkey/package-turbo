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
                id: issueCount
                Layout.preferredWidth: 190
                Layout.minimumWidth: 110
                leftPadding: 6
                text: backend.validationFilter === ""
                      ? qsTr("%1 Fehler, %2 Warnungen").arg(backend.errorCount).arg(backend.warningCount)
                      : qsTr("%1 von %2 Einträgen").arg(backend.visibleIssueCount).arg(backend.errorCount + backend.warningCount)
                elide: Text.ElideRight
                ToolTip.visible: countHover.hovered && truncated
                ToolTip.text: text
                HoverHandler { id: countHover }
            }

            Item { Layout.fillWidth: true }

            ComboBox {
                Layout.preferredWidth: 220
                Layout.minimumWidth: 145
                Layout.maximumWidth: 245
                model: [qsTr("Alle anzeigen")].concat(backend.checkNames)
                currentIndex: backend.validationFilter === "" ? 0 : backend.checkNames.indexOf(backend.validationFilter) + 1
                ToolTip.visible: hovered && currentText.length > 0
                ToolTip.text: currentText
                onActivated: function (index) {
                    backend.setValidationFilter(index === 0 ? "" : backend.checkNames[index - 1])
                }
            }

            ToolButton {
                icon.source: "icons/copy.svg"
                icon.color: palette.buttonText
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Die selektierten Zeilen in die Zwischenablage kopieren")
                onClicked: table.copySelection()
            }

            ToolButton {
                icon.source: "icons/download.svg"
                icon.color: palette.buttonText
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
                        confirmFix.message = qsTr("«%1» ausführen? Diese Aktion verändert das Paket im Dateisystem bzw. löscht Daten.")
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

    MessageBox {
        id: confirmFix
        property string action: ""
        property var rows: []
        title: qsTr("Bestätigen")
        buttonSet: "okCancel"
        onAccepted: fileOps.applyFix(action, rows)
    }
}
