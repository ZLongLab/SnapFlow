"""CleanShot-style screenshot beautifier: gradient backdrops, rounded shadow, aspect ratio & window chrome."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .capture_icons import line_icon
from .windows_identity import apply_dark_titlebar

BEAUTIFY_PRESETS = [
    {'id': 'aurora', 'name': '极光紫蓝', 'stops': ('#3b82f6', '#6366f1', '#a855f7')},
    {'id': 'sunset', 'name': '日落珊瑚', 'stops': ('#f97316', '#ec4899', '#8b5cf6')},
    {'id': 'emerald', 'name': '翡翠极境', 'stops': ('#0f766e', '#0d9488', '#38bdf8')},
    {'id': 'obsidian', 'name': '深空星耀', 'stops': ('#0f172a', '#1e293b', '#334155')},
    {'id': 'rose', 'name': '玫瑰云雾', 'stops': ('#fb7185', '#f472b6', '#c084fc')},
    {'id': 'ocean', 'name': '海洋玻璃', 'stops': ('#0284c7', '#2563eb', '#4f46e5')},
    {'id': 'paper', 'name': '暖白纸感', 'stops': ('#f8fafc', '#e2e8f0', '#cbd5e1')},
    {'id': 'transparent', 'name': '透明纯影', 'transparent': True},
]

_RATIOS = {
    'auto': None,
    '16:9': 16 / 9,
    '4:3': 4 / 3,
    '1:1': 1.0,
}

BEAUTIFY_QSS = """
QDialog { background:#0b0e16; color:#e6eef8; font-family:'Microsoft YaHei UI'; font-size:13px; }
QFrame#controlPanel { background:#121724; border-left:1px solid rgba(255,255,255,18); }
QLabel#panelSection { font-size:12px; font-weight:700; color:#9eb2ca; background:transparent; }
QLabel#valueTag { font-size:12px; font-weight:600; color:#7dd3fc; background:transparent; }
QLabel#dimPill { font-size:11px; color:#d7e5f5; background:rgba(12,18,30,195); border:1px solid rgba(255,255,255,28); border-radius:8px; padding:4px 10px; }
QLabel#errorLabel { font-size:12px; color:#fca5a5; background:transparent; }

QPushButton#ratioPill {
    background-color:rgba(255,255,255,10); color:#b8c8da; border:1px solid rgba(255,255,255,22);
    border-radius:8px; padding:6px 8px; font-size:12px; font-weight:500;
}
QPushButton#ratioPill:hover { background-color:rgba(255,255,255,20); color:#ffffff; }
QPushButton#ratioPill:checked { background-color:rgba(59,130,246,68); border-color:#60a5fa; color:#ffffff; font-weight:600; }

