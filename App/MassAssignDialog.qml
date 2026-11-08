import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Massenzuweisung (8.3.1): build positions and dossiers from folders of the Paket-Navigator.
Dialog {
    id: root

    property var folderKeys: []
    property int targetKey: 0
    property string targetKind: ""
    property string targetName: ""

    function start(folders, target, kind, name) {
        folderKeys = folders
        targetKey = target
        targetKind = kind
        targetName = name
        ospSpin.value = kind === "ordnungssystem" ? 1 : 0
        dossierSpin.value = 1
        open()
    }

    title: qsTr("Massenzuweisung")
    anchors.centerIn: Overlay.overlay
    width: 520
    modal: true

    GridLayout {
        anchors.fill: parent
        columns: 2

        Label { text: qsTr("Ordner") }
        Label { text: qsTr("%1 ausgewählt").arg(root.folderKeys.length) }
        Label { text: qsTr("Ziel") }
        Label {
            id: targetLabel
            text: root.targetName
            elide: Text.ElideRight
            Layout.fillWidth: true
            ToolTip.visible: targetHover.hovered && truncated
            ToolTip.text: text
            HoverHandler { id: targetHover }
        }

        Label { text: qsTr("Anzahl OSP Stufen") }
        SpinBox {
            id: ospSpin
            from: root.targetKind === "ordnungssystem" ? 1 : 0
            to: 10
            enabled: root.targetKind === "ordnungssystem" || root.targetKind === "ordnungssystemposition"
        }
        Label { text: qsTr("Anzahl Dossier Stufen") }
        SpinBox { id: dossierSpin; from: 0; to: 10 }

        CheckBox { id: docsCheck; text: qsTr("Erzeuge Dokumente für Dateien"); Layout.columnSpan: 2 }
        CheckBox { id: topCheck; text: qsTr("Obersten Ordner zuweisen"); Layout.columnSpan: 2 }

        Label {
            Layout.columnSpan: 2
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            color: palette.placeholderText
            text: qsTr("Ordner bis zur Stufe «OSP Stufen» werden zu Ordnungssystempositionen, die folgenden Stufen zu "
                       + "Dossiers und Subdossiers. Dateien werden dem nächsten Dossier zugewiesen; bei GEVER-Ablieferungen "
                       + "wird pro Datei ein Dokument erstellt. Die Zuweisung kann nur durch Löschen der Struktur im "
                       + "Ordnungssystem-Navigator aufgehoben werden.")
        }
    }

    footer: DialogButtonBox {
        Button { text: qsTr("Fertigstellen"); DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole }
        Button { text: qsTr("Abbrechen"); DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
    }

    onAccepted: structure.massAssign(folderKeys, targetKey, ospSpin.value, dossierSpin.value, docsCheck.checked,
                                     topCheck.checked)
}
