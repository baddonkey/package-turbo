import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Extras > Benutzervorgaben.
Dialog {
    id: root

    title: qsTr("Benutzervorgaben")
    anchors.centerIn: Overlay.overlay
    width: 560
    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        GroupBox {
            title: qsTr("Validierung")
            Layout.fillWidth: true
            CheckBox { id: sipNameCheck; text: qsTr("SIP-Namen validieren") }
        }

        GroupBox {
            title: qsTr("Navigatoren")
            Layout.fillWidth: true
            RowLayout {
                Label { text: qsTr("Schwellwert «Alles aufklappen»") }
                SpinBox { id: thresholdSpin; from: 100; to: 1000000; stepSize: 1000; editable: true }
                Button { text: qsTr("Standardwert"); onClicked: thresholdSpin.value = 15000 }
            }
        }

        GroupBox {
            title: qsTr("Suche")
            Layout.fillWidth: true
            RowLayout {
                Label { text: qsTr("Maximale Anzahl Treffer") }
                SpinBox { id: hitsSpin; from: 10; to: 1000000; stepSize: 1000; editable: true }
                Button { text: qsTr("Standardwert"); onClicked: hitsSpin.value = 15000 }
            }
        }

        GroupBox {
            title: qsTr("Stichprobe")
            Layout.fillWidth: true
            RowLayout {
                Label { text: qsTr("Art der Beschränkung") }
                ComboBox { id: sampleModeBox; model: [qsTr("absolut"), qsTr("in Prozent")] }
                Label { text: qsTr("Umfang") }
                SpinBox { id: sampleSizeSpin; from: 0; to: 100000; editable: true }
                Button { text: qsTr("Standardwert"); onClicked: { sampleModeBox.currentIndex = 0; sampleSizeSpin.value = 10 } }
            }
        }

        GroupBox {
            title: qsTr("Berichte")
            Layout.fillWidth: true
            RowLayout {
                anchors.fill: parent
                Label { text: qsTr("Name des Report-Herstellers") }
                TextField { id: reporterField; Layout.fillWidth: true }
            }
        }

        GroupBox {
            title: qsTr("Sprache")
            Layout.fillWidth: true
            RowLayout {
                ComboBox { id: languageBox; model: ["Deutsch", "Français"] }
                Label { text: qsTr("Wird nach einem Neustart wirksam."); color: palette.placeholderText }
            }
        }
    }

    onOpened: {
        sipNameCheck.checked = backend.validateSipName
        thresholdSpin.value = backend.expandThreshold
        hitsSpin.value = backend.maxSearchHits
        sampleModeBox.currentIndex = backend.sampleMode === "percent" ? 1 : 0
        sampleSizeSpin.value = backend.sampleSize
        reporterField.text = backend.reporterName
        languageBox.currentIndex = backend.language === "fr" ? 1 : 0
    }
    onAccepted: {
        backend.validateSipName = sipNameCheck.checked
        backend.expandThreshold = thresholdSpin.value
        backend.maxSearchHits = hitsSpin.value
        backend.sampleMode = sampleModeBox.currentIndex === 1 ? "percent" : "absolute"
        backend.sampleSize = sampleSizeSpin.value
        backend.reporterName = reporterField.text
        backend.language = languageBox.currentIndex === 1 ? "fr" : "de"
    }
}
