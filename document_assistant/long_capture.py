"""User-controlled scrolling capture with refined floating controls, width-fit preview, and click-through outline."""
import ctypes
from collections import deque
from datetime import datetime
import hashlib
import json
import math
import marshal
import os
from pathlib import Path
import sys
import time
import uuid
from fractions import Fraction
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QScreen
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from .capture_icons import line_icon
from .capture_pixels import crop_selection
from .long_stitch import VerticalStitcher
from .video_ui import controls_position

_SHADOW = 10


def _paint_floating_card(painter: QPainter, widget_rect, dark: bool, radius: int = 14):
    """Paint an elevated Mist Light or Slate Dark translucent floating card with soft drop shadow."""
    content = QRectF(widget_rect).adjusted(_SHADOW, _SHADOW, -_SHADOW, -_SHADOW)
    painter.setPen(Qt.PenStyle.NoPen)
    shadow_layers = ((9, 4), (7, 6), (5, 9), (3, 13), (1, 18)) if not dark else ((9, 6), (7, 10), (5, 14), (3, 20), (1, 26))
    for spread, alpha in shadow_layers:
        painter.setBrush(QColor(8, 15, 28, alpha))
        painter.drawRoundedRect(
            content.adjusted(-spread * 0.7, -spread * 0.4 + 2, spread * 0.7, spread * 0.9 + 3),
            radius + spread * 0.4,
            radius + spread * 0.4,
        )

    card_path = QPainterPath()
    card_path.addRoundedRect(content, radius, radius)
    bg = QColor(20, 28, 43, 242) if dark else QColor(255, 255, 255, 248)
    painter.fillPath(card_path, bg)

    # Subtle top sheen
    sheen = QLinearGradient(content.topLeft(), QPointF(content.left(), content.top() + 28))
    sheen.setColorAt(0.0, QColor(255, 255, 255, 16 if dark else 90))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillPath(card_path, sheen)

    border = QColor(148, 163, 184, 58) if dark else QColor(148, 163, 184, 78)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(border, 1.0))
    painter.drawRoundedRect(content.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    return content


def capture_region(screen, rect, geometry):
    """Grab a padded region with the same physical origin as a full snapshot.

    Qt's grab offsets are logical integers. Align them to the DPR denominator
    first (e.g. multiples of 2 at 150%) so Qt rounding cannot move the crop.
    """
    ratio = screen.devicePixelRatio()
    fraction = Fraction(ratio).limit_denominator(16)
    if sys.platform != 'win32' or abs(float(fraction) - ratio) > 1e-6:
        return crop_selection(screen.grabWindow(0).toImage(), rect, geometry.size())
    bounds = QRectF(0, 0, geometry.width(), geometry.height())
    rect = QRectF(rect).normalized().intersected(bounds)
    unit = fraction.denominator
    # Rounded logical screen extents can exceed the native framebuffer by one
    # pixel. At those edges let the full-snapshot crop clamp to its actual size.
    if unit > 1 and (rect.right() > geometry.width() - unit or rect.bottom() > geometry.height() - unit):
        return crop_selection(screen.grabWindow(0).toImage(), rect, geometry.size())
    left = math.floor(rect.left() / unit) * unit
    top = math.floor(rect.top() / unit) * unit
    right = math.ceil(rect.right() / unit) * unit
    bottom = math.ceil(rect.bottom() / unit) * unit
    image = screen.grabWindow(0, left, top, right - left, bottom - top).toImage()
    x = math.floor(rect.left() * ratio) - round(left * ratio)
    y = math.floor(rect.top() * ratio) - round(top * ratio)
    width = math.ceil(rect.right() * ratio) - math.floor(rect.left() * ratio)
    height = math.ceil(rect.bottom() * ratio) - math.floor(rect.top() * ratio)
    if image.isNull() or x + width > image.width() or y + height > image.height():
        raise OSError('无法获取完整截图区域，请重新框选')
    image = image.copy(x, y, width, height)
    image.setDevicePixelRatio(1)
    return image


class CaptureKeys(QAbstractNativeEventFilter):
    def __init__(self, finish, cancel):
        super().__init__()
        self.app = QApplication.instance()
        self.registered = {}
        if sys.platform == 'win32':
            self.user32 = ctypes.WinDLL('user32', use_last_error=True)
            self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            for ident, key, callback in ((0x4DA0, 0x0D, finish), (0x4DA1, 0x1B, cancel)):
                if self.user32.RegisterHotKey(None, ident, 0x4000, key):
                    self.registered[ident] = callback
            self.app.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if sys.platform == 'win32':
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and int(msg.wParam) in self.registered:
                QTimer.singleShot(0, self.registered[int(msg.wParam)])
                return True, 0
        return False, 0

    def shutdown(self):
        if sys.platform == 'win32':
            for ident in self.registered:
                self.user32.UnregisterHotKey(None, ident)
            self.app.removeNativeEventFilter(self)
        self.registered.clear()


class RegionOutline(QWidget):
    """Click-through glowing frame drawn strictly outside the captured crop."""

    def __init__(self, region, color='#3b82f6', title='长截图区域 · SnapFlow'):
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setWindowTitle(title)
        self._color = QColor(color)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # 5px outer margin ensures halo & corner caps stay completely outside the recorded pixels.
        self.setGeometry(region.toAlignedRect().adjusted(-5, -5, 5, 5))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        halo = QColor(self._color)
        halo.setAlpha(46)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(halo, 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawRoundedRect(r, 4, 4)

        line_col = QColor(self._color)
        line_col.setAlpha(185)
        p.setPen(QPen(line_col, 1.6))
        p.drawRoundedRect(r, 3, 3)

        # Crisp L-corner accents
        corner = min(16.0, r.width() / 4.0, r.height() / 4.0)
        p.setPen(QPen(self._color, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for pt, dx, dy in (
            (r.topLeft(), 1, 1),
            (r.topRight(), -1, 1),
            (r.bottomLeft(), 1, -1),
            (r.bottomRight(), -1, -1),
        ):
            p.drawLine(pt, pt + QPointF(dx * corner, 0))
            p.drawLine(pt, pt + QPointF(0, dy * corner))
        p.end()


class _PulseDot(QWidget):
    def __init__(self, color='#3b82f6', parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(12, 12)

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        halo = QColor(self._color)
        halo.setAlpha(60)
        p.setBrush(halo)
        p.drawEllipse(QPointF(6, 6), 5.5, 5.5)
        p.setBrush(self._color)
        p.drawEllipse(QPointF(6, 6), 3.2, 3.2)
        p.end()


class LongControls(QWidget):
    finish_requested = Signal()
    cancel_requested = Signal()
    diagnostic_requested = Signal()
    auto_scroll_toggled = Signal(bool)

    def __init__(self, hotkey, dark=False):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('正在采集长截图 · SnapFlow')
        self.stopping = False
        self.dark = bool(dark)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        if self.dark:
            t = {
                'text': '#f1f5f9', 'muted': '#94a7c0', 'pill_bg': 'rgba(59,130,246,38)', 'pill_fg': '#93c5fd',
                'btn_bg': '#232e44', 'btn_border': '#33435e', 'btn_fg': '#e6eef8', 'btn_hover': '#2d3b56',
                'auto_bg': '#064e3b', 'auto_border': '#10b981', 'auto_fg': '#6ee7b7',
                'cancel_hover': 'rgba(239,68,68,42)', 'key_bg': 'rgba(148,163,184,26)', 'key_fg': '#cbd5e1',
                'warn_bg': 'rgba(120,53,15,95)', 'warn_border': 'rgba(245,158,11,95)', 'warn_fg': '#fde68a',
                'icon_ink': '#cbd5e1',
            }
        else:
            t = {
                'text': '#0f172a', 'muted': '#64748b', 'pill_bg': '#eff6ff', 'pill_fg': '#2563eb',
                'btn_bg': '#f8fafd', 'btn_border': '#d6e0ee', 'btn_fg': '#1e293b', 'btn_hover': '#eff6ff',
                'auto_bg': '#ecfdf5', 'auto_border': '#34d399', 'auto_fg': '#047857',
                'cancel_hover': '#fee2e2', 'key_bg': '#eef3f9', 'key_fg': '#475569',
                'warn_bg': '#fffbeb', 'warn_border': '#fcd34d', 'warn_fg': '#92400e',
                'icon_ink': '#475569',
            }

        outer = QVBoxLayout(self)
        outer.setContentsMargins(_SHADOW, _SHADOW, _SHADOW, _SHADOW)
        outer.setSpacing(0)

        card = QFrame(self)
        card.setObjectName('longCard')
        card.setStyleSheet(
            f'QFrame#longCard{{background:transparent;border:0;}}'
            f'QLabel{{color:{t["muted"]};font-family:"Microsoft YaHei UI";font-size:11px;background:transparent;border:0;}}'
            f'QLabel#longCount{{font-size:13px;font-weight:700;color:{t["text"]};}}'
            f'QLabel#keyPill{{font-size:10px;font-weight:600;color:{t["key_fg"]};background:{t["key_bg"]};border-radius:6px;padding:2px 7px;}}'
            f'QPushButton{{padding:6px 11px;border:1px solid {t["btn_border"]};border-radius:9px;background:{t["btn_bg"]};color:{t["btn_fg"]};font-family:"Microsoft YaHei UI";font-size:12px;font-weight:600;}}'
            f'QPushButton:hover{{background:{t["btn_hover"]};border-color:#60a5fa;}}'
            f'QPushButton:disabled{{opacity:0.45;}}'
            f'QPushButton#longAuto:checked{{background:{t["auto_bg"]};border-color:{t["auto_border"]};color:{t["auto_fg"]};}}'
            f'QPushButton#longCancel{{background:transparent;border-color:transparent;padding:0;border-radius:8px;}}'
            f'QPushButton#longCancel:hover{{background:{t["cancel_hover"]};border-color:#fca5a5;}}'
            f'QPushButton#longFinish{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #3b82f6,stop:1 #2563eb);border:1px solid #2563eb;color:#ffffff;padding:6px 13px;}}'
            f'QPushButton#longFinish:hover{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #60a5fa,stop:1 #3b82f6);border-color:#60a5fa;}}'
            f'QFrame#diagBar{{background:{t["warn_bg"]};border:1px solid {t["warn_border"]};border-radius:9px;}}'
            f'QLabel#diagHint{{color:{t["warn_fg"]};font-size:11px;font-weight:500;}}'
            f'QPushButton#diagBtn{{padding:3px 9px;font-size:11px;border-radius:7px;}}'
        )
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(6)

        # Row 1: Pulsing indicator + clean size readout + action buttons
        top = QHBoxLayout()
        top.setSpacing(7)
        self.dot = _PulseDot('#3b82f6', card)
        top.addWidget(self.dot)
        self.count = QLabel('长截图 · 就绪')
        self.count.setObjectName('longCount')
        top.addWidget(self.count)
        top.addStretch(1)

        self.auto_scroll_button = QPushButton('自动滚动')
        self.auto_scroll_button.setObjectName('longAuto')
        self.auto_scroll_button.setCheckable(True)
        self.auto_scroll_button.setIcon(line_icon('scroll', t['icon_ink']))
        self.auto_scroll_button.setIconSize(QSize(14, 14))
        self.auto_scroll_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.auto_scroll_button.setToolTip('自动向下滚动并拼接；到达底部自动停止')
        self.auto_scroll_button.toggled.connect(self._on_auto_toggled)
        self.auto_scroll_button.toggled.connect(self.auto_scroll_toggled.emit)
        top.addWidget(self.auto_scroll_button)

        cancel = QPushButton()
        cancel.setObjectName('longCancel')
        cancel.setFixedSize(30, 30)
        cancel.setIcon(line_icon('close', '#ef4444'))
        cancel.setIconSize(QSize(16, 16))
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setToolTip('取消长截图 · Esc')
        cancel.setAccessibleName('取消')
        cancel.clicked.connect(self.cancel_requested.emit)
        top.addWidget(cancel)

        self.finish_button = QPushButton('完成')
        self.finish_button.setObjectName('longFinish')
        self.finish_button.setIcon(line_icon('check', '#ffffff'))
        self.finish_button.setIconSize(QSize(14, 14))
        self.finish_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.finish_button.setToolTip(f'完成采集并预览标注 ({hotkey} / Enter)')
        self.finish_button.clicked.connect(self.finish_requested.emit)
        top.addWidget(self.finish_button)
        layout.addLayout(top)

        # Row 2: Single clean status line + compact shortcut badge on right
        sub = QHBoxLayout()
        sub.setSpacing(8)
        self.status = QLabel('滚动页面自动拼接，或点击「自动滚动」')
        self.status.setWordWrap(False)
        sub.addWidget(self.status, 1)
        key_pill = QLabel(f'{hotkey} 完成')
        key_pill.setObjectName('keyPill')
        sub.addWidget(key_pill)
        layout.addLayout(sub)

        # Row 3: Diagnostic strip — hidden by default, only appears on seam failure!
        self.diagnostic_bar = QFrame(card)
        self.diagnostic_bar.setObjectName('diagBar')
        diag_row = QHBoxLayout(self.diagnostic_bar)
        diag_row.setContentsMargins(10, 5, 8, 5)
        diag_row.setSpacing(8)
        self.diagnostic_hint = QLabel('检测到接缝断接，回到上次位置继续，或保存诊断排查')
        self.diagnostic_hint.setObjectName('diagHint')
        diag_row.addWidget(self.diagnostic_hint, 1)
        self.diagnostic_button = QPushButton('保存诊断')
        self.diagnostic_button.setObjectName('diagBtn')
        self.diagnostic_button.setEnabled(False)
        self.diagnostic_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.diagnostic_button.setToolTip('保存断接前后的选区画面与日志到本机；不会上传')
        self.diagnostic_button.clicked.connect(self.diagnostic_requested.emit)
        diag_row.addWidget(self.diagnostic_button)
        self.diagnostic_bar.hide()
        layout.addWidget(self.diagnostic_bar)

        self.setFixedWidth(440 + _SHADOW * 2)
        self.adjustSize()

    def _on_auto_toggled(self, active):
        self.auto_scroll_button.setText('暂停滚动' if active else '自动滚动')
        self.dot.set_color('#10b981' if active else '#3b82f6')

    def reveal_diagnostics(self):
        self.diagnostic_button.setEnabled(True)
        if self.diagnostic_bar.isHidden():
            self.diagnostic_bar.show()
            self.adjustSize()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _paint_floating_card(p, self.rect(), self.dark, radius=14)
        p.end()

    def closeEvent(self, event):
        if not self.stopping:
            self.cancel_requested.emit()
        event.accept()


class LiveLongPreview(QWidget):
    """Sleek width-fit auto-following live preview card with soft edge fade & miniature scrollbar."""

    def __init__(self, dark=False):
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setWindowTitle('长截图实时预览 · SnapFlow')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.dark = bool(dark)
        self.parts = []
        self.total = 1
        self.source_width = 1
        self.viewport = (0, 1)
        self.max_display_height = 460
        self.setFixedSize(208, 460)

    def refresh(self, stitcher):
        self.parts = list(stitcher.parts)
        self.total = max(1, stitcher.height)
        self.source_width = max(1, stitcher.width)
        inner_w = max(40, self.width() - _SHADOW * 2 - 26)
        scale = min(1.0, inner_w / self.source_width)
        desired_h = math.ceil(self.total * scale) + _SHADOW * 2 + 54
        self.setFixedHeight(max(130, min(self.max_display_height, desired_h)))
        self.viewport = (stitcher.position - stitcher.top, stitcher.previous.height())
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        content = _paint_floating_card(p, self.rect(), self.dark, radius=14)

        # Compact header bar: title left, dimensions badge right
        title_font = QFont('Microsoft YaHei UI')
        title_font.setPixelSize(11)
        title_font.setBold(True)
        p.setFont(title_font)
        p.setPen(QColor('#eef5fc') if self.dark else QColor('#1e293b'))
        p.drawText(
            QRectF(content.left() + 12, content.top() + 8, content.width() - 24, 20),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            '实时预览',
        )

        dim_text = f'{self.source_width}×{self.total}'
        dim_font = QFont('Microsoft YaHei UI')
        dim_font.setPixelSize(10)
        dim_font.setBold(True)
        p.setFont(dim_font)
        dw = p.fontMetrics().horizontalAdvance(dim_text) + 12
        dim_pill = QRectF(content.right() - dw - 10, content.top() + 9, dw, 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(59, 130, 246, 38) if self.dark else QColor('#eff6ff'))
        p.drawRoundedRect(dim_pill, 6, 6)
        p.setPen(QColor('#93c5fd') if self.dark else QColor('#2563eb'))
        p.drawText(dim_pill, Qt.AlignmentFlag.AlignCenter, dim_text)

        # Image viewport (fit-to-width & auto-follow latest scrolled viewport — never a tiny noodle!)
        inner = QRectF(
            content.left() + 10,
            content.top() + 34,
            max(24.0, content.width() - 26),
            max(24.0, content.height() - 44),
        )
        frame_bg = QColor('#0f1624') if self.dark else QColor('#edf2f9')
        clip = QPainterPath()
        clip.addRoundedRect(inner, 8, 8)
        p.save()
        p.setClipPath(clip)
        p.fillRect(inner, frame_bg)

        scale = min(1.0, inner.width() / max(1, self.source_width))
        draw_w = self.source_width * scale
        draw_x = inner.left() + (inner.width() - draw_w) / 2.0
        scaled_total = self.total * scale

        vp_top = self.viewport[0] * scale
        vp_h = self.viewport[1] * scale
        max_scroll = max(0.0, scaled_total - inner.height())
        if max_scroll > 0:
            # Frame the active viewport cleanly near bottom (downward scroll) or top (upward scroll)
            if vp_top + vp_h > inner.height() * 0.78:
                scroll_y = min(max_scroll, max(0.0, vp_top + vp_h - inner.height() + 14.0))
            else:
                scroll_y = max(0.0, min(max_scroll, vp_top - 14.0))
        else:
            scroll_y = 0.0

        y_doc = 0.0
        for part in self.parts:
            ph = part.height() * scale
            if y_doc + ph >= scroll_y - 2 and y_doc <= scroll_y + inner.height() + 2:
                target = QRectF(draw_x, inner.top() + y_doc - scroll_y, part.width() * scale, ph)
                p.drawImage(target, part)
            y_doc += ph

        # Crisp blue indicator around current live viewport
        vp_rect = QRectF(draw_x + 0.75, inner.top() + vp_top - scroll_y + 0.75, draw_w - 1.5, max(4.0, vp_h - 1.5))
        p.setPen(QPen(QColor('#3b82f6'), 1.8))
        p.setBrush(QColor(59, 130, 246, 22))
        p.drawRoundedRect(vp_rect, 4, 4)

        # Subtle edge fades when content extends above or below the preview window
        fade_col = QColor(20, 28, 43, 220) if self.dark else QColor(255, 255, 255, 220)
        fade_zero = QColor(fade_col.red(), fade_col.green(), fade_col.blue(), 0)
        if scroll_y > 2.0:
            top_fade = QLinearGradient(inner.topLeft(), QPointF(inner.left(), inner.top() + 26))
            top_fade.setColorAt(0.0, fade_col)
            top_fade.setColorAt(1.0, fade_zero)
            p.fillRect(QRectF(inner.left(), inner.top(), inner.width(), 26), top_fade)
        if scroll_y < max_scroll - 2.0:
            bot_fade = QLinearGradient(QPointF(inner.left(), inner.bottom() - 26), inner.bottomLeft())
            bot_fade.setColorAt(0.0, fade_zero)
            bot_fade.setColorAt(1.0, fade_col)
            p.fillRect(QRectF(inner.left(), inner.bottom() - 26, inner.width(), 26), bot_fade)
        p.restore()

        # Inner frame hairline border
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(148, 163, 184, 48) if self.dark else QColor(148, 163, 184, 70), 1.0))
        p.drawRoundedRect(inner.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

        # Sleek 3px miniature scroll track & thumb along right edge
        track = QRectF(content.right() - 10, inner.top() + 2, 3.5, max(12.0, inner.height() - 4))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(148, 163, 184, 45) if self.dark else QColor(148, 163, 184, 65))
        p.drawRoundedRect(track, 1.8, 1.8)
        if scaled_total > 0:
            frac_h = min(1.0, inner.height() / max(inner.height(), scaled_total))
            thumb_h = max(18.0, track.height() * frac_h)
            pos_ratio = scroll_y / max(1.0, max_scroll) if max_scroll > 0 else 0.0
            thumb_y = track.top() + (track.height() - thumb_h) * pos_ratio
            p.setBrush(QColor('#60a5fa') if self.dark else QColor('#3b82f6'))
            p.drawRoundedRect(QRectF(track.left(), thumb_y, track.width(), thumb_h), 1.8, 1.8)
        p.end()


class LongCaptureSession(QObject):
    completed = Signal(object, str, int)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, screen, rect, hotkey, parent=None, grabber=None, initial_frame=None, wheel_scroller=None):
        super().__init__(parent)
        self.screen = screen
        self.rect = QRectF(rect)
        self.geometry = screen.geometry()
        self.grabber = grabber
        self.wheel_scroller = wheel_scroller
        self.stitcher = None
        self.pending = None
        self.done = False
        self.trace = deque(maxlen=90)
        self.diagnostic_failure = None
        self.diagnostic_frames = deque(maxlen=6)
        self.started_at = time.monotonic()
        self.diagnostic_path = None
        default_home = Path(__file__).resolve().parents[2] / 'DocumentAssistant-local'
        self.diagnostic_home = Path(getattr(parent, 'home', None) or os.environ.get('DOCUMENTASSISTANT_HOME', default_home))
        self.initial_frame = initial_frame.copy() if initial_frame is not None else None
        dark = getattr(parent, 'theme_name', 'light') == 'dark'
        self.controls = LongControls(hotkey, dark=dark)
        self.outline = None
        self.keys = None
        self.preview = LiveLongPreview(dark=dark)
        self.preview_updated = 0.0
        self.controls.finish_requested.connect(self.finish)
        self.controls.cancel_requested.connect(self.cancel)
        self.controls.diagnostic_requested.connect(self.save_diagnostics)
        self.controls.auto_scroll_toggled.connect(self.set_auto_scroll)
        global_rect = QRectF(rect)
        global_rect.translate(self.geometry.topLeft())
        self.position = controls_position(screen.availableGeometry(), global_rect, self.controls.size())
        self.global_rect = global_rect
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.poll)
        self.auto_scrolling = False
        self._auto_scroll_suspended = False
        self._auto_unchanged_ticks = 0
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(140)
        self._auto_timer.timeout.connect(self._auto_scroll_step)

    def _cursor_on_controls(self, pos) -> bool:
        return self.controls.isVisible() and self.controls.geometry().adjusted(-18, -18, 18, 18).contains(pos)

    def _move_cursor_to_region_center(self):
        c = self.global_rect.center()
        # Use Qt logical coordinates (matching global_rect and QCursor.pos()) so
        # High-DPI scaling (e.g. 150%) never maps the cursor outside the capture box.
        if isinstance(self.screen, QScreen):
            QCursor.setPos(self.screen, round(c.x()), round(c.y()))
        else:
            QCursor.setPos(round(c.x()), round(c.y()))

    def set_auto_scroll(self, enabled: bool):
        if self.done:
            enabled = False
        self.auto_scrolling = bool(enabled)
        self._auto_scroll_suspended = False
        self._auto_unchanged_ticks = 0
        blocked = self.controls.auto_scroll_button.blockSignals(True)
        self.controls.auto_scroll_button.setChecked(self.auto_scrolling)
        self.controls._on_auto_toggled(self.auto_scrolling)
        self.controls.auto_scroll_button.blockSignals(blocked)
        if self.auto_scrolling:
            if self.wheel_scroller is None and sys.platform == 'win32':
                try:
                    pos = QCursor.pos()
                    if not self.global_rect.contains(pos.x(), pos.y()):
                        self._move_cursor_to_region_center()
                except Exception:
                    pass
            self._auto_timer.start()
            self.controls.status.setText('正在自动向下滚动… 点击「完成」或移出选区暂停')
        else:
            self._auto_timer.stop()

    def _auto_scroll_step(self):
        if self.done or not self.auto_scrolling:
            self._auto_timer.stop()
            return
        if self.wheel_scroller is not None:
            self._auto_scroll_suspended = False
            self.wheel_scroller()
            return
        pos = QCursor.pos()
        # Suspend wheel ticks while hovering the floating controls bar so the user
        # can click 完成 without triggering a false "reached bottom" or "left region" stop.
        if self._cursor_on_controls(pos):
            self._auto_scroll_suspended = True
            self._auto_unchanged_ticks = 0
            return
        self._auto_scroll_suspended = False
        if not self.global_rect.adjusted(-24, -24, 24, 24).contains(pos.x(), pos.y()):
            self.set_auto_scroll(False)
            self.controls.status.setText('已暂停自动滚动（检测到鼠标移出）')
            return
        if sys.platform == 'win32':
            ctypes.windll.user32.mouse_event(0x0800, 0, 0, ctypes.c_uint32(-240).value, 0)

    def frame(self):
        if self.screen.geometry() != self.geometry:
            raise OSError('屏幕尺寸或缩放发生变化，已停止继续拼接')
        if self.grabber:
            return crop_selection(self.grabber(), self.rect, self.geometry.size())
        return capture_region(self.screen, self.rect, self.geometry)

    def start(self):
        if self.done or self.stitcher:
            return
        try:
            self.stitcher = VerticalStitcher(self.initial_frame if self.initial_frame is not None else self.frame())
            self.initial_frame = None
            self.keys = CaptureKeys(self.finish, self.cancel)
            self.outline = RegionOutline(self.global_rect)
            self.outline.show()
            area = self.screen.availableGeometry()
            region = self.global_rect
            for side in ('right', 'left'):
                room = (area.right() - region.right() - 16) if side == 'right' else (region.left() - area.left() - 16)
                if room < 110:
                    continue
                w = min(214, int(room))
                h = min(460, area.height() - 32)
                self.preview.setFixedSize(w, h)
                self.preview.max_display_height = h
                x = int(region.right() + 8) if side == 'right' else int(region.left() - w - 8)
                y = max(area.top() + 8, min(int(region.top()), area.bottom() - h - 8))
                candidate = QRectF(x, y, w, h)
                if self.position is not None and candidate.intersects(
                    QRectF(self.position.x(), self.position.y(), self.controls.width(), self.controls.height())
                ):
                    continue
                self.preview.move(x, y)
                self.preview.refresh(self.stitcher)
                self.preview.show()
                break
            if not self.preview.isVisible():
                for height in (320, 190, 130):
                    self.preview.setFixedSize(min(214, area.width() - 24), height)
                    self.preview.max_display_height = height
                    point = controls_position(area, region, self.preview.size())
                    if point is None:
                        continue
                    candidate = QRectF(point.x(), point.y(), self.preview.width(), height)
                    if self.position is not None and candidate.intersects(
                        QRectF(self.position.x(), self.position.y(), self.controls.width(), self.controls.height())
                    ):
                        continue
                    self.preview.move(point)
                    self.preview.refresh(self.stitcher)
                    self.preview.show()
                    break
            if self.position is not None:
                self.controls.move(self.position)
                self.controls.show()
            self.update_count()
            self.timer.start()
            # Catch any wheel movement during overlay handoff before waiting another tick.
            self.poll()
        except Exception as exc:
            self.done = True
            self.teardown()
            self.failed.emit(str(exc))

    def update_count(self):
        if self.stitcher:
            count = len(self.stitcher.parts)
            self.controls.count.setText(f'{self.stitcher.width} × {self.stitcher.height} px · {count} 段')

    def poll(self):
        if self.done:
            return
        try:
            image = self.frame()
            self.pending = image
            reference = self.stitcher.previous
            started = time.monotonic()
            result = self.stitcher.append(image)
            self.record_result(reference, image, result, started)
            messages = {
                'appended': '已拼接下方新内容，可继续滚动',
                'prepended': '已拼接上方新内容，可继续滚动',
                'covered': '正在浏览已采集内容，越过边缘继续拼接',
                'unchanged': '滚动页面自动拼接，或点击「自动滚动」',
                'no_overlap': '画面变化过快未能匹配接缝，请稍回滚重试',
                'size_changed': '画面大小改变，已保留当前长图',
            }
            if result.status == 'limit':
                self.set_auto_scroll(False)
                self.finish('已达到长图大小上限，保留已采集内容')
                return
            if result.status == 'size_changed':
                self.set_auto_scroll(False)
                self.finish(messages[result.status])
                return
            status_text = messages[result.status]
            if result.status in ('appended', 'prepended'):
                self.controls.dot.set_color('#10b981')
            elif result.status == 'no_overlap':
                self.controls.dot.set_color('#f59e0b')
            elif not self.auto_scrolling:
                self.controls.dot.set_color('#3b82f6')

            if self.auto_scrolling:
                suspended = self._auto_scroll_suspended or (
                    self.wheel_scroller is None and self._cursor_on_controls(QCursor.pos())
                )
                if suspended:
                    self._auto_unchanged_ticks = 0
                    status_text = '自动滚动暂候（移回选区继续，或点击「完成」）'
                elif result.status in ('appended', 'prepended'):
                    self._auto_unchanged_ticks = 0
                elif result.status == 'unchanged':
                    self._auto_unchanged_ticks += 1
                    if self._auto_unchanged_ticks >= 60:
                        self.set_auto_scroll(False)
                        status_text = '已到达页面底部，可点击「完成」'
                elif result.status == 'no_overlap':
                    self.set_auto_scroll(False)
            self.controls.status.setText(status_text)
            self.update_count()
            now = time.monotonic()
            if now - self.preview_updated >= 0.12:
                self.preview.refresh(self.stitcher)
                self.preview_updated = now
        except Exception as exc:
            self.finish(str(exc))

    def record_result(self, reference, image, result, started):
        entry = {
            'elapsed_ms': round((time.monotonic() - self.started_at) * 1000, 1),
            'match_ms': round((time.monotonic() - started) * 1000, 2),
            'status': result.status,
            'added': result.added,
            'position': self.stitcher.position,
            'height': self.stitcher.height,
            'top': self.stitcher.top,
            'bottom': self.stitcher.bottom,
            'parts': len(self.stitcher.parts),
        }
        self.trace.append(entry)
        capacity = min(6, (12 * 1024 * 1024) // max(1, image.sizeInBytes()))
        changed = not self.diagnostic_frames or image != self.diagnostic_frames[-1]['image']
        if changed and capacity:
            self.diagnostic_frames.append({'image': QImage(image), 'event': dict(entry)})
            while len(self.diagnostic_frames) > capacity:
                self.diagnostic_frames.popleft()
            if self.diagnostic_failure is not None and len(self.diagnostic_failure['context']) < capacity:
                self.diagnostic_failure['context'].append({'image': QImage(image), 'event': dict(entry)})
        if result.status == 'no_overlap':
            if self.diagnostic_failure is None:
                self.diagnostic_failure = {
                    'reference': QImage(reference),
                    'first': QImage(image),
                    'first_event': dict(entry),
                    'context': list(self.diagnostic_frames)[-min(capacity, max(2, (capacity + 1) // 2)):] if capacity else [],
                }
            self.diagnostic_failure['latest'] = QImage(image)
            self.diagnostic_failure['latest_reference'] = QImage(reference)
            self.diagnostic_failure['latest_event'] = dict(entry)
            self.controls.reveal_diagnostics()

    def save_diagnostics(self):
        failure = self.diagnostic_failure
        if not failure or self.done:
            return
        try:
            target = self.diagnostic_home / 'capture-diagnostics' / (datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:8])
            target.mkdir(parents=True, exist_ok=False)
            images = {
                'reference.png': failure['reference'],
                'first-failed.png': failure['first'],
                'latest-reference.png': failure['latest_reference'],
                'latest-failed.png': failure['latest'],
                'captured.png': self.stitcher.image(),
            }
            context = []
            for index, sample in enumerate(failure['context']):
                filename = f'context-{index:02}.png'
                images[filename] = sample['image']
                context.append({'file': filename, **sample['event']})
            for name, image in images.items():
                if not image.save(str(target / name), 'PNG'):
                    raise OSError('无法保存诊断画面：' + name)
            from . import long_stitch
            source = Path(long_stitch.__file__)
            report = {
                'format_version': 1,
                'scope': '用户主动保存的长截图选区；不上传',
                'source': str(source),
                'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                'loaded_code_sha256': hashlib.sha256(
                    marshal.dumps(long_stitch.VerticalStitcher.append.__code__)
                    + marshal.dumps(long_stitch.vertical_shift.__code__)
                    + marshal.dumps(long_stitch._verify_shift.__code__)
                ).hexdigest(),
                'python': sys.version,
                'device_pixel_ratio': self.screen.devicePixelRatio() if hasattr(self.screen, 'devicePixelRatio') else None,
                'region': [self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height()],
                'image_size': [failure['first'].width(), failure['first'].height()],
                'first_failure': failure['first_event'],
                'latest_failure': failure['latest_event'],
                'context': context,
                'current_capture': {
                    'file': 'captured.png',
                    'position': self.stitcher.position,
                    'top': self.stitcher.top,
                    'bottom': self.stitcher.bottom,
                    'height': self.stitcher.height,
                },
                'recent_results': list(self.trace),
            }
            (target / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            self.diagnostic_path = target
            self.controls.diagnostic_hint.setText('诊断已保存到本机')
            self.controls.diagnostic_hint.setToolTip(str(target))
            self.controls.status.setText('诊断已保存，可继续采集')
            self.controls.status.setToolTip(str(target))
        except Exception as exc:
            self.controls.diagnostic_hint.setText('保存失败，请重试')
            self.controls.diagnostic_hint.setToolTip(str(exc))

    def finish(self, warning=''):
        if self.done:
            return
        self.done = True
        self.timer.stop()
        try:
            if not self.stitcher:
                raise ValueError('尚未获取长截图画面')
            if not warning:
                try:
                    frame = self.frame()
                    reference = self.stitcher.previous
                    started = time.monotonic()
                    result = self.stitcher.append(frame)
                    self.record_result(reference, frame, result, started)
                    if result.status == 'no_overlap':
                        warning = '最后一屏未能可靠拼接，已保留此前采集的内容'
                    elif result.status == 'size_changed':
                        warning = '最后一屏画面大小变化，已保留此前采集的内容'
                    elif result.status == 'limit':
                        warning = '已达到长图大小上限，保留已采集内容'
                except Exception as exc:
                    warning = str(exc)
            image = self.stitcher.image()
            count = len(self.stitcher.parts)
            if count == 1:
                warning = '尚未拼接到新内容，当前只有一屏。请重新采集并框选正文；若已跳过整屏，请回到上次位置再继续。' + (
                    ' ' + warning if warning else ''
                )
            self.teardown()
            self.completed.emit(image, warning, count)
        except Exception as exc:
            self.teardown()
            self.failed.emit(str(exc))

    def cancel(self):
        if self.done:
            return
        self.done = True
        self.teardown()
        self.cancelled.emit()

    def teardown(self):
        self.timer.stop()
        self._auto_timer.stop()
        self.auto_scrolling = False
        self.preview.close()
        self.preview.deleteLater()
        if self.keys:
            self.keys.shutdown()
            self.keys = None
        if self.outline:
            self.outline.close()
            self.outline.deleteLater()
            self.outline = None
        self.controls.stopping = True
        self.controls.close()
        self.controls.deleteLater()
