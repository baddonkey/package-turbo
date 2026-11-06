import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    required property int elementKey
    required property var field
    property bool editable: false
    property var rows: []
    objectName: "repeated-" + field.tag + "-" + elementKey
    Layout.fillWidth: true
    spacing: 4

    onFieldChanged: rows = (field.values || []).map((value, index) => ({ value: value, sourceIndex: index }))

    function commit(values) {
        const key = elementKey
        const tag = field.tag
        const token = editor.packageToken
        const payload = values.map(value => ({ value: value.value, sourceIndex: value.sourceIndex }))
        Qt.callLater(() => {
            if (editor.packageToken === token)
                editor.setRepeatedField(key, tag, payload)
        })
    }

    Repeater {
        model: root.rows
        delegate: RowLayout {
            id: row
            required property var modelData
            required property int index
            Layout.fillWidth: true
            TextArea {
                objectName: "repeatedValue-" + root.field.tag + "-" + row.index
                Layout.fillWidth: true
                implicitHeight: Math.max(32, contentHeight + topPadding + bottomPadding)
                wrapMode: TextEdit.Wrap
                text: row.modelData.value
                readOnly: !root.editable
                selectByMouse: true
                onEditingFinished: {
                        if (!root.editable || row.index < 0 || row.index >= root.rows.length
                            || text === root.rows[row.index].value)
                        return
                    const values = root.rows.slice()
                    values[row.index] = { value: text, sourceIndex: row.modelData.sourceIndex }
                    root.commit(values)
                }
            }
            ToolButton {
                text: "\u2191"
                visible: root.editable
                enabled: row.index > 0
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Nach oben")
                onClicked: {
                    const values = root.rows.slice()
                    const previous = values[row.index - 1]
                    values[row.index - 1] = values[row.index]
                    values[row.index] = previous
                    root.commit(values)
                }
            }
            ToolButton {
                text: "\u2193"
                visible: root.editable
                enabled: row.index + 1 < root.rows.length
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Nach unten")
                onClicked: {
                    const values = root.rows.slice()
                    const next = values[row.index + 1]
                    values[row.index + 1] = values[row.index]
                    values[row.index] = next
                    root.commit(values)
                }
            }
            ToolButton {
                text: "\u2715"
                visible: root.editable
                enabled: root.rows.length > root.field.minimum
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Wert entfernen")
                onClicked: {
                    const values = root.rows.slice()
                    values.splice(row.index, 1)
                    root.commit(values)
                }
            }
        }
    }
    ToolButton {
        text: "+"
        visible: root.editable
        enabled: root.field.maximum < 0 || root.rows.length < root.field.maximum
        ToolTip.visible: hovered
        ToolTip.text: qsTr("Wert hinzuf\u00fcgen")
        onClicked: root.rows = root.rows.concat([{ value: "", sourceIndex: -1 }])
    }
}