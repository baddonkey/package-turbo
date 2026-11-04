import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Action view "Stichprobe" (14.2).
ColumnLayout {
    id: root

    signal exportRequested()

    spacing: 0

    ToolBar {
        Layout.fillWidth: true
        RowLayout {
            anchors.fill: parent
            Label {
                leftPadding: 6
                Layout.fillWidth: true
                text: qsTr("%1 Dossiers (Vorgabe: %2 %3)").arg(sampleTable.total).arg(backend.sampleSize)
                      .arg(backend.sampleMode === "percent" ? "%" : qsTr("Dossiers"))
            }
            ToolButton {
                text: qsTr("Neue Auswahl")
                enabled: backend.hasPackage
                onClicked: searchCtl.drawSample()
            }
            ToolButton { text: qsTr("Kopieren"); onClicked: table.copySelection() }
            ToolButton { text: qsTr("Export"); onClicked: root.exportRequested() }
        }
    }

    DataTable {
        id: table
        Layout.fillWidth: true
        Layout.fillHeight: true
        tableModel: sampleTable
        columnRatios: [0.15, 0.25, 0.6]
        onRowActivated: function (row) { backend.reveal(sampleTable.recordAt(row).key) }
    }
}
