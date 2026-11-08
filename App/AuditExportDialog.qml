import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root
    signal premisExportRequested(bool redactValues)
    signal bundleExportRequested(bool redactValues, string metsVersion)

    objectName: "auditExportDialog"
    title: qsTr("PREMIS/METS exportieren")
    modal: true
    anchors.centerIn: Overlay.overlay
    width: 540
    standardButtons: Dialog.Cancel

    ButtonGroup { id: privacyGroup }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: qsTr("Wählen Sie, ob Ereignisdetails im PREMIS-Dokument enthalten sein sollen.")
        }

        RadioButton {
            objectName: "fullPremisChoice"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            ButtonGroup.group: privacyGroup
            checked: true
            text: qsTr("Vollständig: Ereignisdetails einschliessen")
        }

        RadioButton {
            id: redactedChoice
            objectName: "redactedPremisChoice"
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            ButtonGroup.group: privacyGroup
            text: qsTr("Redigiert: Ereignisdetails auslassen; Bedienerkennung und Prüfsummen bleiben sichtbar")
            contentItem: Text {
                leftPadding: redactedChoice.indicator && !redactedChoice.mirrored ? redactedChoice.indicator.width + redactedChoice.spacing : 0
                rightPadding: redactedChoice.indicator && redactedChoice.mirrored ? redactedChoice.indicator.width + redactedChoice.spacing : 0
                text: redactedChoice.text
                font: redactedChoice.font
                color: redactedChoice.palette.windowText
                wrapMode: Text.Wrap
                verticalAlignment: Text.AlignVCenter
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Label { text: qsTr("METS-Version") }
            ComboBox {
                id: metsFormat
                objectName: "metsVersionChoice"
                Layout.fillWidth: true
                model: [qsTr("METS 2"), qsTr("METS 1.12.1")]
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            Button {
                objectName: "exportPremisOnlyButton"
                text: qsTr("Nur PREMIS XML...")
                onClicked: {
                    const redact = redactedChoice.checked
                    root.close()
                    root.premisExportRequested(redact)
                }
            }
            Button {
                objectName: "exportSipMetsButton"
                text: qsTr("SIP + METS/PREMIS...")
                onClicked: {
                    const redact = redactedChoice.checked
                    const version = metsFormat.currentIndex === 0 ? "2" : "1.12.1"
                    root.close()
                    root.bundleExportRequested(redact, version)
                }
            }
        }
    }
}