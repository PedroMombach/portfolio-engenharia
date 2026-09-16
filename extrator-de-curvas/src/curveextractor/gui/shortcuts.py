"""Apply each action's user-editable shortcut."""

from PySide6.QtGui import QKeySequence


def apply_shortcuts(actions, settings):
    for key, action in actions.items():
        if key in settings["shortcuts"]:
            action.setShortcut(QKeySequence(settings["shortcuts"][key]))
