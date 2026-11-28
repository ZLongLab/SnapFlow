"""Non-intrusive floating HUD pill and rolling anti-loss clipboard capture history."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget


class ToastHud(QWidget):
    """Click-through, non-activating frosted capsule notification that never steals focus."""

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._title = ''
        self._subtitle = ''
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

    def show_message(self, title: str, subtitle: str = '', duration_ms: int = 1200, screen=None):
        self._title = str(title or '').strip()
        self._subtitle = str(subtitle or '').strip()
        if not self._title:
            return
        font_title = QFont('Microsoft YaHei UI')
        font_title.setPixelSize(13)
        font_title.setBold(True)
        from PySide6.QtGui import QFontMetrics
        fm_title = QFontMetrics(font_title)
        text = self._title if not self._subtitle else f'{self._title} · {self._subtitle}'
        if len(text) > 56:
            text = text[:55] + '…'
        self._display_text = text
        width = max(140, min(520, fm_title.horizontalAdvance(text) + 42))
        height = 38
        self.setFixedSize(width, height)

        target_screen = screen
        if target_screen is None:
            pos = QCursor.pos()
            target_screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
        if target_screen is not None:
            area = target_screen.availableGeometry()
            x = area.x() + (area.width() - width) // 2
            y = area.bottom() - height - 36
            self.move(x, y)

        self._timer.start(max(400, int(duration_ms)))
        self.show()
        self.raise_()
        self.update()

    def dismiss(self):
        self._timer.stop()
        if self.isVisible():
            self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)
        p.fillPath(path, QColor(15, 24, 38, 232))
        p.setPen(QPen(QColor(125, 211, 252, 95), 1.0))
        p.drawPath(path)

        # Crisp status indicator dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#38bdf8'))
        p.drawEllipse(QPointF(18, rect.center().y()), 4.0, 4.0)

        font = QFont('Microsoft YaHei UI')
        font.setPixelSize(12)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor('#eef6ff'))
        p.drawText(
            rect.adjusted(28, 0, -14, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            getattr(self, '_display_text', self._title),
        )
        p.end()


class CaptureHistory:
    """Rolling cache of copy-only captures stored inside app home, never touching save dir."""

    def __init__(self, home: Path, limit: int = 20):
        self.directory = (Path(home).resolve() / 'history')
        self.limit = max(1, int(limit))

    def record(self, image: QImage, now: datetime | None = None) -> Path | None:
        if image is None or image.isNull():
            return None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            data = QByteArray()
            buf = QBuffer(data)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            if not image.save(buf, 'PNG'):
                return None
            buf.close()
            payload = bytes(data)
            stamp = (now or datetime.now()).strftime('%Y%m%d_%H%M%S_%f')[:19]
            target = self.directory / f'剪贴_{stamp}.png'
            idx = 1
            while target.exists() and idx < 1000:
                target = self.directory / f'剪贴_{stamp}_{idx}.png'
                idx += 1
            target.write_bytes(payload)
            self._prune()
            return target
        except OSError:
            return None

    def _prune(self):
        items = self.entries()
        for _, _, old_path in items[self.limit:]:
            try:
                old_path.unlink(missing_ok=True)
            except OSError:
                pass

    def entries(self):
        if not self.directory.is_dir():
            return []
        items = []
        try:
            for child in self.directory.iterdir():
                if child.is_file() and child.suffix.lower() == '.png':
                    st = child.stat()
                    items.append((st.st_mtime, st.st_size, child))
        except OSError:
            return []
        items.sort(key=lambda item: item[0], reverse=True)
        return items

    def delete(self, path: Path) -> bool:
        try:
            target = Path(path).resolve()
            if target.parent == self.directory.resolve() and target.is_file():
                target.unlink()
                return True
        except OSError:
            pass
        return False

    def clear(self) -> int:
        removed = 0
        for _, _, path in self.entries():
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
        return removed
