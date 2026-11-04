import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: root

    property var folderKeys: []
    property int targetKey: 0
    property string targetKind: ""
    property string targetName: ""
    property var folderOverrides: []
    property var previewRows: []
    property var previewSummary: ({})
    property int selectedFolderKey: 0
    property bool previewReady: false
    property bool previewDirty: false
    property bool folderLevelsDirty: false

    function start(folders, target, kind, name) {
        folderKeys = folders
        targetKey = target
        targetKind = kind
        targetName = name
        folderOverrides = []
        previewRows = []
        previewSummary = ({})
        selectedFolderKey = 0
        previewReady = false
        folderLevelsDirty = false
        previewList.currentIndex = -1
        ospSpin.value = kind === "ordnungssystem" ? 1 : 0
        dossierSpin.value = 1
        docsCheck.checked = false
        topCheck.checked = false
        previewDirty = false
        open()
    }

    function saveSelectedFolderLevels() {
        if (!selectedFolderKey || !folderLevelsDirty)
            return
        const nextOverrides = folderOverrides.filter(item => item.key !== selectedFolderKey)
        nextOverrides.push({
            key: selectedFolderKey,
            ospLevels: folderOspSpin.value,
            dossierLevels: folderDossierSpin.value
        })
        folderOverrides = nextOverrides
        folderLevelsDirty = false
    }

    function setFolderLevels(row) {
        saveSelectedFolderLevels()
        selectedFolderKey = row.key
        folderOspSpin.value = row.ospLevels
        folderDossierSpin.value = row.dossierLevels
    }

    function assignProposal() {
        saveSelectedFolderLevels()

        const proposal = structure.previewMassAssign(
            folderKeys, targetKey, ospSpin.value, dossierSpin.value, docsCheck.checked,
            topCheck.checked, folderOverrides
        )
        if (!proposal || !proposal.rows) {
            previewReady = false
            previewRows = []
            previewSummary = ({})
            return
        }
        previewRows = proposal.rows
        previewSummary = proposal
        if (selectedFolderKey) {
            const selectedRow = proposal.rows.find(row => row.key === selectedFolderKey)
            if (selectedRow)
                setFolderLevels(selectedRow)
        }
        previewReady = true
        previewDirty = false
    }

    function clearProposal() {
        folderOverrides = []
        previewRows = []
        previewSummary = ({})
        selectedFolderKey = 0
        previewReady = false
        previewDirty = false
        folderLevelsDirty = false
        previewList.currentIndex = -1
    }

    function stageLabel(row) {
        if (row.stage === "osp")
            return qsTr("OSP-Stufe %1").arg(row.stageNumber)
        if (row.stage === "dossier")
            return qsTr("Dossier-Stufe %1").arg(row.stageNumber)
        if (row.stage === "subdossier")
            return qsTr("Subdossier-Stufe %1").arg(row.stageNumber)
        if (row.stage === "existingDossier")
            return qsTr("Im Dossier des übergeordneten Ordners")
        if (row.stage === "topExcluded")
            return qsTr("Obersten Ordner nicht zuweisen")
        return qsTr("Dateien bleiben unzugewiesen")
    }

    title: qsTr("Massenzuweisung")
    anchors.centerIn: Overlay.overlay
    width: 900
    height: 650
    modal: true

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        GridLayout {
            Layout.fillWidth: true
            columns: 4
            columnSpacing: 12

            Label { text: qsTr("Ordner") }
            Label { text: qsTr("%1 ausgewählt").arg(root.folderKeys.length); Layout.fillWidth: true }
            Label { text: qsTr("Ziel") }
            Label { text: root.targetName; elide: Text.ElideRight; Layout.fillWidth: true }

            Label { text: qsTr("Anzahl OSP-Stufen") }
            SpinBox {
                id: ospSpin
                from: 0
                to: 10
                enabled: root.targetKind === "ordnungssystem" || root.targetKind === "ordnungssystemposition"
                onValueModified: root.previewDirty = true
            }
            Label { text: qsTr("Anzahl Dossier-Stufen") }
            SpinBox {
                id: dossierSpin
                from: 0
                to: 10
                onValueModified: root.previewDirty = true
            }

            CheckBox {
                id: docsCheck
                text: qsTr("Erzeuge Dokumente für Dateien")
                Layout.columnSpan: 2
                onToggled: root.previewDirty = true
            }
            CheckBox {
                id: topCheck
                text: qsTr("Obersten Ordner zuweisen")
                Layout.columnSpan: 2
                onToggled: root.previewDirty = true
            }
        }

        Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            color: palette.placeholderText
            text: qsTr("Ordner werden bis zur angegebenen OSP-Stufe zu Ordnungssystempositionen und danach zu Dossiers "
                       + "bzw. Subdossiers. Klicken Sie in der Vorschau einen Ordner an, um die Stufen für diesen "
                       + "Ordner und seinen Unterbaum individuell anzupassen.")
        }

        RowLayout {
            Layout.fillWidth: true
            Label { text: qsTr("Vorschau der Zuweisung"); font.bold: true; Layout.fillWidth: true }
            Button { text: qsTr("Zuweisen"); onClicked: root.assignProposal() }
            Button { text: qsTr("Zuweisung löschen"); enabled: root.previewReady; onClicked: root.clearProposal() }
        }

        Label {
            Layout.fillWidth: true
            visible: root.previewReady && root.previewDirty
            color: palette.highlight
            text: qsTr("Einstellungen geändert. Aktualisieren Sie den Vorschlag mit «Zuweisen».")
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.previewReady
            Label {
                Layout.fillWidth: true
                text: qsTr("%1 Struktur-Elemente, %2 Dateien zugewiesen, %3 Dateien bleiben unzugewiesen")
                      .arg(root.previewSummary.created).arg(root.previewSummary.assigned).arg(root.previewSummary.unassigned)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Label { text: qsTr("Ordner"); font.bold: true; Layout.fillWidth: true }
            Label { text: qsTr("Vorgesehene Stufe"); font.bold: true; Layout.preferredWidth: 250 }
            Label { text: qsTr("Dateien auf dieser Stufe"); font.bold: true; Layout.preferredWidth: 180 }
        }

        ListView {
            id: previewList
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.previewReady
            clip: true
            model: root.previewRows
            currentIndex: -1
            ScrollBar.vertical: ScrollBar {}

            delegate: Rectangle {
                id: previewRow
                required property var modelData
                required property int index
                width: previewList.width
                height: 34
                color: previewList.currentIndex === index
                       ? Qt.tint(palette.highlight, Qt.alpha(palette.highlight, 0.18))
                       : index % 2 ? palette.alternateBase : palette.base

                RowLayout {
                    anchors.fill: parent
                    spacing: 8

                    Label {
                        Layout.fillWidth: true
                        leftPadding: 8 + previewRow.modelData.depth * 18
                        text: previewRow.modelData.name
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.preferredWidth: 250
                        text: root.stageLabel(previewRow.modelData)
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.preferredWidth: 180
                        text: qsTr("%1 (%2 zugewiesen)").arg(previewRow.modelData.fileCount)
                             .arg(previewRow.modelData.assignedCount)
                    }
                }

                TapHandler {
                    onTapped: {
                        previewList.currentIndex = previewRow.index
                        root.setFolderLevels(previewRow.modelData)
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: root.previewReady
            Label {
                text: root.selectedFolderKey
                      ? qsTr("Stufen für den ausgewählten Ordner und seinen Unterbaum")
                      : qsTr("Wählen Sie einen Ordner, um die Stufen individuell anzupassen.")
                Layout.fillWidth: true
            }
            Label { text: qsTr("OSP") }
            SpinBox {
                id: folderOspSpin
                from: 0
                to: 10
                enabled: root.selectedFolderKey > 0
                onValueModified: { root.folderLevelsDirty = true; root.previewDirty = true }
            }
            Label { text: qsTr("Dossier") }
            SpinBox {
                id: folderDossierSpin
                from: 0
                to: 10
                enabled: root.selectedFolderKey > 0
                onValueModified: { root.folderLevelsDirty = true; root.previewDirty = true }
            }
            Button {
                text: qsTr("Zuweisen")
                enabled: root.selectedFolderKey > 0
                onClicked: root.assignProposal()
            }
        }
    }

    footer: DialogButtonBox {
        Button {
            text: qsTr("Fertigstellen")
            enabled: root.previewReady && !root.previewDirty
            DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
        }
        Button { text: qsTr("Abbrechen"); DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
    }

    onAccepted: {
        if (previewReady && !previewDirty)
            structure.massAssignWithOverrides(
                folderKeys, targetKey, ospSpin.value, dossierSpin.value,
                docsCheck.checked, topCheck.checked, folderOverrides
            )
    }
}
