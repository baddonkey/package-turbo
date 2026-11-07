import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Metadata editor with one tab per object type (Überblick, Statistik, Validierung, Dossier, ...).
Pane {
    id: root
    property var expandedSections: ({})
    property int expansionToken: -1

    Connections {
        target: editor
        function onContentChanged() {
            if (root.expansionToken !== editor.packageToken) {
                root.expansionToken = editor.packageToken
                root.expandedSections = ({})
            }
        }
    }

    signal newNoteRequested(int key)
    signal showNotesRequested(int key)
    signal titleDoubleClicked()

    padding: 0

    component FieldRow: RowLayout {
        id: fieldRow

        required property var field
        required property int elementKey

        readonly property bool editable: !editor.readOnly && field.editable
        readonly property string tip: [field.help, field.error].filter(t => !!t).join("\n\n")

        Layout.fillWidth: true
        spacing: 8

        function commitText(value) {
            const key = elementKey
            const tag = field.tag
            const type = field.type
            const token = editor.packageToken
            Qt.callLater(() => {
                if (editor.packageToken !== token)
                    return
                if (type === "timepoint")
                    editor.setTimePoint(key, tag, value)
                else
                    editor.setField(key, tag, value)
            })
        }

        Label {
            Layout.preferredWidth: 230
            Layout.alignment: Qt.AlignTop
            topPadding: 6
            text: fieldRow.field.label + (fieldRow.field.required ? " *" : "")
            elide: Text.ElideRight
            color: (fieldRow.field.required && !fieldRow.field.value) || fieldRow.field.error ? "#c62828" : palette.text
            ToolTip.visible: labelHover.hovered && fieldRow.tip.length > 0
            ToolTip.delay: 500
            ToolTip.text: fieldRow.tip
            HoverHandler { id: labelHover }
        }

        Loader {
            Layout.fillWidth: true
            sourceComponent: fieldRow.field.type === "repeated" ? repeatedEditor
                           : fieldRow.field.type === "timespan" ? timeSpanEditor
                           : fieldRow.field.type === "multiline" ? multilineEditor
                           : fieldRow.field.type === "choice" ? choiceEditor
                           : textEditor
        }

        Component {
            id: repeatedEditor
            RepeatedTextEditor {
                elementKey: fieldRow.elementKey
                field: fieldRow.field
                editable: fieldRow.editable
            }
        }

        Component {
            id: textEditor
            TextField {
                objectName: "metadataField-" + fieldRow.field.tag
                text: fieldRow.field.value
                readOnly: !fieldRow.editable
                selectByMouse: true
                placeholderText: fieldRow.field.type === "timepoint" ? qsTr("JJJJ oder TT.MM.JJJJ, «ca.» für Schätzungen") : ""
                background: Rectangle {
                    color: parent.readOnly ? palette.window : palette.base
                    border.color: fieldRow.field.error ? "#c62828" : parent.activeFocus ? palette.highlight : palette.mid
                    radius: 2
                }
                onEditingFinished: {
                    if (!fieldRow.editable || text === fieldRow.field.value)
                        return
                    fieldRow.commitText(text)
                }
                ContextMenu.menu: EditMenu { target: parent }
            }
        }

        Component {
            id: choiceEditor
            ComboBox {
                model: fieldRow.field.choices
                enabled: fieldRow.editable
                currentIndex: Math.max(0, fieldRow.field.choices.indexOf(fieldRow.field.value))
                displayText: currentText === "" ? qsTr("(keine Auswahl)") : currentText
                onActivated: function (index) {
                    if (fieldRow.field.choices[index] !== fieldRow.field.value)
                        fieldRow.commitText(fieldRow.field.choices[index])
                }
            }
        }

        Component {
            id: multilineEditor
            ScrollView {
                implicitHeight: 64
                TextArea {
                    objectName: "metadataField-" + fieldRow.field.tag
                    text: fieldRow.field.value
                    readOnly: !fieldRow.editable
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    onEditingFinished: if (fieldRow.editable && text !== fieldRow.field.value)
                                           fieldRow.commitText(text)
                    ContextMenu.menu: EditMenu { target: parent }
                }
            }
        }

        Component {
            id: timeSpanEditor
            RowLayout {
                function commit() {
                    if (fieldRow.editable && (startField.text !== fieldRow.field.start || endField.text !== fieldRow.field.end)) {
                        const key = fieldRow.elementKey
                        const tag = fieldRow.field.tag
                        const start = startField.text
                        const end = endField.text
                        const token = editor.packageToken
                        Qt.callLater(() => {
                            if (editor.packageToken === token)
                                editor.setTimeSpan(key, tag, start, end)
                        })
                    }
                }
                Label { text: qsTr("von") }
                TextField {
                    id: startField
                    Layout.fillWidth: true
                    text: fieldRow.field.start
                    placeholderText: qsTr("JJJJ, TT.MM.JJJJ, keine Angabe")
                    readOnly: !fieldRow.editable
                    onEditingFinished: parent.commit()
                }
                Label { text: qsTr("bis") }
                TextField {
                    id: endField
                    Layout.fillWidth: true
                    text: fieldRow.field.end
                    placeholderText: qsTr("JJJJ, TT.MM.JJJJ, keine Angabe")
                    readOnly: !fieldRow.editable
                    onEditingFinished: parent.commit()
                }
            }
        }
    }

    component StatTable: GroupBox {
        id: statTable
        property var rows: []
        Layout.fillWidth: true
        Layout.leftMargin: 12
        Layout.rightMargin: 12
        visible: rows.length > 0
        ColumnLayout {
            Repeater {
                model: statTable.rows
                delegate: RowLayout {
                    required property var modelData
                    Label { Layout.preferredWidth: 300; text: parent.modelData.label }
                    Label { text: parent.modelData.value; font.bold: true }
                }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Kopfzeile: identifies the delivery on every tab.
        Pane {
            Layout.fillWidth: true
            visible: editor.hasPackage
            background: Rectangle { color: Qt.tint(palette.window, Qt.alpha(palette.highlight, 0.15)) }

            GridLayout {
                anchors.fill: parent
                columns: 4
                columnSpacing: 16

                Label { text: qsTr("Ablieferungstyp:"); font.bold: true }
                Label { text: editor.header.deliveryType ?? ""; Layout.fillWidth: true }
                Label { text: qsTr("Aktenbildner:"); font.bold: true }
                Label { text: editor.header.creator ?? ""; Layout.fillWidth: true; elide: Text.ElideRight }
                Label { text: qsTr("Ablieferungsnummer:"); font.bold: true }
                Label { text: (backend.dirty ? "*" : "") + (editor.header.deliveryNumber ?? "") }
                Label { text: qsTr("Erscheinungsform:"); font.bold: true }
                Label { text: editor.header.appearance ?? "" }
            }
            TapHandler { onDoubleTapped: root.titleDoubleClicked() }
        }

        // Breadcrumb of hyperlinks back to the delivery.
        Flow {
            Layout.fillWidth: true
            Layout.margins: 6
            visible: editor.breadcrumb.length > 0
            spacing: 4

            Repeater {
                model: editor.breadcrumb
                delegate: Row {
                    id: crumb
                    required property var modelData
                    required property int index
                    spacing: 4
                    Label {
                        text: crumb.modelData.label
                        color: palette.link
                        font.underline: linkHover.hovered
                        HoverHandler { id: linkHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: backend.reveal(crumb.modelData.key) }
                    }
                    Label { text: "\u203A"; visible: crumb.index < editor.breadcrumb.length - 1 }
                }
            }
        }

        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            visible: editor.hasPackage

            ColumnLayout {
                width: scroll.availableWidth
                spacing: 12

                Label {
                    Layout.margins: 12
                    visible: editor.sections.length === 0
                             && ["ueberblick", "statistik", "validierung"].indexOf(editor.currentTab) < 0
                    text: qsTr("Wählen Sie in einem Navigator ein Objekt aus, um dessen Metadaten anzuzeigen.")
                    color: palette.placeholderText
                }

                Repeater {
                    model: editor.sections

                    delegate: GroupBox {
                        id: section

                        required property var modelData

                        Layout.fillWidth: true
                        Layout.leftMargin: 12
                        Layout.rightMargin: 12

                        label: RowLayout {
                            width: section.availableWidth
                            spacing: 8
                            Label {
                                text: section.modelData.title
                                      + (section.modelData.name && section.modelData.kind !== "paket" ? " \u2013 " + section.modelData.name : "")
                                font.bold: true
                            }
                            Label {
                                visible: section.modelData.noteCount > 0
                                text: "N"
                                font.bold: true
                                color: "#ef6c00"
                            }
                            Label {
                                visible: section.modelData.readOnly && !editor.readOnly
                                text: qsTr("(nur Anzeige)")
                                color: palette.placeholderText
                            }
                            Item { Layout.fillWidth: true }
                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                onTapped: sectionMenu.popup()
                            }
                        }

                        Menu {
                            id: sectionMenu
                            MenuItem {
                                text: qsTr("Neue Notiz...")
                                enabled: section.modelData.canHaveNotes && !editor.readOnly
                                onTriggered: root.newNoteRequested(section.modelData.key)
                            }
                            MenuItem {
                                text: qsTr("Gehe zu Notiz")
                                enabled: section.modelData.noteCount > 0
                                onTriggered: root.showNotesRequested(section.modelData.key)
                            }
                        }

                        ColumnLayout {
                            anchors.fill: parent
                            spacing: 4

                            Repeater {
                                model: section.modelData.primary
                                delegate: FieldRow {
                                    required property var modelData
                                    field: modelData
                                    elementKey: section.modelData.key
                                }
                            }

                            Button {
                                id: moreToggle
                                objectName: "moreFields-" + section.modelData.key
                                visible: section.modelData.more.length > 0
                                flat: true
                                checkable: true
                                checked: root.expandedSections[editor.packageToken + ":" + section.modelData.key] === true
                                onCheckedChanged: {
                                    const key = editor.packageToken + ":" + section.modelData.key
                                    if (root.expandedSections[key] !== checked) {
                                        const values = Object.assign({}, root.expandedSections)
                                        values[key] = checked
                                        root.expandedSections = values
                                    }
                                }
                                text: (checked ? "\u2212 " : "+ ") + qsTr("Weitere Angaben")
                            }

                            Repeater {
                                model: moreToggle.checked ? section.modelData.more : []
                                delegate: FieldRow {
                                    required property var modelData
                                    field: modelData
                                    elementKey: section.modelData.key
                                }
                            }

                            AdditionalDataEditor {
                                Layout.fillWidth: true
                                visible: section.modelData.canHaveAdditionalData || section.modelData.additionalData.length > 0
                                elementKey: section.modelData.key
                                items: section.modelData.additionalData
                                editable: !editor.readOnly && !section.modelData.readOnly
                            }
                            AdditionalDataEditor {
                                Layout.fillWidth: true
                                visible: section.modelData.canHaveFileProperties || section.modelData.fileProperties.length > 0
                                elementKey: section.modelData.key
                                items: section.modelData.fileProperties
                                editable: !editor.readOnly && !section.modelData.readOnly
                                fileProperties: true
                            }
                            ReferenceAttributesEditor {
                                Layout.fillWidth: true
                                visible: section.modelData.references.length > 0
                                elementKey: section.modelData.key
                                references: section.modelData.references
                                editable: !editor.readOnly && !section.modelData.readOnly
                            }
                        }
                    }
                }

                // Register Statistik
                GroupBox {
                    Layout.fillWidth: true
                    Layout.margins: 12
                    visible: editor.currentTab === "statistik"
                    title: qsTr("Vergleich von Zeiträumen")
                    TimeSpanChart {
                        width: parent.width
                        chart: editor.currentTab === "statistik" ? editor.timeSpanChart : ({ bars: [] })
                    }
                }

                StatTable {
                    title: qsTr("Angaben zur Aktenführung")
                    rows: editor.currentTab === "statistik" ? (editor.statistics.records || []) : []
                }
                StatTable {
                    title: qsTr("Detailinformation Ordnungssystem (Positionen pro Stufe)")
                    rows: editor.currentTab === "statistik" ? (editor.statistics.positionsPerLevel || []) : []
                }
                StatTable {
                    title: qsTr("Detailinformation Dossier (Subdossiers pro Stufe)")
                    rows: editor.currentTab === "statistik" ? (editor.statistics.subdossiersPerLevel || []) : []
                }
                StatTable {
                    title: qsTr("Detailinformation Dokument (Dokumente nach Anzahl Dateien)")
                    rows: editor.currentTab === "statistik" ? (editor.statistics.documentsByFileCount || []) : []
                }
                StatTable {
                    title: qsTr("Technische Angaben")
                    rows: editor.currentTab === "statistik" ? (editor.statistics.technical || []) : []
                }

                GroupBox {
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.rightMargin: 12
                    visible: editor.currentTab === "statistik"
                    title: qsTr("Verteilung der Schutzfristen")

                    ColumnLayout {
                        RowLayout {
                            Label { Layout.preferredWidth: 180; text: qsTr("Stufe"); font.bold: true }
                            Label { Layout.preferredWidth: 200; text: qsTr("Schutzfristenkategorie"); font.bold: true }
                            Label { Layout.preferredWidth: 120; text: qsTr("Schutzfrist"); font.bold: true }
                            Label { text: qsTr("Anzahl"); font.bold: true }
                        }
                        Repeater {
                            model: editor.currentTab === "statistik" ? editor.protectionPeriods : []
                            delegate: RowLayout {
                                required property var modelData
                                Label { Layout.preferredWidth: 180; text: parent.modelData.level }
                                Label { Layout.preferredWidth: 200; text: parent.modelData.category }
                                Label { Layout.preferredWidth: 120; text: parent.modelData.period }
                                Label { text: parent.modelData.count }
                            }
                        }
                    }
                }

                // Register Validierung
                GroupBox {
                    Layout.fillWidth: true
                    Layout.margins: 12
                    visible: editor.currentTab === "validierung"
                    title: qsTr("Durchgeführte Prüfungen")

                    ColumnLayout {
                        anchors.fill: parent
                        Repeater {
                            model: editor.validationSummary
                            delegate: RowLayout {
                                id: checkRow
                                required property var modelData
                                Layout.fillWidth: true
                                Label {
                                    Layout.preferredWidth: 260
                                    text: checkRow.modelData.group
                                    color: palette.placeholderText
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: checkRow.modelData.check + (checkRow.modelData.fullOnly ? " *" : "")
                                    color: checkRow.modelData.errors > 0 ? "#c62828" : palette.text
                                    font.bold: checkRow.modelData.errors > 0
                                }
                                Label {
                                    Layout.preferredWidth: 160
                                    text: qsTr("%1 Fehler / %2 Warnungen").arg(checkRow.modelData.errors).arg(checkRow.modelData.warnings)
                                }
                                Button {
                                    text: qsTr("Anzeigen")
                                    flat: true
                                    enabled: checkRow.modelData.errors + checkRow.modelData.warnings > 0
                                    onClicked: backend.setValidationFilter(checkRow.modelData.check)
                                }
                            }
                        }
                        Label {
                            text: qsTr("* Wird nur bei «Paket vollständig validieren» geprüft.")
                            color: palette.placeholderText
                        }
                    }
                }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !editor.hasPackage
            Label {
                anchors.centerIn: parent
                text: qsTr("Kein Paket geöffnet.\nÖffnen oder erstellen Sie ein Paket oder ziehen Sie den SIP-Ordner hierher.")
                horizontalAlignment: Text.AlignHCenter
                color: palette.placeholderText
            }
        }

        TabBar {
            id: tabBar
            Layout.fillWidth: true
            visible: editor.hasPackage
            currentIndex: editor.tabs.findIndex(t => t.id === editor.currentTab)

            Repeater {
                model: editor.tabs
                delegate: TabButton {
                    required property var modelData
                    text: modelData.label
                    width: implicitWidth
                    onClicked: editor.showTab(modelData.id)
                    ToolTip.visible: hovered && modelData.help.length > 0
                    ToolTip.delay: 600
                    ToolTip.text: modelData.help
                }
            }
        }
    }
}
