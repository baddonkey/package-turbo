import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Extras > Benutzervorgaben.
Dialog {
    id: root

    title: qsTr("Benutzervorgaben")
    anchors.centerIn: Overlay.overlay
    width: 560
    height: Math.min(Overlay.overlay.height - 32, 720)
    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel

    ScrollView {
        id: preferencesScroll
        objectName: "preferencesScrollView"
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.vertical: ScrollBar {
            objectName: "preferencesVerticalScrollBar"
            parent: preferencesScroll
            x: preferencesScroll.width - width
            y: preferencesScroll.topPadding
            height: preferencesScroll.availableHeight
            width: 12
            policy: ScrollBar.AlwaysOn
            background: Rectangle {
                radius: 3
                color: palette.alternateBase
                border.color: palette.mid
            }
            contentItem: Rectangle {
                implicitWidth: 8
                implicitHeight: 8
                radius: 4
                color: palette.dark
            }
        }

        ColumnLayout {
            width: preferencesScroll.availableWidth
            spacing: 8

            GroupBox {
                objectName: "appearancePreferencesGroup"
                title: qsTr("Erscheinungsbild")
                Layout.fillWidth: true
                ColumnLayout {
                    spacing: 4
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("Farbschema") }
                        ComboBox {
                            id: themeBox
                            objectName: "themeModeBox"
                            Layout.fillWidth: true
                            model: [qsTr("Systemstandard"), qsTr("Hell"), qsTr("Dunkel")]
                        }
                        Label {
                            visible: themeBox.currentIndex === 0
                            text: backend.systemTheme === "dark" ? qsTr("System: Dunkel") : qsTr("System: Hell")
                            color: palette.placeholderText
                        }
                    }
                }
            }

            GroupBox {
                objectName: "incomingReferencesPreferencesGroup"
                title: qsTr("Dateiverweise")
                Layout.fillWidth: true
                CheckBox {
                    id: showIncomingFileReferencesCheck
                    objectName: "showIncomingFileReferencesCheck"
                    text: qsTr("Verweise auf ausgewählte Dateien anzeigen")
                }
            }

            GroupBox {
                objectName: "metadataHistoryPreferencesGroup"
                title: qsTr("Metadaten-Historie")
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    RowLayout {
                        Label { text: qsTr("Bearbeitet durch") }
                        TextField { id: auditOperatorField; objectName: "auditOperatorField"; Layout.fillWidth: true }
                    }
                    RowLayout {
                        Label { text: qsTr("Arbeitskopie-Limit (GiB)") }
                        SpinBox { id: workspaceLimit; objectName: "workspaceLimit"; from: 1; to: 1024; editable: true }
                    }
                    RowLayout {
                        Label { text: qsTr("Sicherungskopien behalten") }
                        SpinBox { id: retentionCopies; objectName: "retentionCopies"; from: 1; to: 100; editable: true }
                    }
                    RowLayout {
                        Label { text: qsTr("Mindestalter (Tage)") }
                        SpinBox { id: retentionAge; objectName: "retentionAge"; from: 0; to: 3650; editable: true }
                    }
                }
            }

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
                    TextField { id: reporterField; objectName: "reporterNameField"; Layout.fillWidth: true }
                }
            }

            GroupBox {
                title: qsTr("Sprache")
                Layout.fillWidth: true
                RowLayout {
                    ComboBox { id: languageBox; objectName: "languageBox"; model: ["Deutsch", "Français"] }
                    Label { text: qsTr("Wird nach einem Neustart wirksam."); color: palette.placeholderText }
                }
            }
        }
    }

    onOpened: {
        auditOperatorField.text = backend.auditOperator
        workspaceLimit.value = backend.workspaceLimitGiB
        retentionCopies.value = backend.retentionCopies
        retentionAge.value = backend.retentionAgeDays
        sipNameCheck.checked = backend.validateSipName
        thresholdSpin.value = backend.expandThreshold
        hitsSpin.value = backend.maxSearchHits
        sampleModeBox.currentIndex = backend.sampleMode === "percent" ? 1 : 0
        sampleSizeSpin.value = backend.sampleSize
        reporterField.text = backend.reporterName
        languageBox.currentIndex = backend.language === "fr" ? 1 : 0
        themeBox.currentIndex = backend.themeMode === "light" ? 1 : backend.themeMode === "dark" ? 2 : 0
        showIncomingFileReferencesCheck.checked = backend.showIncomingFileReferences
    }
    onAccepted: {
        backend.auditOperator = auditOperatorField.text
        backend.workspaceLimitGiB = workspaceLimit.value
        backend.retentionCopies = retentionCopies.value
        backend.retentionAgeDays = retentionAge.value
        backend.validateSipName = sipNameCheck.checked
        backend.expandThreshold = thresholdSpin.value
        backend.maxSearchHits = hitsSpin.value
        backend.sampleMode = sampleModeBox.currentIndex === 1 ? "percent" : "absolute"
        backend.sampleSize = sampleSizeSpin.value
        backend.reporterName = reporterField.text
        backend.language = languageBox.currentIndex === 1 ? "fr" : "de"
        backend.themeMode = ["system", "light", "dark"][themeBox.currentIndex]
        backend.showIncomingFileReferences = showIncomingFileReferencesCheck.checked
    }
}
