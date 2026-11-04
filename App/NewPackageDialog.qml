import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

// Neues Paket erstellen (8.1.1 / 8.1.2).
Dialog {
    id: root

    property url location: ""
    property url csvFile: ""
    property bool nameEdited: false
    readonly property string nameError: packageCtl.nameError(nameField.text)

    title: qsTr("Neues Paket erstellen")
    anchors.centerIn: Overlay.overlay
    width: 620
    modal: true
    standardButtons: Dialog.Cancel

    function suggest() {
        if (!nameEdited)
            nameField.text = packageCtl.suggestedName(officeField.text, referenceField.text)
    }

    onOpened: {
        nameEdited = false
        csvFile = ""
        csvCheck.checked = false
        suggest()
    }

    GridLayout {
        anchors.fill: parent
        columns: 3
        columnSpacing: 8

        Label { text: qsTr("XSD-Version") }
        Label { text: packageCtl.xsdVersion; Layout.columnSpan: 2 }

        Label { text: qsTr("Ablieferungstyp") }
        ComboBox { id: typeBox; model: ["GEVER", "FILES"]; Layout.columnSpan: 2 }

        Label { text: qsTr("Abliefernde Stelle *") }
        TextField { id: officeField; Layout.fillWidth: true; Layout.columnSpan: 2; onTextEdited: root.suggest() }

        Label { text: qsTr("Referenz") }
        TextField { id: referenceField; Layout.fillWidth: true; Layout.columnSpan: 2; onTextEdited: root.suggest() }

        Label { text: qsTr("Aktenbildner") }
        TextField { id: creatorField; Layout.fillWidth: true; Layout.columnSpan: 2; placeholderText: qsTr("wie abliefernde Stelle") }

        Label { text: qsTr("Ordnungssystem") }
        TextField { id: systemField; Layout.fillWidth: true; Layout.columnSpan: 2; text: qsTr("Ordnungssystem") }

        Label { text: qsTr("SIP-Name *") }
        TextField {
            id: nameField
            Layout.fillWidth: true
            Layout.columnSpan: 2
            onTextEdited: root.nameEdited = true
            color: root.nameError ? "#c62828" : palette.text
        }
        Item { width: 1 }
        Label {
            Layout.columnSpan: 2
            Layout.fillWidth: true
            visible: root.nameError.length > 0
            text: root.nameError
            color: "#c62828"
            wrapMode: Text.Wrap
        }

        Label { text: qsTr("Speicherort *") }
        TextField { Layout.fillWidth: true; readOnly: true; text: decodeURIComponent(root.location.toString().replace("file:///", "")) }
        Button { text: qsTr("Durchsuchen..."); onClicked: locationDialog.open() }

        CheckBox { id: csvCheck; text: qsTr("Struktur aus CSV importieren"); Layout.columnSpan: 3 }
        Label { text: qsTr("CSV-Datei"); enabled: csvCheck.checked }
        TextField {
            Layout.fillWidth: true
            readOnly: true
            enabled: csvCheck.checked
            text: decodeURIComponent(root.csvFile.toString().replace("file:///", ""))
            placeholderText: qsTr("Spalten mit «|» getrennt, Spalte «nummer» zwingend, optional «type», «titel», ...")
        }
        Button { text: qsTr("Auswählen..."); enabled: csvCheck.checked; onClicked: csvDialog.open() }
    }

    footer: DialogButtonBox {
        Button {
            text: qsTr("Fertigstellen")
            DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole
            enabled: !root.nameError && officeField.text.trim().length > 0 && root.location.toString().length > 0
                     && (!csvCheck.checked || root.csvFile.toString().length > 0)
        }
        Button { text: qsTr("Abbrechen"); DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
    }

    onAccepted: packageCtl.createPackage(location, nameField.text, officeField.text, typeBox.currentText,
                                         creatorField.text, systemField.text, csvCheck.checked ? csvFile : "")

    FolderDialog {
        id: locationDialog
        title: qsTr("Speicherort für das neue Paket")
        onAccepted: root.location = selectedFolder
    }

    FileDialog {
        id: csvDialog
        title: qsTr("CSV-Datei mit der Struktur")
        nameFilters: [qsTr("CSV (*.csv *.txt)")]
        onAccepted: root.csvFile = selectedFile
    }
}
