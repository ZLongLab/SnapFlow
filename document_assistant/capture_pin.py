"""Always-on-top floating desktop Pin windows with in-place 1:1 DPI placement, zoom, opacity, and collapse."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import QApplication, QMenu, QWidget

PIN_MENU_QSS = """
QMenu {
    background:#141a26; color:#e6eef8; border:1px solid rgba(155,200,235,50);
    border-radius:10px; padding:6px; font-family:'Microsoft YaHei UI'; font-size:12px;
}
QMenu::item { padding:7px 16px; border-radius:6px; }
QMenu::item:selected { background:#2563eb; color:#ffffff; }
QMenu::separator { height:1px; background:rgba(155,200,235,30); margin:4px 8px; }
"""

_MARGIN = 10
_COMPACT_SIZE = 76


class PinnedImageWindow(QWidget):
    """Frameless always-on-top pinned screenshot window."""

    def __init__(self, image: QImage, controller=None, screen=None, target_rect=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setWindowTitle('桌面贴图 · SnapFlow')
        self.image = image.copy()
        self.controller = controller
        self.screen_ref = screen
        self.zoom = 1.0
        self.opacity_level = 1.0
        self.hud_text = ''
        self._drag_offset = None
        self._hovered = False
        self.compact = False
        self._expanded_pos = None

        self._hud_timer = QTimer(self)
        self._hud_timer.setSingleShot(True)
        self._hud_timer.timeout.connect(self._clear_hud)

        target_screen = screen or QApplication.primaryScreen()
        self._dpr = (
            max(1.0, float(target_screen.devicePixelRatio()))
            if target_screen and hasattr(target_screen, 'devicePixelRatio')
            else 1.0
        )
        area = target_screen.availableGeometry() if target_screen else None
        base_w, base_h = self._base_logical_size()

        if target_rect is not None:
            rect = QRectF(target_rect)
            # Match the selected region size 1:1 on screen without inflating on high-DPI displays.
            if rect.width() >= 2 and rect.height() >= 2:
                self._base_override = (max(48, round(rect.width())), max(48, round(rect.height())))
            else:
                self._base_override = None
            w = max(60, round(self._base_logical_size()[0] * self.zoom)) + _MARGIN * 2
            h = max(60, round(self._base_logical_size()[1] * self.zoom)) + _MARGIN * 2
            x = round(rect.left()) - _MARGIN
            y = round(rect.top()) - _MARGIN
            if area:
                x = max(area.left() - _MARGIN, min(area.right() - w + _MARGIN + 1, x))
                y = max(area.top() - _MARGIN, min(area.bottom() - h + _MARGIN + 1, y))
            self.setGeometry(x, y, w, h)
        else:
            self._base_override = None
            if area:
                fit = min(1.0, (area.width() - 80) / max(1, base_w), (area.height() - 80) / max(1, base_h))
                if fit < 1.0:
                    self.zoom = max(0.25, fit)
            self._apply_geometry(center_in=area)

        for seq, fn in (('Escape', self.close), ('Ctrl+C', self.copy), ('Ctrl+S', self.save)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(fn)

    def _base_logical_size(self):
        if getattr(self, '_base_override', None):
            return self._base_override
        dpr = getattr(self, '_dpr', 1.0)
        return max(48, round(self.image.width() / dpr)), max(48, round(self.image.height() / dpr))

    def _apply_geometry(self, center_in=None):
        if self.compact:
            side = _COMPACT_SIZE + _MARGIN * 2
            pos = self.geometry().topLeft()
            self.setGeometry(pos.x(), pos.y(), side, side)
            self.update()
            return
        bw, bh = self._base_logical_size()
        w = max(60, round(bw * self.zoom)) + _MARGIN * 2
        h = max(60, round(bh * self.zoom)) + _MARGIN * 2
        if center_in is not None:
            x = center_in.x() + (center_in.width() - w) // 2
            y = center_in.y() + (center_in.height() - h) // 2
            self.setGeometry(x, y, w, h)
        else:
            old = self.geometry().center()
            self.setGeometry(old.x() - w // 2, old.y() - h // 2, w, h)
        self.update()

    def _show_hud(self, text: str):
        self.hud_text = text
        self._hud_timer.start(900)
        self.update()

    def _clear_hud(self):
        self.hud_text = ''
        self.update()

    def toggle_compact(self):
        """Double-click folds pin into a tiny corner badge instead of accidentally destroying it."""
        if not self.compact:
            self._expanded_pos = self.geometry().topLeft()
            self.compact = True
            self._apply_geometry()
            self._show_hud('已收起')
        else:
            self.compact = False
            bw, bh = self._base_logical_size()
            w = max(60, round(bw * self.zoom)) + _MARGIN * 2
            h = max(60, round(bh * self.zoom)) + _MARGIN * 2
            pos = self.geometry().topLeft()
            self.setGeometry(pos.x(), pos.y(), w, h)
            self._show_hud(f'{round(self.zoom * 100)}%')
            self.update()

    def set_zoom(self, value: float):
        if self.compact:
            self.compact = False
        self.zoom = max(0.25, min(3.0, float(value)))
        self._apply_geometry()
        self._show_hud(f'{round(self.zoom * 100)}%')

    def set_opacity_level(self, value: float):
        self.opacity_level = max(0.25, min(1.0, float(value)))
        self.setWindowOpacity(self.opacity_level)
        self._show_hud(f'不透明度 {round(self.opacity_level * 100)}%')

    def reset_view(self):
        self.compact = False
        self.zoom = 1.0
        self.opacity_level = 1.0
        self.setWindowOpacity(1.0)
        self._apply_geometry()
        self._show_hud('100%')

    def copy(self):
        try:
            from .screen_capture import copy_image

            copy_image(self.image)
            self._show_hud('已复制')
            if self.controller and hasattr(self.controller, 'notify'):
                self.controller.notify('贴图已复制', '已写入剪贴板')
        except Exception as exc:
            self._show_hud('复制失败: ' + str(exc))

    def save(self):
        try:
            from .screen_capture import save_png

            directory = (
                Path(self.controller.settings['directory'])
                if self.controller and hasattr(self.controller, 'settings')
                else Path.home() / 'Desktop'
            )
            path = save_png(self.image, directory)
            if self.controller:
                self.controller.last_saved = path
                if hasattr(self.controller, '_notify_window_refresh'):
                    self.controller._notify_window_refresh()
                if hasattr(self.controller, 'notify'):
                    self.controller.notify('贴图已保存', str(path))
            self._show_hud('已保存 PNG')
        except Exception as exc:
            self._show_hud('保存失败: ' + str(exc))

    def open_beautify(self):
        if self.controller and hasattr(self.controller, 'beautify_image'):
            self.controller.beautify_image(self.image, self.screen_ref)

    def open_edit(self):
        if self.controller and hasattr(self.controller, 'edit_image'):
            self.controller.edit_image(self.image, self.screen_ref)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        content = QRectF(_MARGIN, _MARGIN, self.width() - _MARGIN * 2, self.height() - _MARGIN * 2)
        p.setPen(Qt.PenStyle.NoPen)
        for spread, alpha in ((8, 14), (6, 20), (4, 28), (2, 36)):
            p.setBrush(QColor(4, 8, 16, alpha))
            p.drawRoundedRect(content.adjusted(-spread, -spread + 2, spread, spread + 4), 10 + spread * 0.5, 10 + spread * 0.5)

        radius = 12 if self.compact else 8
        clip = QPainterPath()
        clip.addRoundedRect(content, radius, radius)
        p.save()
        p.setClipPath(clip)
        if self.compact:
            # Center-crop thumbnail inside compact square badge
            scaled = self.image.scaled(
                int(content.width()),
                int(content.height()),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            sx = max(0, (scaled.width() - int(content.width())) // 2)
            sy = max(0, (scaled.height() - int(content.height())) // 2)
            p.drawImage(content, scaled, QRectF(sx, sy, content.width(), content.height()))
        else:
            p.drawImage(content, self.image)
        p.restore()

        # Subtle cool glow border so an in-place 1:1 pin stands out clearly from underlying windows
        p.setBrush(Qt.BrushStyle.NoBrush)
        border_color = QColor(96, 165, 250, 210) if self._hovered else QColor(147, 197, 253, 125)
        p.setPen(QPen(border_color, 1.6 if self._hovered else 1.2))
        p.drawRoundedRect(content.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        if self.hud_text:
            metrics = p.fontMetrics()
            tw = min(self.width() - 16, metrics.horizontalAdvance(self.hud_text) + 22)
            pill = QRectF((self.width() - tw) / 2, content.bottom() - 32, tw, 24)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(12, 18, 30, 220))
            p.drawRoundedRect(pill, 12, 12)
            p.setPen(QColor('#eef6ff'))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, self.hud_text)
        p.end()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.close()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            self.unsetCursor()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_compact()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if not delta:
            return
        steps = delta / 120.0
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_opacity_level(self.opacity_level + steps * 0.08)
        else:
            self.set_zoom(self.zoom * (1.1 ** steps))
        event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(PIN_MENU_QSS)
        menu.addAction('复制图片 (Ctrl+C)', self.copy)
        if self.controller:
            menu.addAction('美化套壳…', self.open_beautify)
            menu.addAction('二次标注…', self.open_edit)
        menu.addAction('保存 PNG (Ctrl+S)', self.save)
        menu.addAction('展开贴图 (双击)' if self.compact else '收起为缩略图 (双击)', self.toggle_compact)
        menu.addAction('还原原始尺寸', self.reset_view)
        menu.addSeparator()
        menu.addAction('关闭贴图 (Esc / 中键)', self.close)
        menu.exec(event.globalPos())
