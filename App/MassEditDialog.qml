import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Massenmutation (9.2): set or delete one metadata field on all objects of a type below the selection.
Dialog {
    id: root

    property int key: 0
    property string targetName: ""
    property var kinds: []
    property var fields: []
    readonly property var field: fieldBox.currentIndex >= 0 ? fields[fieldBox.currentIndex] : null

    function start(key, name) {
        root.key = key
        targetName = name
        kinds = structure.massEditKinds(key)
        kindBox.currentIndex = kinds.length > 0 ? 0 : -1
        loadFields()
        open()
    }

    function loadFields() {
        fields = kindBox.currentIndex >= 0 ? structure.massEditFields(kinds[kindBox.currentIndex].kind) : []
        fieldBox.currentIndex = fields.length > 0 ? 0 : -1
    }

    title: qsTr("Massenmutation")
    anchors.centerIn: Overlay.overlay
    width: 560
    modal: true

    GridLayout {
        anchors.fill: parent
        columns: 2

        Label { text: qsTr("Objekt") }
        Label {
            id: targetLabel
            text: root.targetName
            elide: Text.ElideRight
            Layout.fillWidth: true
            ToolTip.visible: targetHover.hovered && truncated
            ToolTip.text: text
            HoverHandler { id: targetHover }
        }
        Label { text: qsTr("Betroffene Objekte") }
        ComboBox {
            id: kindBox
            Layout.fillWidth: true
            model: root.kinds.map(k => k.label)
            ToolTip.visible: hovered && currentText.length > 0
            ToolTip.text: currentText
            onActivated: root.loadFields()
        }
        Label { text: qsTr("Metadatum") }
        ComboBox {
            id: fieldBox
            Layout.fillWidth: true
            model: root.fields.map(f => f.label)
            ToolTip.visible: hovered && currentText.length > 0
            ToolTip.text: currentText
        }

        Label { text: root.field && root.field.type === "timespan" ? qsTr("von / bis") : qsTr("Wert") }
        RowLayout {
            Layout.fillWidth: true
            TextField { id: valueField; Layout.fillWidth: true; enabled: !deleteCheck.checked }
            TextField {
                id: endField
                Layout.fillWidth: true
                visible: root.field && root.field.type === "timespan"
                enabled: !deleteCheck.checked
            }
        }
        CheckBox { id: deleteCheck; text: qsTr("Eintrag in allen Objekten löschen"); Layout.columnSpan: 2 }
        Label {
            Layout.columnSpan: 2
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            color: palette.placeholderText
            text: qsTr("Die Änderung wirkt sich auf das gewählte Objekt und alle Objekte dieses Typs darunter aus.")
        }
    }

    footer: DialogButtonBox {
        Button {
            text: qsTr("Fertigstellen")
            enabled: root.field !== null
            DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
        }
        Button { text: qsTr("Abbrechen"); DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
    }

    onAccepted: structure.massEdit(key, kinds[kindBox.currentIndex].kind, field.tag,
                                   deleteCheck.checked ? "" : valueField.text, deleteCheck.checked ? "" : endField.text)
}
