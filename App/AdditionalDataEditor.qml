import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Element Zusatzdaten (7.3.5): list of Merkmale (name, value) of one object.
ColumnLayout {
    id: root

    property int elementKey: 0
    property var items: []
    property bool editable: false
    property var rows: []

    spacing: 4

    onItemsChanged: rows = items.map(i => ({ name: i.name, value: i.value }))

    function commit() {
        editor.setAdditionalData(elementKey, rows.filter(r => r.name.trim() || r.value.trim()))
    }

    RowLayout {
        Label {
            Layout.preferredWidth: 230
            text: qsTr("Zusatzdaten")
            font.bold: true
            ToolTip.visible: zusatzHover.hovered
            ToolTip.delay: 500
            ToolTip.text: qsTr("Generisches Element für weitere beschreibende Metadaten als Merkmale (Name und Wert).")
            HoverHandler { id: zusatzHover }
        }
        Label {
            visible: root.rows.length === 0
            text: qsTr("keine Merkmale")
            color: palette.placeholderText
        }
        Item { Layout.fillWidth: true }
        Button {
            text: qsTr("+ Merkmal")
            flat: true
            visible: root.editable
            onClicked: root.rows = root.rows.concat([{ name: "", value: "" }])
        }
    }

    Repeater {
        model: root.rows

        delegate: RowLayout {
            id: merkmalRow
            required property var modelData
            required property int index
            Layout.fillWidth: true
            spacing: 8

            TextField {
                Layout.preferredWidth: 230
                text: merkmalRow.modelData.name
                placeholderText: qsTr("Name")
                readOnly: !root.editable
                selectByMouse: true
                onEditingFinished: {
                    if (text === root.rows[merkmalRow.index].name)
                        return
                    root.rows[merkmalRow.index].name = text
                    root.commit()
                }
            }
            TextField {
                Layout.fillWidth: true
                text: merkmalRow.modelData.value
                placeholderText: qsTr("Wert")
                readOnly: !root.editable
                selectByMouse: true
                onEditingFinished: {
                    if (text === root.rows[merkmalRow.index].value)
                        return
                    root.rows[merkmalRow.index].value = text
                    root.commit()
                }
            }
            ToolButton {
                text: "\u2715"
                visible: root.editable
                ToolTip.visible: hovered
                ToolTip.text: qsTr("Merkmal entfernen")
                onClicked: {
                    const rows = root.rows.slice()
                    rows.splice(merkmalRow.index, 1)
                    root.rows = rows
                    root.commit()
                }
            }
        }
    }
}
