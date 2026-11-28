"""Unified SnapFlow settings dialog with press-to-record hotkey input and startup/UX preferences."""
import sys
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)
from .capture_hotkey import parse_hotkey
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
            'input_bg': '#141c2c',
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
        'input_bg': '#f8fafd',
        'error': '#dc2626',
    }


class HotkeyRecorderEdit(QLineEdit):
    """Press-to-record hotkey input that captures Ctrl/Alt/Shift + key directly."""

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setPlaceholderText('点击后直接按下快捷键组合（如 Alt+S）')
        self.setToolTip('聚焦后直接按下组合键即可录入，支持 Ctrl/Alt (+ Shift) + 字母/数字/F1–F24')

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            event.accept()
            return
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab, Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            super().keyPressEvent(event)
            return
        mods = event.modifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append('Ctrl')
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append('Alt')
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append('Shift')
        if not parts:
            if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                self.clear()
                event.accept()
                return
            super().keyPressEvent(event)
            return
        key_name = None
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            key_name = chr(key)
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            key_name = chr(key)
        elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            key_name = f'F{key - Qt.Key.Key_F1 + 1}'
        if key_name:
            candidate = '+'.join(parts + [key_name])
            try:
                canonical, _, _ = parse_hotkey(candidate)
                self.setText(canonical)
            except ValueError:
                self.setText(candidate)
            event.accept()
            return
        event.accept()


