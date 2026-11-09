import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root

    required property int elementKey
    property var references: []
    property var targets: []
    property bool editable: false
    readonly property var attributeNames: {
        const names = []
        for (const reference of references) {
            for (const attribute of reference.attributes) {
                if (!names.includes(attribute.name))
                    names.push(attribute.name)
            }
        }
        return names
    }
    readonly property real referenceGridWidth: {
        let width = 500
        for (const name of attributeNames)
            width += attributeWidth(name)
        return width
    }
    readonly property var selectedTarget: targetPicker.currentIndex > 0
                                        ? targets[targetPicker.currentIndex - 1] : null
    objectName: "incomingReferences-" + elementKey
    Layout.fillWidth: true
    spacing: 6

    function attributeWidth(name) {
        if (name === "version")
            return 120
        if (name === "repraesentation")
            return 170
        if (name === "information")
            return 240
        if (name === "reihung")
            return 120
        return 180
    }

    function refresh() {
        references = editor.incomingReferenceAttributes(elementKey)
        targets = editor.incomingReferenceTargets(elementKey)
    }

    Component.onCompleted: refresh()

    Connections {
        target: editor
        function onContentChanged() { root.refresh() }
    }

    Label {
        text: qsTr("Referenziert in")
        font.bold: true
    }

    RowLayout {
        Layout.fillWidth: true
        visible: root.editable && root.targets.length > 0

        ComboBox {
            id: targetPicker
            objectName: "incomingReferenceTarget-" + root.elementKey
            Layout.fillWidth: true
            model: [{ ownerKey: 0, label: qsTr("Zielobjekt auswählen...") }].concat(root.targets)
            textRole: "label"
            valueRole: "ownerKey"
            currentIndex: 0
            ToolTip.visible: hovered && currentIndex > 0
            ToolTip.text: currentIndex > 0 ? currentText : ""
        }

        Button {
            objectName: "addIncomingReferenceButton-" + root.elementKey
            text: root.selectedTarget && root.selectedTarget.hasReference
                  ? qsTr("Weitere Referenz hinzufügen") : qsTr("Referenz hinzufügen")
            enabled: targetPicker.currentValue > 0
            onClicked: {
                const targetKey = targetPicker.currentValue
                if (targetKey > 0)
                    structure.addFileReference(root.elementKey, targetKey)
                targetPicker.currentIndex = 0
                root.refresh()
            }
        }
    }

    Label {
        visible: root.editable && root.targets.length === 0
        text: qsTr("Keine weiteren schemazulässigen Zielobjekte.")
        color: palette.placeholderText
        wrapMode: Text.Wrap
    }

    Label {
        objectName: "incomingReferencesEmptyMessage"
        visible: root.references.length === 0
        text: qsTr("Keine Verweise auf diese Datei.")
        color: palette.placeholderText
    }

    ScrollView {
        id: referenceGridScroll
        objectName: "incomingReferenceGridScroll-" + root.elementKey
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(280, gridContent.implicitHeight + 8)
        visible: root.references.length > 0
        clip: true
        contentWidth: Math.max(root.width, root.referenceGridWidth)
        ScrollBar.horizontal: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: gridContent
            width: referenceGridScroll.contentWidth
            spacing: 2

            GridLayout {
                Layout.fillWidth: true
                columns: 2 + root.attributeNames.length
                columnSpacing: 6
                Label {
                    Layout.preferredWidth: 280
                    text: qsTr("Referenzierendes Objekt")
                    font.bold: true
                }
                Label {
                    Layout.preferredWidth: 220
                    text: qsTr("Datei(en) im Verweis")
                    font.bold: true
                }
                Repeater {
                    model: root.attributeNames
                    delegate: Label {
                        required property string modelData
                        Layout.preferredWidth: root.attributeWidth(modelData)
                        text: modelData
                        font.bold: true
                    }
                }
            }

            Repeater {
                model: root.references
                delegate: GridLayout {
                    id: referenceRow
                    required property var modelData
                    Layout.fillWidth: true
                    columns: 2 + root.attributeNames.length
                    columnSpacing: 6

                    Label {
                        objectName: "incomingReferenceOwner-" + referenceRow.modelData.ownerKey
                                    + "-" + referenceRow.modelData.index
                        Layout.preferredWidth: 280
                        text: referenceRow.modelData.ownerContext
                        elide: Text.ElideMiddle
                        ToolTip.visible: ownerHover.hovered && truncated
                        ToolTip.text: text
                        HoverHandler { id: ownerHover }
                    }
                    Label {
                        Layout.preferredWidth: 220
                        text: referenceRow.modelData.name + " (" + referenceRow.modelData.fileId + ")"
                        wrapMode: Text.WrapAnywhere
                    }
                    Repeater {
                        model: root.attributeNames
                        delegate: TextField {
                            id: attributeField
                            required property string modelData
                            readonly property var attribute: referenceRow.modelData.attributes.find(
                                item => item.name === modelData)
                            Layout.preferredWidth: root.attributeWidth(modelData)
                            text: attribute ? attribute.value : ""
                            readOnly: !root.editable || !attribute || !attribute.editable
                            selectByMouse: true
                            objectName: "referenceAttribute-" + modelData + "-"
                                        + referenceRow.modelData.index + "-owner-"
                                        + referenceRow.modelData.ownerKey
                            onEditingFinished: {
                                if (readOnly || !attribute || text === attribute.value)
                                    return
                                const targetToken = editor.packageToken
                                editor.setReferenceAttribute(referenceRow.modelData.ownerKey,
                                                             referenceRow.modelData.index,
                                                             modelData, text)
                                Qt.callLater(() => {
                                    if (editor.packageToken === targetToken)
                                        root.refresh()
                                })
                            }
                        }
                    }
                }
            }
        }
    }
}