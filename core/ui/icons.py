"""Small inline SVG icons tinted with the current palette so they follow light and dark themes."""
from qgis.PyQt.QtCore import QByteArray
from qgis.PyQt.QtGui import QIcon, QPalette, QPixmap
from qgis.PyQt.QtWidgets import QApplication

_STROKE = ('<g fill="none" stroke="{fg}" stroke-width="2" stroke-linecap="round" '
           'stroke-linejoin="round">{body}</g>')

_SHAPES = {
    "new_session": _STROKE.format(fg="{fg}", body=(
        '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/><path d="M8 12h8"/><path d="M12 8v8"/>')),
    "sessions": _STROKE.format(fg="{fg}", body=(
        '<path d="M9 6h11"/><path d="M9 12h11"/><path d="M9 18h11"/>'
        '<path d="M4 6h.01"/><path d="M4 12h.01"/><path d="M4 18h.01"/>')),
    "settings": _STROKE.format(fg="{fg}", body=(
        '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08'
        'a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74'
        'l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25'
        'a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25'
        'a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08'
        'a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38'
        'a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
        '<circle cx="12" cy="12" r="3"/>')),
    "send": ('<circle cx="12" cy="12" r="11" fill="{accent}"/>'
             '<g fill="none" stroke="{on_accent}" stroke-width="2.2" stroke-linecap="round" '
             'stroke-linejoin="round"><path d="M12 17V7"/><path d="M7.5 11.5 12 7l4.5 4.5"/></g>'),
    "stop": ('<circle cx="12" cy="12" r="11" fill="{accent}"/>'
             '<rect x="8" y="8" width="8" height="8" rx="1.5" fill="{on_accent}"/>'),
}


def icon(name):
    palette = QApplication.palette()
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 24 24">'
           + _SHAPES[name].format(fg=palette.color(QPalette.ColorRole.ButtonText).name(),
                                  accent=palette.color(QPalette.ColorRole.Highlight).name(),
                                  on_accent=palette.color(QPalette.ColorRole.HighlightedText).name())
           + '</svg>')
    pixmap = QPixmap()
    pixmap.loadFromData(QByteArray(svg.encode()), "SVG")
    return QIcon(pixmap)
