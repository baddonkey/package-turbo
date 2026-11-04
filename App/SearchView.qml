import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

// Action view "Suche" with simple and advanced search (chapter 13).
ColumnLayout {
    id: root

    signal exportRequested()

    spacing: 0

    function focusSimple(text) {
        modeBar.currentIndex = 0
        if (text !== undefined) {
            simpleField.text = text
            runSimple()
        }
        simpleField.forceActiveFocus()
    }

    function runSimple() {
        if (simpleField.text.trim().length === 0) {
            noHits.text = qsTr("Bitte geben Sie einen Suchbegriff ein.")
            noHits.open()
            return
        }
        if (searchCtl.simpleSearch(simpleField.text) === 0) {
            noHits.text = qsTr("Es wurden keine Objekte gefunden.")
            noHits.open()
        }
    }

    function runAdvanced() {
        const criteria = []
        for (let i = 0; i < criteriaRepeater.count; ++i) {
            const row = criteriaRepeater.itemAt(i)
            if (row.used)
                criteria.push(row.criterion())
        }
        if (criteria.length === 0)
            return
        if (searchCtl.advancedSearch(criteria) === 0) {
            noHits.text = qsTr("Es wurden keine Objekte gefunden.")
            noHits.open()
        }
    }

    ToolBar {
        Layout.fillWidth: true
        ColumnLayout {
            anchors.fill: parent
            spacing: 2

            RowLayout {
                TabBar {
                    id: modeBar
                    TabButton { text: qsTr("Einfache Suche"); width: implicitWidth }
                    TabButton { text: qsTr("Erweiterte Suche"); width: implicitWidth }
                }
                Item { Layout.fillWidth: true }
                Label { text: qsTr("%1 Objekte").arg(searchTable.total) }
                ToolButton { text: qsTr("Kopieren"); onClicked: table.copySelection() }
                ToolButton { text: qsTr("Export"); onClicked: root.exportRequested() }
            }

            RowLayout {
                visible: modeBar.currentIndex === 0
                TextField {
                    id: simpleField
                    Layout.fillWidth: true
                    placeholderText: qsTr("Suchbegriff (Gross-/Kleinschreibung wird nicht unterschieden)")
                    onAccepted: root.runSimple()
                }
                Button { text: qsTr("Suchen"); enabled: backend.hasPackage; onClicked: root.runSimple() }
            }

            ColumnLayout {
                visible: modeBar.currentIndex === 1
                Repeater {
                    id: criteriaRepeater
                    model: 3
                    delegate: RowLayout {
                        id: criterionRow
                        required property int index
                        readonly property bool used: kindBox.currentIndex > 0 && fieldBox.currentIndex >= 0
                        property var fields: []

                        function criterion() {
                            return { kind: searchCtl.kinds[kindBox.currentIndex - 1].kind,
                                     tag: fields[fieldBox.currentIndex].tag,
                                     value: valueField.text, empty: emptyBox.checked }
                        }

                        Label { text: qsTr("Objekt") }
                        ComboBox {
                            id: kindBox
                            Layout.preferredWidth: 200
                            model: [qsTr("(kein Kriterium)")].concat(searchCtl.kinds.map(k => k.label))
                            onActivated: function (index) {
                                criterionRow.fields = index > 0 ? searchCtl.fields(searchCtl.kinds[index - 1].kind) : []
                                fieldBox.currentIndex = criterionRow.fields.length > 0 ? 0 : -1
                            }
                        }
                        Label { text: qsTr("Metadatum") }
                        ComboBox {
                            id: fieldBox
                            Layout.preferredWidth: 220
                            model: criterionRow.fields.map(f => f.label)
                        }
                        Label { text: qsTr("Wert") }
                        TextField {
                            id: valueField
                            Layout.fillWidth: true
                            enabled: !emptyBox.checked
                            onAccepted: root.runAdvanced()
                        }
                        CheckBox { id: emptyBox; text: qsTr("Leerfeld") }
                        ToolButton {
                            text: "\u2715"
                            ToolTip.visible: hovered
                            ToolTip.text: qsTr("Suchkriterium entfernen")
                            onClicked: {
                                kindBox.currentIndex = 0
                                criterionRow.fields = []
                                valueField.text = ""
                                emptyBox.checked = false
                            }
                        }
                    }
                }
                RowLayout {
                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Die Suchkriterien werden mit UND kombiniert (gleicher Objekttyp).")
                        color: palette.placeholderText
                    }
                    Button { text: qsTr("Suchen"); enabled: backend.hasPackage; onClicked: root.runAdvanced() }
                }
            }
        }
    }

    DataTable {
        id: table
        Layout.fillWidth: true
        Layout.fillHeight: true
        tableModel: searchTable
        columnRatios: [0.15, 0.3, 0.2, 0.35]
        onRowActivated: function (row) { backend.reveal(searchTable.recordAt(row).key) }
    }

    MessageDialog {
        id: noHits
        title: qsTr("Keine Treffer")
        buttons: MessageDialog.Ok
    }
}
