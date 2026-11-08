import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Generic input dialog for names, counts and note texts; the caller sets 'callback'.
Dialog {
    id: root

    property string label: ""
    property alias text: field.text
    property bool multiline: false
    property bool numeric: false
    property alias number: spin.value
    property var callback: null

    function ask(title, label, text, callback, options) {
        root.title = title
        root.label = label
        root.multiline = !!(options && options.multiline)
        root.numeric = !!(options && options.numeric)
        field.text = text || ""
        area.text = text || ""
        spin.value = (options && options.number) || 1
        root.callback = callback
        open()
    }

    anchors.centerIn: Overlay.overlay
    width: 460
    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel

    ColumnLayout {
        anchors.fill: parent
        Label { objectName: "inputDialogPrompt"; text: root.label; wrapMode: Text.Wrap; Layout.fillWidth: true }
        TextField {
            id: field
            Layout.fillWidth: true
            visible: !root.multiline && !root.numeric
            selectByMouse: true
            onAccepted: root.accept()
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: 140
            visible: root.multiline
            TextArea { id: area; wrapMode: TextEdit.Wrap }
        }
        SpinBox { id: spin; visible: root.numeric; from: 1; to: 500; editable: true }
    }

    onOpened: (root.multiline ? area : root.numeric ? spin : field).forceActiveFocus()
    onAccepted: {
        if (root.callback)
            root.callback(root.numeric ? spin.value : root.multiline ? area.text : field.text)
    }
}
