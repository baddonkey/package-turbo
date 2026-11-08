import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root

    property string message: ""
    property string informativeText: ""
    property string buttonSet: "ok"

    signal actionChosen(string action)

    title: ""
    anchors.centerIn: Overlay.overlay
    width: Math.min(440, Overlay.overlay ? Overlay.overlay.width - 32 : 440)
    modal: true
    standardButtons: Dialog.NoButton
    padding: 18

    function choose(action) {
        actionChosen(action)
        if (action === "cancel")
            reject()
        else
            accept()
    }

    background: Rectangle {
        color: palette.base
        border.color: palette.mid
        border.width: 1
        radius: 8
    }

    header: Rectangle {
        implicitHeight: 48
        color: palette.highlight
        radius: 8
        Label {
            objectName: "messageBoxTitle"
            anchors.fill: parent
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            verticalAlignment: Text.AlignVCenter
            text: root.title
            color: palette.highlightedText
            font.pixelSize: 15
            font.bold: true
            wrapMode: Text.Wrap
        }
    }

    contentItem: ColumnLayout {
        spacing: 8
        Label {
            objectName: "messageBoxText"
            Layout.fillWidth: true
            text: root.message
            color: palette.text
            font.pixelSize: 14
            wrapMode: Text.WordWrap
        }
        Label {
            Layout.fillWidth: true
            visible: root.informativeText.length > 0
            text: root.informativeText
            color: palette.placeholderText
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
    }

    footer: Rectangle {
        implicitHeight: 62
        color: palette.alternateBase
        radius: 8

        RowLayout {
            anchors.fill: parent
            anchors.rightMargin: 18
            anchors.leftMargin: 18
            spacing: 8
            Item { Layout.fillWidth: true }

            Button {
                visible: root.buttonSet === "yesNo" || root.buttonSet === "yesNoCancel"
                text: qsTr("Nein")
                onClicked: root.choose("no")
            }
            Button {
                visible: root.buttonSet === "saveDiscardCancel"
                text: qsTr("Verwerfen")
                onClicked: root.choose("discard")
            }
            Button {
                visible: root.buttonSet === "okCancel" || root.buttonSet === "yesNoCancel"
                         || root.buttonSet === "saveDiscardCancel"
                text: qsTr("Abbrechen")
                onClicked: root.choose("cancel")
            }
            Button {
                visible: root.buttonSet === "ok" || root.buttonSet === "okCancel"
                text: qsTr("OK")
                highlighted: true
                onClicked: root.choose("ok")
            }
            Button {
                visible: root.buttonSet === "yesNo" || root.buttonSet === "yesNoCancel"
                text: qsTr("Ja")
                highlighted: true
                onClicked: root.choose("yes")
            }
            Button {
                visible: root.buttonSet === "saveDiscardCancel"
                text: qsTr("Speichern")
                highlighted: true
                onClicked: root.choose("save")
            }
        }
    }
}
