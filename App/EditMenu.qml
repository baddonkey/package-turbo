import QtQuick
import QtQuick.Controls

// Cut / copy / paste / undo for text fields (Bearbeiten-Menü, user documentation 9.1).
Menu {
    id: menu

    property Item target: null

    MenuItem { text: qsTr("Rückgängig"); enabled: menu.target && menu.target.canUndo; onTriggered: menu.target.undo() }
    MenuSeparator {}
    MenuItem { text: qsTr("Ausschneiden"); enabled: menu.target && !menu.target.readOnly && menu.target.selectedText.length > 0; onTriggered: menu.target.cut() }
    MenuItem { text: qsTr("Kopieren"); enabled: menu.target && menu.target.selectedText.length > 0; onTriggered: menu.target.copy() }
    MenuItem { text: qsTr("Einfügen"); enabled: menu.target && !menu.target.readOnly && menu.target.canPaste; onTriggered: menu.target.paste() }
    MenuItem { text: qsTr("Löschen"); enabled: menu.target && !menu.target.readOnly && menu.target.selectedText.length > 0; onTriggered: menu.target.remove(menu.target.selectionStart, menu.target.selectionEnd) }
}