QCheckBox { color:#dce7f5; spacing:8px; font-size:12px; }
QCheckBox::indicator { width:16px; height:16px; border-radius:5px; border:1px solid rgba(160,195,230,75); background:#0d1320; }
QCheckBox::indicator:checked { background:#3b82f6; border-color:#60a5fa; }

QSlider::groove:horizontal { height:5px; background:#1e293b; border-radius:2px; }
QSlider::sub-page:horizontal { background:#3b82f6; border-radius:2px; }
QSlider::handle:horizontal { width:14px; height:14px; margin:-5px 0; border-radius:7px; background:#f8fafc; border:1px solid #93c5fd; }

QPushButton#primaryAction {
    background-color:#f8fbff; color:#0b101b; border:1px solid #ffffff; border-radius:10px;
    padding:9px 14px; font-size:13px; font-weight:700;
}
QPushButton#primaryAction:hover { background-color:#ffffff; }
QPushButton#secondaryAction {
    background-color:rgba(255,255,255,14); color:#e4eef8; border:1px solid rgba(255,255,255,28);
    border-radius:10px; padding:8px 12px; font-size:12px; font-weight:600;
}
QPushButton#secondaryAction:hover { background-color:rgba(96,165,250,35); border-color:#60a5fa; color:#ffffff; }
"""


def _preset_by_id(preset_id: str) -> dict:
    for item in BEAUTIFY_PRESETS:
        if item['id'] == preset_id:
            return item
    return BEAUTIFY_PRESETS[0]


def render_beautified(image: QImage, options: dict | None = None) -> QImage:
    """Render screenshot with gradient background, rounded card, shadow, and optional macOS chrome."""
    if image.isNull():
        raise ValueError('图片内容为空')
    cfg = {
        'preset': 'aurora',
        'padding': 56,
        'radius': 14,
        'shadow': 24,
        'ratio': 'auto',
        'window_chrome': False,
    }
    if options:
        cfg.update(options)

    padding = max(0, min(160, int(cfg['padding'])))
    radius = max(0, min(40, int(cfg['radius'])))
    shadow = max(0, min(48, int(cfg['shadow'])))
    chrome_h = 34 if cfg['window_chrome'] else 0
    preset = _preset_by_id(str(cfg['preset']))

    src = image.convertToFormat(QImage.Format.Format_ARGB32)
    src.setDevicePixelRatio(1)
    card_w = src.width()
    card_h = src.height() + chrome_h

    outer_w = card_w + padding * 2
    outer_h = card_h + padding * 2
    target_ratio = _RATIOS.get(cfg['ratio'])
    if target_ratio:
        if outer_w / max(1, outer_h) < target_ratio:
            outer_w = math.ceil(outer_h * target_ratio)
        else:
            outer_h = math.ceil(outer_w / target_ratio)

    out = QImage(max(1, outer_w), max(1, outer_h), QImage.Format.Format_ARGB32)
    out.setDevicePixelRatio(1)
    out.fill(Qt.GlobalColor.transparent)

    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    if not preset.get('transparent'):
        stops = preset['stops']
        grad = QLinearGradient(0, 0, outer_w, outer_h)
        grad.setColorAt(0.0, QColor(stops[0]))
        grad.setColorAt(0.52, QColor(stops[1]))
        grad.setColorAt(1.0, QColor(stops[2]))
        p.fillRect(0, 0, outer_w, outer_h, grad)

        glow = QRadialGradient(QPointF(outer_w * 0.2, outer_h * 0.15), max(outer_w, outer_h) * 0.65)
        glow.setColorAt(0.0, QColor(255, 255, 255, 38))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(0, 0, outer_w, outer_h, glow)

    card_x = (outer_w - card_w) / 2.0
    card_y = (outer_h - card_h) / 2.0
    card_rect = QRectF(card_x, card_y, card_w, card_h)

    if shadow > 0:
        p.setPen(Qt.PenStyle.NoPen)
        steps = 10
        for idx in range(steps, 0, -1):
            frac = idx / steps
            spread = shadow * frac
            alpha = max(2, int(22 * (1.0 - frac * 0.72)))
            p.setBrush(QColor(5, 8, 18, alpha))
            s_rect = card_rect.adjusted(-spread * 0.55, -spread * 0.35 + shadow * 0.25, spread * 0.55, spread * 0.75 + shadow * 0.25)
            p.drawRoundedRect(s_rect, radius + spread * 0.35, radius + spread * 0.35)

    clip = QPainterPath()
    clip.addRoundedRect(card_rect, radius, radius)
    p.save()
    p.setClipPath(clip)

    if chrome_h:
        bar_rect = QRectF(card_x, card_y, card_w, chrome_h)
        p.fillRect(bar_rect, QColor('#181f2e'))
        p.setPen(Qt.PenStyle.NoPen)
        for i, dot_color in enumerate(('#ff5f57', '#febc2e', '#28c840')):
            p.setBrush(QColor(dot_color))
            p.drawEllipse(QPointF(card_x + 18 + i * 20, card_y + chrome_h / 2.0), 5.5, 5.5)
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawLine(QPointF(card_x, card_y + chrome_h - 0.5), QPointF(card_x + card_w, card_y + chrome_h - 0.5))

    p.drawImage(QRectF(card_x, card_y + chrome_h, src.width(), src.height()), src)
    p.restore()

    if radius > 0:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 52), 1.0))
        p.drawRoundedRect(card_rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.end()
    return out


class PresetSwatch(QPushButton):
    def __init__(self, preset: dict, parent=None):
        super().__init__('', parent)
        self.preset = preset
        self.setCheckable(True)
        self.setFixedSize(56, 38)
        self.setToolTip(preset['name'])
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 9, 9)
        p.save()
        p.setClipPath(clip)
        if self.preset.get('transparent'):
            cell = 7
            for y in range(0, self.height(), cell):
                for x in range(0, self.width(), cell):
                    p.fillRect(x, y, cell, cell, QColor('#263042' if (x // cell + y // cell) % 2 == 0 else '#1a2230'))
        else:
            stops = self.preset['stops']
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, QColor(stops[0]))
            grad.setColorAt(0.5, QColor(stops[1]))
            grad.setColorAt(1.0, QColor(stops[2]))
            p.fillRect(rect, grad)
        p.restore()

        if self.isChecked():
            p.setPen(QPen(QColor('#ffffff'), 2.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 10, 10)
        else:
            p.setPen(QPen(QColor(255, 255, 255, 36), 1.0))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect, 9, 9)
        p.end()


class BeautifyPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, image: QImage):
        self.image = image
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor('#0b0e16'))
        if self.image is None or self.image.isNull():
            p.end()
            return
        avail = QRectF(self.rect()).adjusted(22, 22, -22, -22)
        scale = min(avail.width() / max(1, self.image.width()), avail.height() / max(1, self.image.height()), 1.0)
        dw = self.image.width() * scale
        dh = self.image.height() * scale
        target = QRectF(avail.center().x() - dw / 2, avail.center().y() - dh / 2, dw, dh)

        # Subtle checkerboard behind transparent canvas
        clip = QPainterPath()
        clip.addRoundedRect(target, 6, 6)
        p.save()
        p.setClipPath(clip)
        cell = 12
        start_x, start_y = int(target.left()), int(target.top())
        for y in range(start_y, int(target.bottom()) + cell, cell):
            for x in range(start_x, int(target.right()) + cell, cell):
                c = '#1b2232' if ((x - start_x) // cell + (y - start_y) // cell) % 2 == 0 else '#141926'
                p.fillRect(x, y, cell, cell, QColor(c))
        p.drawImage(target, self.image)
        p.restore()
        p.end()


class BeautifyDialog(QDialog):
    """Live CleanShot-style screenshot beautifier dialog."""

    def __init__(self, image: QImage, controller=None, parent=None):
        super().__init__(parent)
        self.source_image = image.copy()
        self.controller = controller
        self.rendered_image = self.source_image
        self.options = {
            'preset': 'aurora',
            'padding': 56,
            'radius': 14,
            'shadow': 24,
            'ratio': 'auto',
            'window_chrome': False,
        }

        self.setWindowTitle('美化套壳 · SnapFlow')
        self.resize(980, 640)
        self.setMinimumSize(780, 540)
        self.setStyleSheet(BEAUTIFY_QSS)
        apply_dark_titlebar(self)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        left = QVBoxLayout()
        left.setContentsMargins(14, 14, 14, 14)
        left.setSpacing(8)
        self.preview = BeautifyPreview()
        left.addWidget(self.preview, 1)

        bottom_info = QHBoxLayout()
        self.dim_label = QLabel()
        self.dim_label.setObjectName('dimPill')
        self.error_label = QLabel()
        self.error_label.setObjectName('errorLabel')
        bottom_info.addWidget(self.error_label, 1)
        bottom_info.addWidget(self.dim_label)
        left.addLayout(bottom_info)
        root.addLayout(left, 1)

        panel = QFrame()
        panel.setObjectName('controlPanel')
        panel.setFixedWidth(280)
        p_layout = QVBoxLayout(panel)
        p_layout.setContentsMargins(18, 18, 18, 18)
        p_layout.setSpacing(14)

        sec1 = QLabel('背景主题')
        sec1.setObjectName('panelSection')
        p_layout.addWidget(sec1)

        grid = QGridLayout()
        grid.setSpacing(8)
        self.preset_group = QButtonGroup(self)
        self.preset_buttons = {}
        for idx, preset in enumerate(BEAUTIFY_PRESETS):
            btn = PresetSwatch(preset)
            btn.setChecked(preset['id'] == 'aurora')
            btn.clicked.connect(lambda _=False, pid=preset['id']: self._set_option('preset', pid))
            self.preset_group.addButton(btn)
            self.preset_buttons[preset['id']] = btn
            grid.addWidget(btn, idx // 4, idx % 4)
        p_layout.addLayout(grid)

        self.sliders = {}
        for key, label, minimum, maximum, initial in (
            ('padding', '内边距', 0, 120, 56),
            ('radius', '圆角', 0, 32, 14),
            ('shadow', '阴影强度', 0, 40, 24),
        ):
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setObjectName('panelSection')
            val = QLabel(f'{initial} px' if key != 'shadow' else f'{initial}')
            val.setObjectName('valueTag')
            row.addWidget(lbl)
            row.addStretch(1)
            row.addWidget(val)
            p_layout.addLayout(row)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(minimum, maximum)
            slider.setValue(initial)
            slider.valueChanged.connect(
                lambda v, k=key, tag=val: (tag.setText(f'{v} px' if k != 'shadow' else f'{v}'), self._set_option(k, v))
            )
            p_layout.addWidget(slider)
            self.sliders[key] = slider

        sec_ratio = QLabel('画面比例')
        sec_ratio.setObjectName('panelSection')
        p_layout.addWidget(sec_ratio)

        ratio_row = QHBoxLayout()
        ratio_row.setSpacing(6)
        self.ratio_group = QButtonGroup(self)
        self.ratio_buttons = {}
        for r_key, r_label in (('auto', '自适应'), ('16:9', '16:9'), ('4:3', '4:3'), ('1:1', '1:1')):
            btn = QPushButton(r_label)
            btn.setObjectName('ratioPill')
            btn.setCheckable(True)
            btn.setChecked(r_key == 'auto')
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, rk=r_key: self._set_option('ratio', rk))
            self.ratio_group.addButton(btn)
            self.ratio_buttons[r_key] = btn
            ratio_row.addWidget(btn, 1)
        p_layout.addLayout(ratio_row)

        self.chrome_check = QCheckBox('显示窗口顶栏（红黄绿圆点）')
        self.chrome_check.toggled.connect(lambda checked: self._set_option('window_chrome', checked))
        p_layout.addWidget(self.chrome_check)

        p_layout.addStretch(1)

        copy_btn = QPushButton('复制到剪贴板')
        copy_btn.setObjectName('primaryAction')
        copy_btn.setIcon(line_icon('copy', '#0b101b'))
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.clicked.connect(self.copy_result)
        p_layout.addWidget(copy_btn)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        pin_btn = QPushButton('贴到屏幕')
        pin_btn.setObjectName('secondaryAction')
        pin_btn.setIcon(line_icon('pin', '#e4eef8'))
        pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pin_btn.clicked.connect(self.pin_result)

        save_btn = QPushButton('保存 PNG')
        save_btn.setObjectName('secondaryAction')
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self.save_result)

        action_row.addWidget(pin_btn, 1)
        action_row.addWidget(save_btn, 1)
        p_layout.addLayout(action_row)

        root.addWidget(panel)
        self.refresh_preview()

    def _set_option(self, key: str, value):
        self.options[key] = value
        self.refresh_preview()

    def refresh_preview(self):
        self.rendered_image = render_beautified(self.source_image, self.options)
        self.preview.set_image(self.rendered_image)
        self.dim_label.setText(f'输出尺寸：{self.rendered_image.width()} × {self.rendered_image.height()} px')

    def copy_result(self):
        try:
            from .screen_capture import copy_image

            copy_image(self.rendered_image)
        except Exception as exc:
            self.error_label.setText('复制失败：' + str(exc))
            return
        if self.controller and hasattr(self.controller, 'notify'):
            self.controller.notify('美化截图已复制', '可直接粘贴到聊天窗口或文档')
        self.accept()

    def pin_result(self):
        if self.controller and hasattr(self.controller, 'pin_image'):
            self.controller.pin_image(self.rendered_image)
        self.accept()

    def save_result(self):
        try:
            from .screen_capture import copy_image, save_png

            directory = (
                Path(self.controller.settings['directory'])
                if self.controller and hasattr(self.controller, 'settings')
                else Path.home() / 'Desktop'
            )
            path = save_png(self.rendered_image, directory)
            if self.controller:
                self.controller.last_saved = path
                if hasattr(self.controller, '_notify_window_refresh'):
                    self.controller._notify_window_refresh()
        except Exception as exc:
            self.error_label.setText('保存失败：' + str(exc))
            return
        try:
            copy_image(self.rendered_image)
        except Exception:
            pass
        if self.controller and hasattr(self.controller, 'notify'):
            self.controller.notify('美化截图已保存', str(path))
        self.accept()
