import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    title: qsTr("Ältere Sicherungskopien entfernen")
    anchors.centerIn: Overlay.overlay
    width: Math.min(680, Overlay.overlay.width - 40)
    height: Math.min(460, Overlay.overlay.height - 40)
    modal: true

    ColumnLayout {
        anchors.fill: parent
        spacing: 12
        Label {
            Layout.fillWidth: true
            text: backend.retentionCandidates.length === 1
                ? qsTr("1 Kopie · %1 Byte").arg(backend.retentionBytes)
                : qsTr("%1 Kopien · %2 Byte").arg(backend.retentionCandidates.length).arg(backend.retentionBytes)
            font.bold: true
        }
        Label {
            Layout.fillWidth: true
            text: backend.retentionProtectedCount === 1
                ? qsTr("1 Verzeichnis geschützt")
                : qsTr("%1 Verzeichnisse geschützt").arg(backend.retentionProtectedCount)
        }
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: backend.retentionCandidates
            ScrollBar.vertical: ScrollBar {}
            delegate: Item {
                required property var modelData
                width: ListView.view.width
                height: 58
                ColumnLayout {
                    anchors.fill: parent
                    RowLayout {
                        Label {
                            id: backupPathLabel
                            Layout.fillWidth: true
                            text: modelData.path
                            elide: Text.ElideMiddle
                            ToolTip.visible: pathHover.hovered && truncated
                            ToolTip.text: text
                            HoverHandler { id: pathHover }
                        }
                        Label { text: qsTr("%1 Byte").arg(modelData.bytes) }
                    }
                    Label { text: modelData.archived; color: palette.placeholderText }
                    Rectangle { Layout.fillWidth: true; height: 1; color: palette.mid }
                }
            }
        }
    }

    footer: DialogButtonBox {
        Button {
            objectName: "applyCleanupButton"
            text: qsTr("Entfernen")
            DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
            enabled: backend.retentionCandidates.length > 0 && !backend.busy && !backend.readOnly
        }
        Button { text: qsTr("Abbrechen"); DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
    }
    onAccepted: backend.applyRetentionCleanup()
}