import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: root

    property string title: ""
    property bool open: true
    property bool floating: false
    property Item dockParent: null
    property var dropSource: null
    default property alias contentData: contentHost.data

    signal titleDoubleClicked()

    implicitWidth: 420
    implicitHeight: 280

    function undock() {
        if (floating)
            return
        dockParent = parent
        floating = true
        parent = floatingWindow.contentItem
        anchors.fill = floatingWindow.contentItem
        floatingWindow.show()
    }

    function dockInto(targetParent) {
        const destination = targetParent || dockParent
        if (!destination)
            return
        floatingWindow.hide()
        floating = false
        anchors.fill = null
        if (parent !== destination) {
            parent = null
            parent = destination
        }
        dockParent = destination
        open = true
    }

    function closePanel() {
        if (floating)
            dockInto(dockParent)
        open = false
    }

    Drag.active: titleDrag.active
    Drag.source: root
    Drag.supportedActions: Qt.MoveAction
    Drag.keys: ["package-turbo-dock"]

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        ToolBar {
            Layout.fillWidth: true

            RowLayout {
                anchors.fill: parent
                spacing: 2

                Label {
                    text: root.title
                    font.bold: true
                    leftPadding: 6
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                    TapHandler { onDoubleTapped: root.titleDoubleClicked() }
                    DragHandler {
                        id: titleDrag
                        target: null
                    }
                    ToolTip.visible: titleHover.hovered
                    ToolTip.delay: 700
                    ToolTip.text: qsTr("Ziehen zum Verschieben; Doppelklick zum Maximieren")
                    HoverHandler { id: titleHover }
                }

                ToolButton {
                    text: root.floating ? "\u2199" : "\u2197"
                    ToolTip.visible: hovered
                    ToolTip.text: root.floating ? qsTr("Ansicht wieder andocken") : qsTr("Ansicht abdocken")
                    onClicked: root.floating ? root.dockInto(root.dockParent) : root.undock()
                }

                ToolButton {
                    text: "\u00d7"
                    ToolTip.visible: hovered
                    ToolTip.text: qsTr("Ansicht schliessen")
                    onClicked: root.closePanel()
                }
            }
        }

        Item {
            id: contentHost
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
        }
    }

    DropArea {
        anchors.fill: parent
        keys: ["package-turbo-dock"]
        onDropped: function (drop) {
            root.dropSource = drop.source
            if (root.dropSource && root.dropSource !== root && root.dropSource.dockInto)
                root.dropSource.dockInto(root.parent)
            root.dropSource = null
        }
    }

    Window {
        id: floatingWindow
        title: root.title
        width: 760
        height: 560
        visible: false
        onClosing: function (close) {
            close.accepted = false
            root.closePanel()
        }
    }
}
