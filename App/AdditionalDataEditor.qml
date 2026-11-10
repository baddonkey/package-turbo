import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Element Zusatzdaten (7.3.5): list of Merkmale (name, value) of one object.
ColumnLayout {
    id: root

    property int elementKey: 0
    property var items: []
    property bool editable: false
    property bool fileProperties: false
    property var rows: []
    property var focusedFields: ({})
    property bool preserveRows: false
    property bool localEditPending: false
    property int currentPackageToken: editor.packageToken
    objectName: fileProperties ? "filePropertiesEditor-" + elementKey : "additionalDataEditor-" + elementKey

    spacing: 4

    onItemsChanged: {
        const incoming = items.map(i => ({ name: i.name, value: i.value }))
        if (localEditPending) {
            if (sameRows(rows, incoming))
                localEditPending = false
            return
        }
        if (!preserveRows)
            rows = incoming
    }
    onCurrentPackageTokenChanged: {
        focusedFields = ({})
        preserveRows = false
        localEditPending = false
        syncRowsTimer.stop()
        rows = items.map(i => ({ name: i.name, value: i.value }))
    }

    function sameRows(left, right) {
        return left.length === right.length && left.every((row, index) =>
            row.name === right[index].name && row.value === right[index].value)
    }

    function trackFieldFocus(key, focused) {
        const fields = Object.assign({}, focusedFields)
        if (focused) {
            fields[key] = true
            preserveRows = true
            syncRowsTimer.stop()
        } else {
            delete fields[key]
        }
        focusedFields = fields
        if (!focused && Object.keys(fields).length === 0)
            syncRowsTimer.restart()
    }

    Timer {
        id: syncRowsTimer
        interval: 250
        repeat: false
        onTriggered: {
            if (Object.keys(root.focusedFields).length === 0 && !root.localEditPending) {
                root.preserveRows = false
                root.rows = root.items.map(i => ({ name: i.name, value: i.value }))
            }
        }
    }

    function commit() {
        const key = elementKey
        const token = editor.packageToken
        localEditPending = true
        const values = rows.filter(row => row.name.trim() || (!fileProperties && row.value.trim()))
                            .map(row => ({ name: row.name, value: row.value }))
        Qt.callLater(() => {
            if (editor.packageToken === token) {
                if (fileProperties)
                    editor.setFileProperties(key, values)
                else
                    editor.setAdditionalData(key, values)
            }
        })
    }

    RowLayout {
        Label {
            Layout.preferredWidth: 230
            text: root.fileProperties ? qsTr("Dateieigenschaften") : qsTr("Zusatzdaten")
            font.bold: true
            ToolTip.visible: zusatzHover.hovered
            ToolTip.delay: 500
            ToolTip.text: root.fileProperties
                          ? qsTr("Technische Dateieigenschaften als wiederholte Name-Wert-Paare.")
                          : qsTr("Generisches Element für weitere beschreibende Metadaten als Merkmale (Name und Wert).")
            HoverHandler { id: zusatzHover }
        }
        Label {
            visible: root.rows.length === 0
            text: root.fileProperties ? qsTr("keine Eigenschaften") : qsTr("keine Merkmale")
            color: palette.placeholderText
        }
        Item { Layout.fillWidth: true }
        Button {
            objectName: "addAdditionalDataButton-" + root.elementKey
            text: root.fileProperties ? qsTr("+ Eigenschaft") : qsTr("+ Merkmal")
            flat: true
            visible: root.editable
            onClicked: {
                root.localEditPending = true
                root.rows = root.rows.concat([{ name: "", value: "" }])
            }
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
                objectName: (root.fileProperties ? "filePropertyName-" : "additionalDataName-")
                            + root.elementKey + "-" + merkmalRow.index
                Layout.preferredWidth: 230
                text: merkmalRow.modelData.name
                placeholderText: qsTr("Name")
                readOnly: !root.editable
                selectByMouse: true
                onActiveFocusChanged: root.trackFieldFocus("name-" + merkmalRow.index, activeFocus)
                onEditingFinished: {
                    if (text === root.rows[merkmalRow.index].name)
                        return
                    root.rows[merkmalRow.index].name = text
                    root.commit()
                }
            }
            TextField {
                objectName: (root.fileProperties ? "filePropertyValue-" : "additionalDataValue-")
                            + root.elementKey + "-" + merkmalRow.index
                Layout.fillWidth: true
                text: merkmalRow.modelData.value
                placeholderText: qsTr("Wert")
                readOnly: !root.editable
                selectByMouse: true
                onActiveFocusChanged: root.trackFieldFocus("value-" + merkmalRow.index, activeFocus)
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
                ToolTip.text: root.fileProperties ? qsTr("Eigenschaft entfernen") : qsTr("Merkmal entfernen")
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
