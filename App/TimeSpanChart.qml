import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Vergleich von Zeiträumen (10.8.1): dark = clear span, light = contains «keine Angabe», dashed end = open.
Item {
    id: root

    property var chart: ({ bars: [] })
    readonly property real span: Math.max(1, (chart.to ?? 1) - (chart.from ?? 0))
    readonly property int labelWidth: 120

    implicitHeight: column.implicitHeight

    function xFor(value, width) {
        return (value - (chart.from ?? 0)) / span * width
    }

    ColumnLayout {
        id: column
        width: root.width
        spacing: 4

        Repeater {
            model: root.chart.bars || []

            delegate: RowLayout {
                id: barRow
                required property var modelData
                Layout.fillWidth: true
                spacing: 8

                Label {
                    id: spanLabel
                    Layout.preferredWidth: root.labelWidth
                    text: barRow.modelData.label
                    elide: Text.ElideRight
                    ToolTip.visible: spanLabelHover.hovered && truncated
                    ToolTip.text: text
                    HoverHandler { id: spanLabelHover }
                }

                Item {
                    id: track
                    Layout.fillWidth: true
                    Layout.preferredHeight: 18

                    Rectangle { anchors.fill: parent; color: "transparent"; border.color: palette.mid; radius: 2 }

                    Rectangle {
                        visible: barRow.modelData.state === "clear" || barRow.modelData.state === "open"
                        x: barRow.modelData.start != null ? root.xFor(barRow.modelData.start, track.width) : 0
                        width: (barRow.modelData.end != null ? root.xFor(barRow.modelData.end, track.width) : track.width) - x
                        height: parent.height
                        radius: 2
                        color: barRow.modelData.state === "clear" ? "#1565c0" : "#90caf9"
                        border.width: barRow.modelData.openStart || barRow.modelData.openEnd ? 1 : 0
                        border.color: "#0d47a1"
                    }

                    Rectangle {
                        visible: barRow.modelData.state === "unknown"
                        anchors.fill: parent
                        color: "#90caf9"
                        opacity: 0.5
                    }
                }

                Label {
                    id: spanValueLabel
                    Layout.preferredWidth: 150
                    text: barRow.modelData.text
                    color: palette.placeholderText
                    elide: Text.ElideRight
                    ToolTip.visible: spanValueHover.hovered && truncated
                    ToolTip.text: text
                    HoverHandler { id: spanValueHover }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: (root.chart.bars || []).length > 0
            Item { Layout.preferredWidth: root.labelWidth }
            Label { text: root.chart.from ?? "" }
            Item { Layout.fillWidth: true }
            Label { text: root.chart.to ?? "" }
            Item { Layout.preferredWidth: 150 }
        }
    }
}
