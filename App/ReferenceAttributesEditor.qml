import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    required property int elementKey
    property var references: []
    property bool editable: false
    objectName: "references-" + elementKey
    Layout.fillWidth: true
    spacing: 6

    Label { text: qsTr("Dateiverweise"); font.bold: true }
    Repeater {
        model: root.references
        delegate: ColumnLayout {
            id: reference
            required property var modelData
            Layout.fillWidth: true
            Label {
                id: referenceNameLabel
                Layout.fillWidth: true
                text: reference.modelData.name + " (" + reference.modelData.fileId + ")"
                elide: Text.ElideMiddle
                ToolTip.visible: referenceNameHover.hovered && truncated
                ToolTip.text: text
                HoverHandler { id: referenceNameHover }
            }
            Repeater {
                model: reference.modelData.attributes
                delegate: RowLayout {
                    id: attribute
                    required property var modelData
                    Layout.fillWidth: true
                    Label {
                        id: attributeNameLabel
                        Layout.preferredWidth: 230
                        text: attribute.modelData.name
                        elide: Text.ElideMiddle
                        ToolTip.visible: attributeNameHover.hovered && truncated
                        ToolTip.text: text
                        HoverHandler { id: attributeNameHover }
                    }
                    TextField {
                        objectName: "referenceAttribute-" + attribute.modelData.name + "-" + reference.modelData.index
                        Layout.fillWidth: true
                        text: attribute.modelData.value
                        readOnly: !root.editable || !attribute.modelData.editable
                        selectByMouse: true
                        onEditingFinished: {
                            if (!readOnly && text !== attribute.modelData.value) {
                                const key = root.elementKey
                                const index = reference.modelData.index
                                const name = attribute.modelData.name
                                const value = text
                                const token = editor.packageToken
                                Qt.callLater(() => {
                                    if (editor.packageToken === token)
                                        editor.setReferenceAttribute(key, index, name, value)
                                })
                            }
                        }
                    }
                }
            }
        }
    }
}