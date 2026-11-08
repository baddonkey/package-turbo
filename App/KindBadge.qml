import QtQuick

// Small coloured marker that stands in for the object icons of the original application.
Rectangle {
    id: badge

    property string kind: ""
    property bool assigned: false

    readonly property var spec: ({
        "paket": ["P", "#607d8b"],
        "ablieferung": ["A", "#6d4c41"],
        "provenienz": ["Pv", "#8d6e63"],
        "ordnungssystem": ["OS", "#3949ab"],
        "ordnungssystemposition": ["OSP", "#5c6bc0"],
        "dossier": ["D", "#f9a825"],
        "subdossier": ["SD", "#fbc02d"],
        "dokument": ["Dk", "#43a047"],
        "vorgang": ["V", "#00897b"],
        "aktivitaet": ["Ak", "#26a69a"],
        "mappe": ["M", "#8e24aa"],
        "datei": ["F", "#1e88e5"],
        "ordner": ["O", "#fb8c00"]
    })

    function linearChannel(value) {
        return value <= 0.04045 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4)
    }

    readonly property real luminance: 0.2126 * linearChannel(color.r)
                                     + 0.7152 * linearChannel(color.g)
                                     + 0.0722 * linearChannel(color.b)

    implicitWidth: Math.max(22, label.implicitWidth + 8)
    implicitHeight: 16
    radius: 3
    color: (spec[kind] || ["?", "#9e9e9e"])[1]

    Text {
        id: label
        objectName: "kindBadgeText"
        anchors.centerIn: parent
        text: (badge.spec[badge.kind] || ["?"])[0] + (badge.assigned ? "\u2197" : "")
        color: badge.luminance > 0.179 ? "black" : "white"
        font.pixelSize: 10
        font.bold: true
    }
}