class ToggleSwitch(QCheckBox):
    def __init__(self, parent=None, dark=False, accessible_name='开关'):
        super().__init__(parent)
        self._dark = dark
        self.setFixedSize(44, 28)
        self.setAccessibleName(accessible_name)
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
    def __init__(self, window, service=None, controller=None):
        super().__init__(window)
        self.window = window
        self.controller = controller or getattr(window, 'capture_controller', None)
        self.service = service or StartupRegistration(window.home)
        dark = getattr(window, 'theme_name', 'light') == 'dark'
        self._pal = _palette(dark)
        pal = self._pal

        self.setWindowTitle('设置与快捷键 · SnapFlow')
        self.resize(560, 580)
        self.setStyleSheet(
            f"""
            QDialog {{ background:{pal['bg']}; color:{pal['text']}; font-family:'Microsoft YaHei UI'; font-size:13px; }}
            QLabel {{ color:{pal['text']}; background:transparent; }}
            QLineEdit, QComboBox {{
                background:{pal['input_bg']}; color:{pal['text']};
                border:1px solid {pal['border']}; border-radius:9px; padding:7px 11px;
                selection-background-color:#2563eb;
            }}
            QLineEdit:focus, QComboBox:focus {{ border-color:{pal['focus']}; }}
            QComboBox QAbstractItemView {{
                background:{pal['card']}; color:{pal['text']};
                selection-background-color:{pal['accent']}; border:1px solid {pal['border']};
            }}
            QPushButton {{
                background:{pal['btn_bg']}; color:{pal['text']};
                border:1px solid {pal['border']}; border-radius:10px; padding:8px 16px; font-weight:500;
            }}
            QPushButton:hover {{ background:{pal['btn_hover']}; border-color:{pal['focus']}; }}
            QPushButton#primarySave {{
                background:{pal['accent']}; color:#ffffff; border-color:{pal['accent']}; font-weight:600;
            }}
            QPushButton#primarySave:hover {{ background:#3b82f6; border-color:#60a5fa; }}
            """
        )
        apply_titlebar_theme(self, dark=dark)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        title = QLabel('设置与快捷操作')
        title.setStyleSheet(f"font-size:19px;font-weight:700;color:{pal['text']}")
        layout.addWidget(title)

        # Card 1: Hotkey & Save Directory
        cfg = self.controller.settings if self.controller is not None else (
            window._configured_settings() if hasattr(window, '_configured_settings') else {'hotkey': 'Alt+S', 'directory': str(window.home)}
        )
        capture_card = self._make_card(pal)
        c_layout = QVBoxLayout(capture_card)
        c_layout.setContentsMargins(16, 14, 16, 14)
        c_layout.setSpacing(10)

        sec1 = QLabel('截图快捷键与保存位置')
        sec1.setStyleSheet(f"font-weight:700;color:{pal['text']};")
        c_layout.addWidget(sec1)

        hk_row = QHBoxLayout()
        hk_row.setSpacing(10)
        hk_lbl = QLabel('全局截图热键')
        hk_lbl.setFixedWidth(96)
        self.hotkey_edit = HotkeyRecorderEdit(cfg.get('hotkey', 'Alt+S'))
        hk_row.addWidget(hk_lbl)
        hk_row.addWidget(self.hotkey_edit, 1)
        c_layout.addLayout(hk_row)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        dir_lbl = QLabel('默认保存目录')
        dir_lbl.setFixedWidth(96)
        self.directory_edit = QLineEdit(cfg.get('directory', ''))
        choose_btn = QPushButton('选择目录')
        choose_btn.setAutoDefault(False)
        choose_btn.clicked.connect(self.choose_directory)
        dir_row.addWidget(dir_lbl)
        dir_row.addWidget(self.directory_edit, 1)
        dir_row.addWidget(choose_btn)
        c_layout.addLayout(dir_row)
        layout.addWidget(capture_card)

        # Card 2: Startup & Workflow Habits
        habit_card = self._make_card(pal)
        h_layout = QVBoxLayout(habit_card)
        h_layout.setContentsMargins(16, 14, 16, 14)
        h_layout.setSpacing(12)

        self.startup_switch = ToggleSwitch(dark=dark, accessible_name='开机自启动')
        h_layout.addLayout(
            self._switch_row(
                '开机自启动',
                '登录 Windows 后在托盘常驻，随时响应截图热键',
                self.startup_switch,
                pal,
            )
        )

        self.system_notify_switch = ToggleSwitch(dark=dark, accessible_name='系统通知横幅')
        self.system_notify_switch.setChecked(bool(cfg.get('system_notifications', False)))
        h_layout.addLayout(
            self._switch_row(
                '使用 Windows 系统通知气泡',
                '关闭时使用轻量无声胶囊提示，不会打断连拍或截进通知栏',
                self.system_notify_switch,
                pal,
            )
        )

        self.copy_history_switch = ToggleSwitch(dark=dark, accessible_name='暂存剪贴历史')
        self.copy_history_switch.setChecked(bool(cfg.get('save_copy_history', True)))
        copy_hist_row = self._switch_row(
            '复制时暂存本机剪贴历史',
            '开启后在运行目录 history 暂存最近 20 张仅复制截图；关闭后「仅复制」不写入磁盘',
            self.copy_history_switch,
            pal,
        )
        clear_hist_btn = QPushButton('清空')
        clear_hist_btn.setAutoDefault(False)
        clear_hist_btn.setToolTip('立即清空已暂存的剪贴历史图片')
        clear_hist_btn.clicked.connect(self.clear_copy_history)
        copy_hist_row.insertWidget(copy_hist_row.count() - 1, clear_hist_btn)
        h_layout.addLayout(copy_hist_row)

        self.skip_countdown_switch = ToggleSwitch(dark=dark, accessible_name='录屏免倒计时')
        self.skip_countdown_switch.setChecked(bool(cfg.get('skip_video_countdown', False)))
        h_layout.addLayout(
            self._switch_row(
                '录屏跳过 3 秒倒计时',
                '点击开始录制后立即开录（不开启时也可在倒计时点击「立即开始」）',
                self.skip_countdown_switch,
                pal,
            )
        )

        tray_row = QHBoxLayout()
        tray_row.setSpacing(10)
        tray_info = QVBoxLayout()
        tray_title = QLabel('托盘图标单击动作')
        tray_title.setStyleSheet(f"font-weight:600;color:{pal['text']};")
        tray_sub = QLabel('中键单击托盘图标始终可直接框选截图')
        tray_sub.setStyleSheet(f"color:{pal['muted']};font-size:11px;")
        tray_info.addWidget(tray_title)
        tray_info.addWidget(tray_sub)
        self.tray_action_combo = QComboBox()
        self.tray_action_combo.addItem('打开 SnapFlow 画廊', 'gallery')
        self.tray_action_combo.addItem('直接开始框选截图', 'capture')
        self.tray_action_combo.setCurrentIndex(1 if cfg.get('tray_click_action') == 'capture' else 0)
        tray_row.addLayout(tray_info, 1)
        tray_row.addWidget(self.tray_action_combo)
        h_layout.addLayout(tray_row)
        layout.addWidget(habit_card)

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
        actions.addStretch()
        cancel_btn = QPushButton('取消')
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        actions.addWidget(cancel_btn)
        save_btn = QPushButton('保存设置')
        save_btn.setObjectName('primarySave')
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save_settings)
        actions.addWidget(save_btn)
        layout.addLayout(actions)

    def _make_card(self, pal):
        card = QFrame()
        card.setStyleSheet(f"QFrame{{background:{pal['card']};border:1px solid {pal['border']};border-radius:14px;}} QLabel{{border:0;}}")
        return card

    def _switch_row(self, title_text, desc_text, switch, pal):
        row = QHBoxLayout()
        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(title_text)
        name.setStyleSheet(f"font-weight:600;color:{pal['text']};")
        desc = QLabel(desc_text)
        desc.setStyleSheet(f"color:{pal['muted']};font-size:11px;")
        desc.setWordWrap(True)
        info.addWidget(name)
        info.addWidget(desc)
        row.addLayout(info, 1)
        row.addWidget(switch)
        return row

    def choose_directory(self):
        path = QFileDialog.getExistingDirectory(self, '选择截图保存目录', self.directory_edit.text())
        if path:
            self.directory_edit.setText(path)

    def update_status(self):
        self.status.setText('已开启 · 下次登录后自动驻留托盘' if self.startup_switch.isChecked() else '已关闭 · 可随时开启开机自启动')
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

    def clear_copy_history(self):
        ctrl = self.controller or getattr(self.window, 'capture_controller', None)
        if ctrl is not None and hasattr(ctrl, 'clear_copy_history'):
            removed = ctrl.clear_copy_history()
        else:
            from .capture_hud import CaptureHistory
            removed = CaptureHistory(self.window.home).clear()
            if hasattr(self.window, 'refresh_recent'):
                self.window.refresh_recent()
        self.status.setStyleSheet(f"color:{self._pal['muted']};font-size:12px;")
        self.status.setText(f'已清空 {removed} 条本机剪贴历史记录' if removed else '当前没有可清空的剪贴历史记录')

    def save_settings(self):
        ctrl = self.controller or (self.window.ensure_capture() if hasattr(self.window, 'ensure_capture') else None)
        if ctrl is None:
            self.accept()
            return
        try:
            ctrl.configure(
                self.hotkey_edit.text(),
                self.directory_edit.text(),
                system_notifications=self.system_notify_switch.isChecked(),
                tray_click_action=self.tray_action_combo.currentData(),
                skip_video_countdown=self.skip_countdown_switch.isChecked(),
                save_copy_history=self.copy_history_switch.isChecked(),
            )
        except Exception as exc:
            self.status.setStyleSheet(f"color:{self._pal['error']};font-size:12px;")
            self.status.setText('保存失败：' + str(exc))
            return
        self.accept()
