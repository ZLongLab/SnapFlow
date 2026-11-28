"""Frosted capture controls sampled only from the existing frozen screenshot."""
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame

SELECTION_COLOR = '#85c9ee'
CORNER_COLOR = '#c4eaff'
HANDLE_COLOR = '#639fc2'
ICON_COLOR = '#d4e5f1'
MUTED_ICON_COLOR = '#9fb8cb'

PANEL_STYLE = '''
QFrame#selectionPanel { background:#172a3b; border:0; border-radius:14px; }
QFrame#selectionPanel[frosted="true"] { background:transparent; }
QPushButton { font-family:"Microsoft YaHei UI"; font-size:12px; color:#e8f2fa; background:transparent; border:1px solid transparent; border-radius:8px; padding:6px 10px; }
QPushButton:hover { background:rgba(185,221,245,24); }
QPushButton:focus { border-color:#85c9ee; }
QPushButton:checked, QPushButton#confirmSelection { color:white; background:#2c81ac; font-weight:600; }
QPushButton:checked:hover, QPushButton#confirmSelection:hover { background:#3897c2; }
QPushButton:pressed { background:#235f83; }
QPushButton:disabled { color:#738c9e; background:transparent; border-color:transparent; }
QPushButton#modePill { color:#b8d0e2; background:transparent; border:1px solid transparent; border-radius:8px; padding:5px 9px; font-weight:500; }
QPushButton#modePill:hover { color:#eef7ff; background:rgba(185,221,245,20); }
QPushButton#modePill:checked { color:#eef7ff; background:rgba(133,201,238,34); border-color:rgba(133,201,238,110); font-weight:600; }
QPushButton#skipCountdown { color:#ffffff; background:#10b981; border:1px solid #34d399; border-radius:8px; padding:6px 11px; font-weight:600; }
QPushButton#skipCountdown:hover { background:#059669; }
QPushButton#colorChoice { border:1.5px solid rgba(255,255,255,78); border-radius:10px; padding:0; }
QPushButton#colorChoice:hover { border-color:rgba(255,255,255,190); }
QPushButton#colorChoice:checked { border:2.5px solid #e4f5ff; }
QPushButton#sizePreset { background:rgba(185,221,245,12); border:1px solid transparent; border-radius:7px; padding:0; }
QPushButton#sizePreset:hover { background:rgba(185,221,245,28); }
QPushButton#sizePreset:checked { background:rgba(133,201,238,44); border-color:#85c9ee; }
QFrame#styleSubBar { background:rgba(6,17,29,76); border:1px solid rgba(187,219,242,24); border-radius:10px; }
QLabel, QLabel#selectionHint { font-family:"Microsoft YaHei UI"; font-size:12px; color:#b9cfdf; background:transparent; border:0; }
QLabel#styleHint { font-family:"Microsoft YaHei UI"; font-size:11px; color:#86a6be; background:transparent; border:0; }
QSpinBox { color:#eef7ff; font-size:12px; font-weight:600; background:rgba(6,19,31,125); border:1px solid rgba(194,222,243,45); border-radius:6px; padding:1px 4px 1px 6px; }
QSpinBox:focus { border-color:#85c9ee; }
QSpinBox::up-button, QSpinBox::down-button { width:16px; border:0; background:rgba(185,221,245,18); }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background:rgba(185,221,245,38); }
QComboBox#captureAudio { font-family:"Microsoft YaHei UI"; font-size:12px; color:#e8f2fa; background:rgba(184,218,242,18); border:1px solid transparent; border-radius:8px; padding:4px 8px; }
QComboBox#captureAudio:focus { border-color:#85c9ee; }
QComboBox#captureAudio QAbstractItemView { background:#172a3b; color:#e8f2fa; selection-background-color:#2c81ac; border:1px solid #37576d; }
QFrame#selectionDivider { background:rgba(187,219,242,35); border:0; }
QToolTip { background:#172a3b; color:#e8f2fa; border:0; padding:6px 9px; }
'''


class CaptureGlassPanel(QFrame):
    def __init__(self, overlay):
        super().__init__(overlay)
        self.setObjectName('selectionPanel')
        self.setProperty('frosted', True)
        self.setStyleSheet(PANEL_STYLE)

    def paintEvent(self, event):
        overlay = self.parentWidget()
        image = overlay.image
        key = (image.cacheKey(), overlay.width(), overlay.height())
        if getattr(overlay, '_capture_frost_key', None) != key:
            # One low-resolution cache per frozen image, shared by panels.
            overlay._capture_frost = image.scaled(
                max(1, overlay.width() // 18),
                max(1, overlay.height() // 18),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            overlay._capture_frost_key = key
        frost = overlay._capture_frost
        origin = self.mapTo(overlay, QPoint(0, 0))
        sx = frost.width() / max(1, overlay.width())
        sy = frost.height() / max(1, overlay.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(self.rect()), 14, 14)
        painter.setClipPath(shape)
        painter.drawImage(
            QRectF(self.rect()),
            frost,
            QRectF(origin.x() * sx, origin.y() * sy, self.width() * sx, self.height() * sy),
        )
        painter.fillRect(self.rect(), QColor(12, 28, 43, 224))
        shine = QLinearGradient(0, 0, 0, self.height())
        shine.setColorAt(0, QColor(210, 235, 255, 18))
        shine.setColorAt(1, QColor(210, 235, 255, 0))
        painter.fillRect(self.rect(), shine)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(193, 223, 245, 34), 1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 14, 14)


def paint_panel_shadows(painter, panels):
    """A small shadow painted once, avoiding nested widget effect artifacts."""
    painter.setPen(Qt.PenStyle.NoPen)
    for panel in panels:
        if panel.isHidden():
            continue
        rect = QRectF(panel.geometry()).translated(0, 3)
        for spread, alpha in ((8, 3), (6, 4), (4, 5), (2, 7), (0, 12)):
            painter.setBrush(QColor(2, 8, 16, alpha))
            painter.drawRoundedRect(rect.adjusted(-spread, -spread, spread, spread), 14 + spread, 14 + spread)
