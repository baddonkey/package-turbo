import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    spacing: 0

    signal detailsRequested(string text)
    signal cleanupRequested()
    signal exportRequested()

    ToolBar {
        Layout.fillWidth: true
        RowLayout {
            anchors.fill: parent
            Label {
                Layout.fillWidth: true
                leftPadding: 6
                text: qsTr("%1 / %2 Ereignisse").arg(historyTable.visibleCount()).arg(historyTable.total)
            }
            ToolButton {
                text: qsTr("Kopieren")
                enabled: historyTable.total > 0
                onClicked: table.copySelection()
            }
            ToolButton {
                objectName: "preservationExportButton"
                text: qsTr("PREMIS/METS exportieren...")
                enabled: backend.hasSip && backend.hasHistory && !backend.busy && !backend.dirty
                ToolTip.visible: hovered && backend.dirty
                ToolTip.text: qsTr("Vor dem Export speichern")
                onClicked: root.exportRequested()
            }
            ToolButton {
                text: qsTr("Wiederherstellen")
                enabled: backend.hasSip && !backend.readOnly && !backend.busy
                onClicked: backend.recoverMetadata()
            }
            ToolButton {
                objectName: "cleanupPreviewButton"
                text: qsTr("Speicher bereinigen...")
                enabled: backend.hasSip && !backend.readOnly && !backend.busy
                onClicked: {
                    if (backend.previewRetentionCleanup())
                        root.cleanupRequested()
                }
            }
        }
    }

    GridLayout {
        Layout.fillWidth: true
        Layout.margins: 6
        columns: width < 680 ? 1 : 3
        columnSpacing: 6
        rowSpacing: 4

        TextField {
            objectName: "historySearchField"
            Layout.fillWidth: true
            placeholderText: qsTr("Historie durchsuchen")
            text: backend.historySearch
            onTextEdited: backend.setHistorySearch(text)
        }
        ComboBox {
            id: eventTypeFilter
            objectName: "historyEventTypeFilter"
            Layout.fillWidth: true
            model: [qsTr("Alle Ereignisse")].concat(backend.historyEventTypes)
            currentIndex: {
                const index = backend.historyEventTypes.indexOf(backend.historyEventFilter)
                return index < 0 ? 0 : index + 1
            }
            ToolTip.visible: hovered && currentText.length > 0
            ToolTip.text: currentText
            onActivated: backend.setHistoryEventFilter(index === 0 ? "" : backend.historyEventTypes[index - 1])
        }
        ComboBox {
            id: outcomeFilter
            objectName: "historyOutcomeFilter"
            Layout.fillWidth: true
            model: [qsTr("Alle Ergebnisse"), qsTr("Erfolgreich"), qsTr("Fehler"), qsTr("Verworfen")]
            currentIndex: backend.historyOutcomeFilter === "success" ? 1
                        : backend.historyOutcomeFilter === "failure" ? 2
                        : backend.historyOutcomeFilter === "discarded" ? 3 : 0
            ToolTip.visible: hovered && currentText.length > 0
            ToolTip.text: currentText
            onActivated: backend.setHistoryOutcomeFilter(["", "success", "failure", "discarded"][index])
        }
    }

    Label {
        Layout.fillWidth: true
        Layout.margins: 6
        visible: backend.auditCompanion.length > 0
        text: backend.auditCompanion
        elide: Text.ElideMiddle
        ToolTip.visible: companionHover.hovered
        ToolTip.text: backend.auditCompanion
        HoverHandler { id: companionHover }
    }

    DataTable {
        id: table
        objectName: "historyView"
        Layout.fillWidth: true
        Layout.fillHeight: true
        tableModel: historyTable
        columnRatios: [0.17, 0.2, 0.14, 0.1, 0.11, 0.14, 0.14]
        onRowActivated: function(row) { root.detailsRequested(backend.historyDetails(row)) }
    }
}