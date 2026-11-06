import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    spacing: 0

    signal detailsRequested(string text)
    signal cleanupRequested()

    ToolBar {
        Layout.fillWidth: true
        RowLayout {
            anchors.fill: parent
            Label {
                Layout.fillWidth: true
                leftPadding: 6
                text: qsTr("%1 Ereignisse").arg(historyTable.total)
            }
            ToolButton {
                text: qsTr("Kopieren")
                enabled: historyTable.total > 0
                onClicked: table.copySelection()
            }
            ToolButton {
                text: qsTr("Wiederherstellen")
                enabled: backend.hasSip && !backend.readOnly && !backend.busy
                onClicked: backend.recoverMetadata()
            }
            ToolButton {
                objectName: "cleanupPreviewButton"
                text: qsTr("Speicher bereinigen...")
                enabled: backend.hasSip && !backend.readOnly && !backend.busy
                onClicked: {
                    if (backend.previewRetentionCleanup())
                        root.cleanupRequested()
                }
            }
        }
    }

    Label {
        Layout.fillWidth: true
        Layout.margins: 6
        visible: backend.auditCompanion.length > 0
        text: backend.auditCompanion
        elide: Text.ElideMiddle
        ToolTip.visible: companionHover.hovered
        ToolTip.text: backend.auditCompanion
        HoverHandler { id: companionHover }
    }

    DataTable {
        id: table
        objectName: "historyView"
        Layout.fillWidth: true
        Layout.fillHeight: true
        tableModel: historyTable
        columnRatios: [0.17, 0.2, 0.14, 0.1, 0.11, 0.14, 0.14]
        onRowActivated: function(row) { root.detailsRequested(backend.historyDetails(row)) }
    }
}