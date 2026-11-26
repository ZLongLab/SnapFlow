"""Startup and screenshot settings dialog synced with active SnapFlow theme."""
import sys
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QFrame
from .startup_registration import StartupRegistration
from .windows_identity import apply_titlebar_theme


def _palette(dark: bool) -> dict:
    if dark:
        return {
            'bg': '#131926',
            'card': '#1d2638',
            'border': '#2e3b52',
            'text': '#eef5fc',
            'muted': '#94a7c0',
            'accent': '#3b82f6',
            'track': '#334155',
            'focus': '#93c5fd',
            'btn_bg': '#232e44',
            'btn_hover': '#2b3954',
            'error': '#fca5a5',
        }
    return {
        'bg': '#f4f7fb',
        'card': '#ffffff',
        'border': '#dfe7f2',
        'text': '#0f172a',
        'muted': '#64748b',
        'accent': '#2563eb',
        'track': '#cbd5e1',
        'focus': '#60a5fa',
        'btn_bg': '#ffffff',
        'btn_hover': '#eff6ff',
        'error': '#dc2626',
    }


class ToggleSwitch(QCheckBox):
    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self.setFixedSize(44, 28)
        self.setAccessibleName('开机自启动')
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        pal = _palette(self._dark)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(pal['accent'] if self.isChecked() else pal['track']))
        p.drawRoundedRect(QRectF(1, 3, 42, 22), 11, 11)
        p.setBrush(QColor('#ffffff'))
        p.drawEllipse(QRectF(24 if self.isChecked() else 4, 6, 16, 16))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(pal['focus']), 1.2))
            p.drawRoundedRect(QRectF(0, 1, 43, 26), 12, 12)
        p.end()


class SettingsDialog(QDialog):
    def __init__(self, window, service=None):
        super().__init__(window)
        self.window = window
        self.service = service or StartupRegistration(window.home)
        dark = getattr(window, 'theme_name', 'light') == 'dark'
        self._pal = _palette(dark)
        pal = self._pal

        self.setWindowTitle('设置 · SnapFlow')
        self.resize(480, 290)
        self.setStyleSheet(
            f"""
            QDialog {{ background:{pal['bg']}; color:{pal['text']}; font-family:'Microsoft YaHei UI'; font-size:13px; }}
            QLabel {{ color:{pal['text']}; background:transparent; }}
            QPushButton {{ background:{pal['btn_bg']}; color:{pal['text']}; border:1px solid {pal['border']}; border-radius:10px; padding:8px 16px; font-weight:500; }}
            QPushButton:hover {{ background:{pal['btn_hover']}; border-color:{pal['focus']}; }}
            """
        )
        apply_titlebar_theme(self, dark=dark)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(16)
        title = QLabel('启动与快捷操作')
        title.setStyleSheet(f"font-size:20px;font-weight:700;color:{pal['text']}")
        layout.addWidget(title)
        card = QFrame()
        card.setStyleSheet(f"QFrame{{background:{pal['card']};border:1px solid {pal['border']};border-radius:14px;}} QLabel{{border:0;}}")
        row = QHBoxLayout(card)
        row.setContentsMargins(16, 14, 16, 14)
        info = QVBoxLayout()
        name = QLabel('开机自启动')
        name.setStyleSheet(f"font-weight:700;color:{pal['text']};")
        info.addWidget(name)
        description = QLabel('登录 Windows 后在托盘运行\n无需打开主窗口，即可使用截图与录屏快捷键')
        description.setStyleSheet(f"color:{pal['muted']};font-size:12px;")
        info.addWidget(description)
        row.addLayout(info, 1)
        self.startup_switch = ToggleSwitch(dark=dark)
        row.addWidget(self.startup_switch)
        layout.addWidget(card)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        try:
            self.startup_switch.setChecked(self.service.enabled())
            self.update_status()
        except OSError as exc:
            self.status.setText('启动项读取失败：' + str(exc))
            self.startup_switch.setEnabled(False)
        if sys.platform != 'win32':
            self.startup_switch.setEnabled(False)
            self.status.setText('开机自启动目前支持 Windows')
        self.startup_switch.toggled.connect(self.toggle_startup)
        actions = QHBoxLayout()
        capture = QPushButton('截图设置')
        capture.clicked.connect(self.open_capture)
        actions.addWidget(capture)
        actions.addStretch()
        close = QPushButton('完成')
        close.clicked.connect(self.accept)
        actions.addWidget(close)
        layout.addLayout(actions)

    def update_status(self):
        self.status.setText('已开启 · 下次登录后自动驻留托盘' if self.startup_switch.isChecked() else '已关闭 · 可随时开启')
        self.status.setStyleSheet(f"color:{self._pal['muted']};font-size:12px;")

    def toggle_startup(self, enabled):
        try:
            self.service.set_enabled(enabled)
        except (OSError, ValueError) as exc:
            blocked = self.startup_switch.blockSignals(True)
            try:
                self.startup_switch.setChecked(self.service.enabled())
            except OSError:
                self.startup_switch.setChecked(not enabled)
            self.startup_switch.blockSignals(blocked)
            self.status.setStyleSheet(f"color:{self._pal['error']};font-size:12px;")
            self.status.setText('设置未成功：' + str(exc))
            return
        self.update_status()

    def open_capture(self):
        self.accept()
        self.window.screenshot_settings()
