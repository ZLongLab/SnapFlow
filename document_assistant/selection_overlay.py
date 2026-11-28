"""Select, annotate and copy a screenshot in one native screen overlay."""
import copy
import math
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal, QSize
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap, QFont, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QButtonGroup,
    QLabel,
    QSpinBox,
    QComboBox,
)
from .capture_pixels import crop_selection, pixel_scale, selection_pixels
from .capture_icons import line_icon
from .inline_capture import InlineAnnotationCanvas
from .capture_tools import COLOR_CHOICES, COLORS, normalize_tools
from .video_audio import normalize_audio_mode, audio_label

from .capture_material import (
    CaptureGlassPanel,
    PANEL_STYLE,
    SELECTION_COLOR,
    CORNER_COLOR,
    HANDLE_COLOR,
    ICON_COLOR,
    MUTED_ICON_COLOR,
    paint_panel_shadows,
)

_SIZE_PRESETS = {
    'width': (2, 4, 8),
    'size': (16, 24, 36),
    'brush': (10, 20, 34),
}


class SizeDotButton(QPushButton):
    """Compact circular size preset dot (S / M / L) for 1-click stroke sizing."""

    def __init__(self, radius, tooltip, parent=None):
        super().__init__('', parent)
        self._radius = radius
        self.setObjectName('sizePreset')
        self.setCheckable(True)
        self.setFixedSize(26, 26)
        self.setToolTip(tooltip)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#eef7ff' if self.isChecked() else '#b9cfdf'))
        p.drawEllipse(QPointF(self.width() / 2, self.height() / 2), self._radius, self._radius)
        p.end()


class SelectionOverlay(QWidget):
    selected = Signal(object)
    save_selected = Signal(object)
    save_as_selected = Signal(object)
    pin_selected = Signal(object)
    beautify_selected = Signal(object)
    color_picked = Signal(str)
    video_selected = Signal(object)
    long_selected = Signal(object)
    mode_changed = Signal(str)
    video_audio_changed = Signal(str)
    skip_countdown_requested = Signal()
    cancelled = Signal()
    preferences_changed = Signal(object)

    def __init__(self, screen, image, preferences=None, window_rects=None):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.screen_ref, self.image = screen, image
        self.window_rects = [QRectF(r) for r in (window_rects or [])]
        self.hovered_window = None
        self._click_candidate_window = None
        self._drag_moved = False
        self.color_format = 'hex'

        self.start = self.end = None
        self.drag = None
        self.origin = None
        self.press = None
        self.hover_pos = None
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowTitle('SnapFlow · 框选截图')
        self.setGeometry(screen.geometry())
        self._pixmap_cache_key = None
        self._bright_pixmap = None
        self._dimmed_pixmap = None
        self._last_dynamic_dirty = QRect()
        self._badge_font = QFont('Microsoft YaHei UI')
        self._badge_font.setPixelSize(12)
        self._win_badge_font = QFont('Microsoft YaHei UI')
        self._win_badge_font.setPixelSize(11)
        self.mode = 'photo'
        self.stop_key = 'Alt+S'
        self.selection_locked = False
        self.long_submitted = False
        self.video_audio_mode = 'silent'
        self.copy_history_enabled = True
        self.canvas = None
        self.crop_origin = None
        self.tool = 'view'
        self.error_text = ''
        self.saved_path = self.saved_image = None
        self.tool_preferences = normalize_tools(preferences)

        self.actions = CaptureGlassPanel(self)
        self.actions.setCursor(Qt.CursorShape.ArrowCursor)
        self.toolbar_layout = QVBoxLayout(self.actions)
        self.toolbar_layout.setContentsMargins(9, 8, 9, 8)
        self.toolbar_layout.setSpacing(6)

        self.action_layout = QHBoxLayout()
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        self.action_layout.setSpacing(4)
        self.toolbar_layout.addLayout(self.action_layout)
        self._modes_stacked = False

        # Capture mode capsule (截图 / 长截图 / 视频)
        self.modes = QWidget(self.actions)
        self.modes.setObjectName('captureModes')
        modes = QHBoxLayout(self.modes)
        modes.setContentsMargins(0, 0, 0, 0)
        modes.setSpacing(3)
        self.mode_group = QButtonGroup(self)
        self.mode_buttons = {}
        for key, label in [('photo', '截图'), ('long', '长截图'), ('video', '视频')]:
            button = QPushButton(label)
            button.setObjectName('modePill')
            button.setCheckable(True)
            button.setMinimumWidth(62)
            button.setFixedHeight(32)
            self.mode_group.addButton(button)
            modes.addWidget(button)
            button.clicked.connect(lambda checked=False, value=key: self.set_mode(value, True))
            self.mode_buttons[key] = button
        self.mode_buttons['photo'].setChecked(True)

        self.video_audio_combo = QComboBox()
        self.video_audio_combo.setObjectName('captureAudio')
        self.video_audio_combo.addItem('无声', 'silent')
        self.video_audio_combo.addItem('有声（电脑声音）', 'system')
        self.video_audio_combo.setAccessibleName('录屏声音')
        self.video_audio_combo.setToolTip('有声：录入默认播放设备的电脑声音，不录麦克风；无声：只录画面')
        self.video_audio_combo.setFixedHeight(32)
        self.video_audio_combo.setMinimumWidth(124)
        self.video_audio_combo.currentIndexChanged.connect(
            lambda: self.set_video_audio_mode(self.video_audio_combo.currentData(), True)
        )
        modes.addWidget(self.video_audio_combo)
        self.video_audio_combo.hide()

        self.modes_divider = QFrame()
        self.modes_divider.setObjectName('selectionDivider')
        self.modes_divider.setFixedSize(1, 20)
        modes.addWidget(self.modes_divider)
        self.hint_label = QLabel()
        self.hint_label.setObjectName('selectionHint')
        modes.addWidget(self.hint_label)
        self.action_layout.setSizeConstraint(QHBoxLayout.SizeConstraint.SetNoConstraint)

        # Row 1: Unified Smart Pointer + 7 annotation tools (stable main-row width)
        self.photo_controls = []
        self.tool_buttons = {}
        self.tool_group = QButtonGroup(self)
        for key, title, icon in [
            ('view', '智能指针 (V) · 移动选区 / 点选标注', 'cursor'),
            ('pen', '画笔 (B) · 按住拖动自由绘画', 'pen'),
            ('highlighter', '荧光笔 (H) · 半透明高亮标记', 'highlighter'),
            ('rectangle', '矩形 (R)', 'rectangle'),
            ('arrow', '箭头 (A)', 'arrow'),
            ('text', '文字 (T)', 'text'),
            ('step', '序号 (N) · 点击依次标注 ①②③', 'step'),
            ('mask', '马赛克 (M) · 按住拖动涂抹打码', 'mask'),
        ]:
            button = QPushButton()
            button.setFixedSize(32, 32)
            button.setCheckable(True)
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.setIcon(line_icon(icon, ICON_COLOR))
            button.setIconSize(QSize(19, 19))
            button.clicked.connect(lambda checked=False, value=key: self.set_tool(value))
            self.tool_group.addButton(button)
            self.tool_buttons[key] = button
            self.action_layout.addWidget(button)
            self.photo_controls.append(button)
        self.tool_buttons['view'].setChecked(True)

        self.tool_divider = QFrame()
        self.tool_divider.setObjectName('selectionDivider')
        self.tool_divider.setFixedSize(1, 20)
        self.action_layout.addWidget(self.tool_divider)
        self.photo_controls.append(self.tool_divider)

        for title, icon, attr, handler in [
            ('撤销', 'undo', 'undo_button', self.undo),
            ('重做', 'redo', 'redo_button', self.redo),
        ]:
            button = QPushButton()
            button.setFixedSize(32, 32)
            button.setIcon(line_icon(icon, ICON_COLOR))
            button.setIconSize(QSize(19, 19))
            button.setToolTip(title + ' · ' + ('Ctrl+Z' if icon == 'undo' else 'Ctrl+Y'))
            button.setAccessibleName(title)
            button.clicked.connect(handler)
            self.action_layout.addWidget(button)
            self.photo_controls.append(button)
            setattr(self, attr, button)

        self.pin_button = QPushButton()
        self.pin_button.setFixedSize(32, 32)
        self.pin_button.setIcon(line_icon('pin', ICON_COLOR))
        self.pin_button.setIconSize(QSize(19, 19))
        self.pin_button.setToolTip('贴图 (F / Ctrl+P) · 原位 1:1 置顶悬浮')
        self.pin_button.setAccessibleName('贴到屏幕')
        self.pin_button.clicked.connect(self.pin)
        self.action_layout.addWidget(self.pin_button)
        self.photo_controls.append(self.pin_button)

        self.beautify_button = QPushButton()
        self.beautify_button.setFixedSize(32, 32)
        self.beautify_button.setIcon(line_icon('sparkle', ICON_COLOR))
        self.beautify_button.setIconSize(QSize(19, 19))
        self.beautify_button.setToolTip('美化套壳 · 渐变背景与圆角阴影')
        self.beautify_button.setAccessibleName('美化套壳')
        self.beautify_button.clicked.connect(self.beautify)
        self.action_layout.addWidget(self.beautify_button)
        self.photo_controls.append(self.beautify_button)

        self.save_button = QPushButton('保存')
        self.save_button.setIcon(line_icon('save', ICON_COLOR))
        self.save_button.setIconSize(QSize(16, 16))
        self.save_button.setToolTip('保存 PNG 并复制 (Ctrl+S) · Ctrl+Shift+S 另存为')
        self.save_label = '保存'
        self.save_button.setFixedHeight(32)
        self.save_button.clicked.connect(self.save)
        self.action_layout.addWidget(self.save_button)
        self.photo_controls.append(self.save_button)

        self.action_layout.addWidget(self.modes)

        cancel = QPushButton()
        cancel.setFixedSize(32, 32)
        cancel.setIcon(line_icon('close', '#ff827c'))
        cancel.setIconSize(QSize(20, 20))
        self.cancel_button = cancel
        cancel.setToolTip('取消 · Esc')
        cancel.setAccessibleName('取消截图')
        cancel.clicked.connect(self.cancelled.emit)
        self.action_layout.addWidget(cancel)

        self.skip_countdown_button = QPushButton('立即开始')
        self.skip_countdown_button.setObjectName('skipCountdown')
        self.skip_countdown_button.setFixedHeight(32)
        self.skip_countdown_button.setIcon(line_icon('fast_forward', '#ffffff'))
        self.skip_countdown_button.setIconSize(QSize(15, 15))
        self.skip_countdown_button.setToolTip('跳过倒计时立即开始录屏')
        self.skip_countdown_button.clicked.connect(self.skip_countdown_requested.emit)
        self.skip_countdown_button.hide()
        self.action_layout.addWidget(self.skip_countdown_button)

        self.confirm_button = QPushButton('完成 · 复制')
        self.confirm_button.setObjectName('confirmSelection')
        self.confirm_button.setFixedHeight(32)
        self.confirm_button.setIcon(line_icon('check', '#ffffff'))
        self.confirm_button.setIconSize(QSize(17, 17))
        self.confirm_button.setToolTip('复制截图 (Enter / 选区内双击)')
        self.confirm_button.clicked.connect(lambda: self.confirm())
        self.action_layout.addWidget(self.confirm_button)

        for index in range(self.action_layout.count()):
            w = self.action_layout.itemAt(index).widget()
            if w is not None:
                self.action_layout.setAlignment(w, Qt.AlignmentFlag.AlignVCenter)

        # Row 2: Dedicated secondary style bar (prevents Row 1 width jumps!)
        self.style_bar = QFrame(self.actions)
        self.style_bar.setObjectName('styleSubBar')
        style_row = QHBoxLayout(self.style_bar)
        style_row.setContentsMargins(10, 5, 10, 5)
        style_row.setSpacing(6)

        self.size_preset_group = QButtonGroup(self)
        self.size_preset_buttons = []
        for idx, (radius, label) in enumerate([(2.6, '细'), (4.5, '中'), (6.5, '粗')]):
            dot = SizeDotButton(radius, f'快速粗细：{label}（也可用滚轮或 [ ] 微调）', self.style_bar)
            dot.clicked.connect(lambda _=False, i=idx: self._apply_size_preset(i))
            self.size_preset_group.addButton(dot, idx)
            self.size_preset_buttons.append(dot)
            style_row.addWidget(dot)

        self.style_groups = []
        self.option_groups = {}
        for title, attr, minimum, maximum, value in [
            ('线宽', 'width_spin', 1, 16, 3),
            ('字号', 'size_spin', 12, 64, 22),
            ('笔刷', 'brush_spin', 4, 64, 12),
            ('颗粒', 'block_spin', 2, 32, 6),
        ]:
            group = QWidget(self.style_bar)
            row = QHBoxLayout(group)
            row.setContentsMargins(2, 0, 0, 0)
            row.setSpacing(4)
            group.setFixedHeight(28)
            caption = QLabel(title)
            row.addWidget(caption)
            spin = QSpinBox()
            spin.setRange(minimum, maximum)
            spin.setValue(value)
            spin.setFixedSize(58, 26)
            spin.setAccessibleName(title)
            row.addWidget(spin)
            style_row.addWidget(group)
            setattr(self, attr, spin)
            self.style_groups.append((caption, title, spin))
            self.option_groups[attr] = group
        self.width_spin.valueChanged.connect(lambda value: self.change_style(width=value))
        self.width_spin.setToolTip('画笔、矩形或箭头的线宽（滚轮或 [ ] 快捷微调）')
        self.size_spin.valueChanged.connect(lambda value: self.change_style(size=value))
        self.brush_spin.valueChanged.connect(lambda value: self.change_style(brush=value))
        self.block_spin.valueChanged.connect(lambda value: self.change_style(block=value))
        self.brush_spin.setToolTip('马赛克涂抹范围的直径')
        self.block_spin.setToolTip('马赛克像素块的大小')

        self.style_color_divider = QFrame(self.style_bar)
        self.style_color_divider.setObjectName('selectionDivider')
        self.style_color_divider.setFixedSize(1, 18)
        style_row.addWidget(self.style_color_divider)

        self.color_group = QButtonGroup(self)
        self.color_buttons = []
        for color, title in COLOR_CHOICES:
            button = QPushButton(self.style_bar)
            button.setObjectName('colorChoice')
            button.setFixedSize(20, 20)
            button.setCheckable(True)
            button.setStyleSheet(f'QPushButton#colorChoice {{ background:{color}; }}')
            button.setToolTip(title)
            button.setAccessibleName(title)
            button.clicked.connect(lambda checked=False, value=color: self.change_style(color=value))
            self.color_group.addButton(button)
            self.color_buttons.append(button)
            style_row.addWidget(button)
        self.color_buttons[0].setChecked(True)
        style_row.addStretch(1)
        self.style_hint = QLabel('滚轮 / [ ] 调大小 · 右键返回', self.style_bar)
        self.style_hint.setObjectName('styleHint')
        style_row.addWidget(self.style_hint)

        self.style_bar.hide()
        self.toolbar_layout.addWidget(self.style_bar)

        for key, handler in [
            ('Return', lambda: self.confirm(True)),
            ('Enter', lambda: self.confirm(True)),
            ('Escape', self.handle_escape),
            ('Ctrl+Z', self.undo),
            ('Ctrl+Y', self.redo),
            ('Ctrl+S', self.save),
            ('Ctrl+Shift+S', self.save_as),
            ('Ctrl+P', self.pin),
            ('Ctrl+A', self.select_full_screen),
        ]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(handler)
        self.shortcuts = self.findChildren(QShortcut)
        self.actions.hide()
        self.refresh_options()
        self.refresh_toolbar()
        self.position_actions()

    def _active_size_key(self):
        kind = self.effective_tool()
        if kind in ('pen', 'highlighter', 'rectangle', 'arrow'):
            return 'width'
        if kind in ('text', 'step'):
            return 'size'
        if kind == 'mask':
            return 'brush'
        return None

    def _apply_size_preset(self, index):
        key = self._active_size_key()
        if key not in _SIZE_PRESETS:
            return
        value = _SIZE_PRESETS[key][max(0, min(2, index))]
        self.change_style(**{key: value})

    def adjust_active_size(self, delta_step):
        key = self._active_size_key()
        if key is None:
            return False
        attr = {'width': 'width_spin', 'size': 'size_spin', 'brush': 'brush_spin'}[key]
        spin = getattr(self, attr)
        step = 2 if key in ('size', 'brush') else 1
        target = max(spin.minimum(), min(spin.maximum(), spin.value() + delta_step * step))
        if target != spin.value():
            spin.setValue(target)
        return True

    def set_copy_history_enabled(self, enabled: bool):
        self.copy_history_enabled = bool(enabled)
        if self.mode == 'photo':
            self.confirm_button.setToolTip(self._photo_copy_tooltip())

    def _photo_copy_tooltip(self):
        if self.copy_history_enabled:
            return '复制到剪贴板并暂存至本机剪贴历史（可在设置中关闭） · Enter 或选区内双击'
        return '仅复制到剪贴板，不写入磁盘文件 · Enter 或选区内双击'

    def refresh_toolbar(self):
        if not hasattr(self, 'hint_label'):
            return
        hint = '悬停单击选窗口，拖拽自由框选 · Esc 取消'
        if self.mode == 'video':
            hint = audio_label(self.video_audio_mode) + ' · ' + self.stop_key + ' 停止'
        elif self.mode == 'long':
            hint = '框选正文后自动开始，直接上下滚动'
        if self.selection_locked:
            hint = '区域已锁定 · Esc 取消'
        if self.error_text:
            hint = self.error_text
        self.hint_label.setToolTip('拖动选取区域；拖动四边调整大小，内部移动，双击复制。' + hint)
        width = max(70, min(320, self.width() - (500 if self.mode == 'video' else 350)))
        self.hint_label.setText(self.hint_label.fontMetrics().elidedText(hint, Qt.TextElideMode.ElideRight, width))
        self.hint_label.setMaximumWidth(width)
        icon_map = {'photo': 'capture', 'long': 'scroll', 'video': 'video'}
        for mode, button in self.mode_buttons.items():
            button.setIcon(line_icon(icon_map[mode], '#ffffff' if button.isChecked() else MUTED_ICON_COLOR))
            button.setIconSize(QSize(15, 15))
        if hasattr(self, 'confirm_button'):
            if self.mode == 'photo':
                self.confirm_button.setToolTip(self._photo_copy_tooltip())
            self.position_actions()

    def set_video_audio_mode(self, mode, announce=False):
        if self.selection_locked:
            return
        self.video_audio_mode = normalize_audio_mode(mode)
        blocked = self.video_audio_combo.blockSignals(True)
        self.video_audio_combo.setCurrentIndex(1 if self.video_audio_mode == 'system' else 0)
        self.video_audio_combo.blockSignals(blocked)
        self.refresh_toolbar()
        if self.mode == 'video':
            self.confirm_button.setToolTip('开始' + audio_label(self.video_audio_mode) + '录屏')
        if announce:
            self.video_audio_changed.emit(self.video_audio_mode)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.refresh_toolbar()
        if hasattr(self, 'actions') and self.actions.isVisible():
            self.position_actions()

    def set_mode(self, mode, announce=False):
        if self.selection_locked:
            return
        if mode not in self.mode_buttons:
            return
        self.mode = mode
        self.error_text = ''
        self.mode_buttons[mode].setChecked(True)
        self.video_audio_combo.setVisible(mode == 'video')
        if self.canvas:
            self.canvas.finish_text()
            self.canvas.setVisible(mode == 'photo')
        self.refresh_options()
        self.confirm_button.setText(
            '开始录制  ↵' if mode == 'video' else '开始长截图  ↵' if mode == 'long' else '完成 · 复制'
        )
        self.confirm_button.setToolTip(
            '开始' + audio_label(self.video_audio_mode) + '录屏'
            if mode == 'video'
            else '框选区域内上下滚动，自动拼接并去重'
            if mode == 'long'
            else self._photo_copy_tooltip()
        )
        self.confirm_button.setIcon(
            line_icon('video' if mode == 'video' else 'scroll' if mode == 'long' else 'check', '#ffffff')
        )
        self.refresh_toolbar()
        if self.actions.isVisible():
            self.position_actions()
        self.update()
        if announce:
            self.mode_changed.emit(mode)
            if mode == 'long' and self.start is not None:
                self.confirm()

    def lock_selection(self, show_skip=False):
        self.selection_locked = True
        self.drag = None
        self.modes.setEnabled(False)
        self.confirm_button.setEnabled(False)
        self.skip_countdown_button.setVisible(bool(show_skip))
        for widget in self.photo_controls:
            widget.setEnabled(False)
        if self.canvas:
            self.canvas.setEnabled(False)
        self.style_bar.hide()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.refresh_toolbar()
        self.update()

    def selection_rect(self):
        return QRectF(self.start, self.end).normalized() if self.start is not None else QRectF()

    def handles(self):
        r = self.selection_rect()
        x, y = r.center().x(), r.center().y()
        return {
            'nw': r.topLeft(), 'n': QPointF(x, r.top()), 'ne': r.topRight(), 'e': QPointF(r.right(), y),
            'se': r.bottomRight(), 's': QPointF(x, r.bottom()), 'sw': r.bottomLeft(), 'w': QPointF(r.left(), y),
        }

    def hit_test_selection(self, point, edge_margin=7):
        """Return corner/edge/move hit target for full 4-edge + 4-corner resizing."""
        if self.start is None:
            return None
        r = self.selection_rect()
        # Corners first (highest priority)
        for key in ('nw', 'ne', 'sw', 'se'):
            h = self.handles()[key]
            if max(abs(point.x() - h.x()), abs(point.y() - h.y())) <= 10:
                return key
        # Midpoint handles
        for key in ('n', 's', 'w', 'e'):
            h = self.handles()[key]
            if (h - point).manhattanLength() <= 10:
                return key
        # Full 4 border edges
        if r.left() - edge_margin <= point.x() <= r.right() + edge_margin:
            if abs(point.y() - r.top()) <= edge_margin:
                return 'n'
            if abs(point.y() - r.bottom()) <= edge_margin:
                return 's'
        if r.top() - edge_margin <= point.y() <= r.bottom() + edge_margin:
            if abs(point.x() - r.left()) <= edge_margin:
                return 'w'
            if abs(point.x() - r.right()) <= edge_margin:
                return 'e'
        if r.contains(point):
            return 'move'
        return None

    @staticmethod
    def cursor_for_hit(hit):
        if hit in ('nw', 'se'):
            return Qt.CursorShape.SizeFDiagCursor
        if hit in ('ne', 'sw'):
            return Qt.CursorShape.SizeBDiagCursor
        if hit in ('n', 's'):
            return Qt.CursorShape.SizeVerCursor
        if hit in ('w', 'e'):
            return Qt.CursorShape.SizeHorCursor
        if hit == 'move':
            return Qt.CursorShape.SizeAllCursor
        return Qt.CursorShape.CrossCursor

    def position_actions(self):
        if not hasattr(self, 'confirm_button'):
            return
        r = self.selection_rect()
        selected = self.start is not None
        self.confirm_button.setVisible(selected)
        show_hint = (not selected) or bool(self.error_text) or (self.mode == 'long' and not self.selection_locked)
        self.hint_label.setVisible(show_hint)
        self.modes_divider.setVisible(show_hint)
        available = max(1, self.width() - 24)

        # Restore inline mode layout before checking width fit.
        if self._modes_stacked:
            self.toolbar_layout.removeWidget(self.modes)
            self.action_layout.insertWidget(self.action_layout.indexOf(self.cancel_button), self.modes)
            self._modes_stacked = False

        icons = [
            *self.tool_buttons.values(),
            self.undo_button,
            self.redo_button,
            self.pin_button,
            self.beautify_button,
            self.cancel_button,
        ]
        for button in icons:
            button.setFixedSize(32, 32)
        for button in self.color_buttons:
            button.setFixedSize(20, 20)
        for caption, title, spin in self.style_groups:
            caption.setText(title)
            spin.setFixedWidth(58)
        self.style_hint.setVisible(available >= 720)
        self.action_layout.setSpacing(4)
        self.save_button.setText(self.save_label)
        if self.mode == 'photo':
            self.confirm_button.setText('完成 · 复制')
        self.action_layout.invalidate()
        border = self.actions.frameWidth() * 2
        margins = self.toolbar_layout.contentsMargins()
        padding = margins.left() + margins.right() + border
        self.modes.adjustSize()

        if self.action_layout.sizeHint().width() + padding > available:
            self.action_layout.removeWidget(self.modes)
            self.toolbar_layout.addWidget(self.modes, 0, Qt.AlignmentFlag.AlignRight)
            self._modes_stacked = True
            self.action_layout.invalidate()

        if self.action_layout.sizeHint().width() + padding > available:
            for button in icons:
                button.setFixedSize(24, 32)
            for button in self.color_buttons:
                button.setFixedSize(16, 16)
            for caption, title, spin in self.style_groups:
                caption.setText(title[0])
                spin.setFixedWidth(36)
            self.action_layout.setSpacing(2)
            self.save_button.setText('保存')
            if self.mode == 'photo':
                self.confirm_button.setText('复制')
            self.action_layout.invalidate()

        self.toolbar_layout.invalidate()
        hint = self.toolbar_layout.sizeHint()
        self.actions.resize(min(available, hint.width() + border), hint.height() + border)
        self.toolbar_layout.activate()

        x = int(r.right()) - self.actions.width() if selected else (self.width() - self.actions.width()) // 2
        x = max(8, min(self.width() - self.actions.width() - 8, x))
        y = int(r.bottom()) + 12 if selected else self.height() - self.actions.height() - 20
        if y + self.actions.height() > self.height() - 8:
            y = int(r.top()) - self.actions.height() - 12
        y = max(8, min(self.height() - self.actions.height() - 8, y))
        self.actions.move(x, y)
        self.actions.show()
        self.actions.raise_()

    def show_error(self, text):
        self.error_text = text
        self.refresh_toolbar()
        self.hint_label.setToolTip(text)

    def set_tool(self, tool):
        self.tool = tool
        btn_key = 'view' if tool == 'select' else tool
        if btn_key in self.tool_buttons:
            self.tool_buttons[btn_key].setChecked(True)
        if self.canvas:
            self.canvas.set_tool(tool)
        self.refresh_options()

    def change_style(self, **style):
        kind = self.effective_tool()
        if kind in self.tool_preferences:
            self.tool_preferences[kind].update({k: v for k, v in style.items() if k in self.tool_preferences[kind]})
        if self.canvas:
            self.canvas.apply_style(**style)
        self.preferences_changed.emit(copy.deepcopy(self.tool_preferences))
        self.refresh_options()

    def effective_tool(self):
        if self.tool in ('view', 'select') and self.canvas and self.canvas.selected_index is not None:
            return self.canvas.marks[self.canvas.selected_index][0]
        return self.tool

    def refresh_options(self):
        if not hasattr(self, 'block_spin'):
            return
        kind = self.effective_tool()
        photo = self.mode == 'photo' and self.start is not None
        for widget in self.photo_controls:
            widget.setVisible(photo)

        has_colors = kind in ('pen', 'highlighter', 'rectangle', 'arrow', 'text', 'step')
        has_style = photo and not self.selection_locked and kind in (
            'pen', 'highlighter', 'rectangle', 'arrow', 'text', 'step', 'mask'
        )
        self.style_bar.setVisible(has_style)
        self.style_color_divider.setVisible(has_style and has_colors)
        for button in self.color_buttons:
            button.setVisible(has_style and has_colors)
        visible = {
            'width_spin': kind in ('pen', 'highlighter', 'rectangle', 'arrow'),
            'size_spin': kind in ('text', 'step'),
            'brush_spin': kind == 'mask',
            'block_spin': kind == 'mask',
        }
        for attr, group in self.option_groups.items():
            group.setVisible(has_style and visible[attr])

        values = dict(self.tool_preferences.get(kind, {}))
        if self.canvas and self.canvas.selected_index is not None:
            from .capture_markup import style_of
            mark = self.canvas.marks[self.canvas.selected_index]
            values.update(style_of(mark))
            values['color'] = mark[4]
            if kind == 'mask':
                values['brush'] = values.get('brush', values.get('width', 3) * 4)

        for key, attr in [('width', 'width_spin'), ('size', 'size_spin'), ('brush', 'brush_spin'), ('block', 'block_spin')]:
            if key in values:
                spin = getattr(self, attr)
                blocked = spin.blockSignals(True)
                spin.setValue(values[key])
                spin.blockSignals(blocked)

        # Highlight nearest quick size dot
        size_key = self._active_size_key()
        if size_key in _SIZE_PRESETS:
            current_val = values.get(size_key, _SIZE_PRESETS[size_key][0])
            nearest = min(range(3), key=lambda i: abs(_SIZE_PRESETS[size_key][i] - current_val))
            for i, dot in enumerate(self.size_preset_buttons):
                dot.setVisible(has_style)
                dot.setChecked(i == nearest)
        else:
            for dot in self.size_preset_buttons:
                dot.setVisible(False)

        color = values.get('color', '#e34f45')
        for button, choice in zip(self.color_buttons, COLORS):
            button.setChecked(choice == color)
        if self.canvas:
            self.canvas.color = color
            self.canvas.line_width = self.width_spin.value()
            self.canvas.text_size = self.size_spin.value()
            self.canvas.brush_size = self.brush_spin.value()
            self.canvas.mosaic_block = self.block_spin.value()
            self.canvas.update()
        if self.actions.isVisible():
            self.position_actions()

    def undo(self):
        if self.canvas:
            if self.canvas.text_editor is not None:
                self.canvas.text_editor.undo()
            else:
                self.canvas.undo()

    def redo(self):
        if self.canvas:
            if self.canvas.text_editor is not None:
                self.canvas.text_editor.redo()
            else:
                self.canvas.redo()

    def reset_selection(self):
        """Return to pre-selection state so user can re-box without restarting capture."""
        if self.selection_locked:
            return
        if self.canvas:
            self.canvas.set_drag_hidden(False)
            self.canvas.cancel_text()
            self.canvas.hide()
            self.canvas.marks = []
            self.canvas.history = []
            self.canvas.future = []
            self.canvas.selected_index = None
        self.start = self.end = None
        self.drag = None
        self.error_text = ''
        self.tool = 'view'
        self.tool_buttons['view'].setChecked(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.refresh_options()
        self.refresh_toolbar()
        self.position_actions()
        self.update()

    def select_full_screen(self):
        if self.selection_locked:
            return
        if self.canvas and self.canvas.text_editor is not None:
            self.canvas.text_editor.selectAll()
            return
        r = QRectF(self.rect())
        if r.width() < 2 or r.height() < 2:
            return
        self.start, self.end = r.topLeft(), r.bottomRight()
        self.hovered_window = None
        self.refresh_canvas(reset=True)
        self.refresh_toolbar()
        self.position_actions()
        self.update()

    def handle_escape(self):
        if self.canvas and self.canvas.text_editor is not None:
            self.canvas.cancel_text()
            self.setFocus()
            return
        self.cancelled.emit()

    def handle_right_click(self):
        """Tiered backout: cancel text -> exit drawing tool -> clear selection -> exit capture."""
        if self.selection_locked:
            self.cancelled.emit()
            return
        if self.canvas and self.canvas.text_editor is not None:
            self.canvas.cancel_text()
            self.setFocus()
            return
        if self.start is not None:
            if self.mode == 'photo' and self.tool not in ('view', 'select'):
                self.set_tool('view')
                return
            self.reset_selection()
            return
        self.cancelled.emit()

    def refresh_canvas(self, reset=False):
        image = crop_selection(self.image, self.selection_rect(), self.size())
        r = self.selection_rect()
        sx, sy = pixel_scale(self.image, self.size())
        origin = QPointF(selection_pixels(self.image, r, self.size()).topLeft())
        previous = self.canvas
        if previous is None:
            self.canvas = InlineAnnotationCanvas(image, self)
            self.canvas.changed.connect(self.update_annotation_controls)
            self.canvas.selection_changed.connect(self.update_annotation_controls)
        else:
            previous.finish_text()
            delta = (self.crop_origin - origin) if self.crop_origin is not None else QPointF()

            def shifted(marks):
                result = []
                for old in marks:
                    mark = list(copy.deepcopy(old))
                    mark[1] += delta
                    mark[2] += delta
                    result.append(tuple(mark))
                return result

            if reset:
                previous.marks = []
                previous.history = []
                previous.future = []
            else:
                previous.marks = shifted(previous.marks)
                previous.history = [shifted(m) for m in previous.history]
                previous.future = [shifted(m) for m in previous.future]
            previous.image = image
            previous.cached_image = previous.cached_marks = previous.cached_pixmap = previous._drag_base_pixmap = None
            previous.selected_index = None
        self.crop_origin = origin
        self.canvas.setGeometry(r.toRect())
        self.canvas.pixel_mapping = (sx, sy, origin.x() / sx - self.canvas.x(), origin.y() / sy - self.canvas.y())
        self.canvas.set_tool(self.tool)
        self.canvas.setVisible(self.mode == 'photo')
        self.canvas.update()
        self.update_annotation_controls()
        self.actions.raise_()
        self.modes.raise_()

    def update_annotation_controls(self):
        if self.canvas:
            self.canvas._sync_mouse_passthrough()
        self.undo_button.setEnabled(bool(self.canvas and self.canvas.history) and not self.selection_locked)
        self.redo_button.setEnabled(bool(self.canvas and self.canvas.future) and not self.selection_locked)
        self.refresh_options()

    def _window_at(self, pos):
        if pos is None or not self.window_rects:
            return None
        for rect in self.window_rects:
            if rect.contains(pos):
                return rect
        return None

    def _ensure_pixmaps(self):
        key = (self.image.cacheKey(), self.image.width(), self.image.height())
        if self._pixmap_cache_key == key and self._bright_pixmap is not None and self._dimmed_pixmap is not None:
            return
        src = self.image.convertToFormat(self.image.Format.Format_ARGB32_Premultiplied) if self.image.format() not in (
            self.image.Format.Format_RGB32,
            self.image.Format.Format_ARGB32_Premultiplied,
        ) else self.image
        self._bright_pixmap = QPixmap.fromImage(src)
        self._bright_pixmap.setDevicePixelRatio(1.0)
        dimmed = src.copy()
        dp = QPainter(dimmed)
        dp.fillRect(dimmed.rect(), QColor(7, 15, 26, 112))
        dp.end()
        self._dimmed_pixmap = QPixmap.fromImage(dimmed)
        self._dimmed_pixmap.setDevicePixelRatio(1.0)
        self._pixmap_cache_key = key

    def _dynamic_dirty_rect(self):
        bounds = QRect()
        if self.start is not None:
            r = self.selection_rect().toAlignedRect()
            # Include resize handles, corner caps, and the W x H px badge even for narrow selections
            right_pad = max(24, 190 - r.width())
            bounds = r.adjusted(-24, -56, right_pad, 24)
        else:
            if self.hovered_window is not None:
                bounds = bounds.united(self.hovered_window.toAlignedRect().adjusted(-20, -48, 240, 20))
            if self.hover_pos is not None:
                px, py = int(self.hover_pos.x()), int(self.hover_pos.y())
                bounds = bounds.united(QRect(px - 175, py - 185, 350, 370))
        return bounds.intersected(self.rect())

    def _update_dynamic(self):
        current = self._dynamic_dirty_rect()
        dirty = self._last_dynamic_dirty.united(current).intersected(self.rect())
        self._last_dynamic_dirty = current
        if not dirty.isEmpty():
            self.update(dirty)

    def paintEvent(self, event):
        self._ensure_pixmaps()
        sx, sy = pixel_scale(self.image, self.size())
        clip_rect = event.rect().intersected(self.rect())
        if clip_rect.isEmpty():
            return
        p = QPainter(self)
        p.setClipRect(clip_rect)
        # Blit pre-dimmed background ONLY inside dirty clip rect (zero per-frame alpha blending!).
        dim_src = QRectF(clip_rect.x() * sx, clip_rect.y() * sy, clip_rect.width() * sx, clip_rect.height() * sy)
        p.drawPixmap(QRectF(clip_rect), self._dimmed_pixmap, dim_src)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.start is None and self.hovered_window is not None:
            hr = self.hovered_window.intersected(QRectF(self.rect()))
            if hr.width() >= 4 and hr.height() >= 4:
                vis = hr.intersected(QRectF(clip_rect))
                if not vis.isEmpty():
                    vis_src = QRectF(vis.x() * sx, vis.y() * sy, vis.width() * sx, vis.height() * sy)
                    p.drawPixmap(vis, self._bright_pixmap, vis_src)
                p.setPen(QPen(QColor('#7dd3fc'), 2.0))
                p.setBrush(QColor(125, 211, 252, 16))
                p.drawRect(hr)
                p.setFont(self._win_badge_font)
                pixels = selection_pixels(self.image, hr, self.size())
                tag = f'{pixels.width()} × {pixels.height()} px · 单击选中窗口'
                tw = p.fontMetrics().horizontalAdvance(tag) + 22
                bx = max(8, min(self.width() - tw - 8, hr.left() + 8))
                by = max(8, hr.top() - 32 if hr.top() >= 40 else hr.top() + 8)
                badge = QRectF(bx, by, tw, 24)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(14, 29, 46, 232))
                p.drawRoundedRect(badge, 7, 7)
                p.setPen(QColor('#e5f5ff'))
                p.drawText(badge, Qt.AlignmentFlag.AlignCenter, tag)

        if self.start is not None:
            r = self.selection_rect()
            vis = r.intersected(QRectF(clip_rect))
            if not vis.isEmpty():
                vis_src = QRectF(vis.x() * sx, vis.y() * sy, vis.width() * sx, vis.height() * sy)
                p.drawPixmap(vis, self._bright_pixmap, vis_src)
            p.setPen(QPen(QColor(SELECTION_COLOR), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
            corner = min(15, r.width() / 3, r.height() / 3)
            p.setPen(QPen(QColor(CORNER_COLOR), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for point, dx, dy in [
                (r.topLeft(), 1, 1), (r.topRight(), -1, 1), (r.bottomLeft(), 1, -1), (r.bottomRight(), -1, -1)
            ]:
                p.drawLine(point, point + QPointF(dx * corner, 0))
                p.drawLine(point, point + QPointF(0, dy * corner))
            p.setPen(QPen(QColor(HANDLE_COLOR), 1.2))
            p.setBrush(QColor('#e5f5ff'))
            for point in self.handles().values():
                p.drawEllipse(point, 3.5, 3.5)
            p.setFont(self._badge_font)
            pixels = selection_pixels(self.image, r, self.size()) if r.width() >= 2 and r.height() >= 2 else None
            pixel_width = pixels.width() if pixels else 0
            pixel_height = pixels.height() if pixels else 0
            text = f'{pixel_width} × {pixel_height} px'
            badge_width = p.fontMetrics().horizontalAdvance(text) + 26
            x = max(8, min(self.width() - badge_width - 8, r.left()))
            y = max(8, r.top() - 38)
            badge = QRectF(x, y, badge_width, 28)
            if self.actions.isVisible() and badge.intersects(QRectF(self.actions.geometry())):
                badge.moveTop(max(8, r.top() + 12))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(17, 36, 53, 235))
            p.drawRoundedRect(badge, 8, 8)
            p.setPen(QColor('#e5f5ff'))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)

        paint_panel_shadows(p, (self.actions,))
        if (
            self.start is None
            and self.hover_pos is not None
            and not (self.actions.isVisible() and self.actions.geometry().contains(self.hover_pos.toPoint()))
        ):
            self._paint_eyedropper(p, self.hover_pos)
        p.end()

    def sample_color(self, pos=None):
        point = pos if pos is not None else self.hover_pos
        if point is None or self.image.isNull():
            return None
        sx, sy = pixel_scale(self.image, self.size())
        px = max(0, min(self.image.width() - 1, int(point.x() * sx)))
        py = max(0, min(self.image.height() - 1, int(point.y() * sy)))
        return self.image.pixelColor(px, py)

    def format_color(self, color):
        if self.color_format == 'rgb':
            return f'rgb({color.red()}, {color.green()}, {color.blue()})'
        return color.name(QColor.NameFormat.HexRgb).upper()

    def _paint_eyedropper(self, p, pos):
        sx, sy = pixel_scale(self.image, self.size())
        px = max(0, min(self.image.width() - 1, int(pos.x() * sx)))
        py = max(0, min(self.image.height() - 1, int(pos.y() * sy)))
        color = self.image.pixelColor(px, py)
        color_text = self.format_color(color)

        box_w, box_h = 136, 148
        x = pos.x() + 18
        y = pos.y() + 18
        if x + box_w > self.width() - 8:
            x = pos.x() - box_w - 14
        if y + box_h > self.height() - 8:
            y = pos.y() - box_h - 14
        x = max(8, x)
        y = max(8, y)

        box = QRectF(x, y, box_w, box_h)
        p.setPen(QPen(QColor(155, 205, 242, 70), 1))
        p.setBrush(QColor(14, 22, 36, 232))
        p.drawRoundedRect(box, 10, 10)

        cell = 14
        grid_x = x + (box_w - cell * 7) / 2
        grid_y = y + 9
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                sx_i = max(0, min(self.image.width() - 1, px + dx))
                sy_i = max(0, min(self.image.height() - 1, py + dy))
                p.setPen(QPen(QColor(255, 255, 255, 20), 0.5))
                p.setBrush(self.image.pixelColor(sx_i, sy_i))
                p.drawRect(QRectF(grid_x + (dx + 3) * cell, grid_y + (dy + 3) * cell, cell, cell))

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor('#7dd3fc'), 1.8))
        p.drawRect(QRectF(grid_x + 3 * cell, grid_y + 3 * cell, cell, cell))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(x + 15, grid_y + cell * 7 + 14), 5.5, 5.5)

        font = QFont('Microsoft YaHei UI')
        font.setPixelSize(10 if self.color_format == 'rgb' else 11)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor('#f0f6fc'))
        p.drawText(QRectF(x + 25, grid_y + cell * 7 + 5, box_w - 30, 18), Qt.AlignmentFlag.AlignVCenter, color_text)

        font.setBold(False)
        font.setPixelSize(9)
        p.setFont(font)
        p.setPen(QColor('#9bb2c9'))
        p.drawText(QRectF(x + 6, grid_y + cell * 7 + 24, box_w - 12, 15), Qt.AlignmentFlag.AlignCenter, 'C 复制 · Shift 切格式')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.handle_right_click()
            return
        if self.selection_locked:
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.begin_drag(event.position())

    def mouseDoubleClickEvent(self, event):
        if self.selection_locked or event.button() != Qt.MouseButton.LeftButton:
            return
        if self.start is not None and self.selection_rect().contains(event.position()) and self.tool == 'view':
            self.drag = None
            self.confirm()

    def begin_drag(self, point):
        if self.selection_locked:
            return
        self._click_candidate_window = self.hovered_window if self.start is None else None
        self.hover_pos = None
        self.hovered_window = None
        self._drag_moved = False
        if self.canvas:
            self.canvas.finish_text()
        self.press = point
        self.origin = self.selection_rect()
        self.drag = 'new'
        if self.start is not None:
            hit = self.hit_test_selection(point)
            self.drag = hit if hit is not None else 'new'
        if self.drag == 'new':
            self.start = self.end = point
            if self.canvas:
                self.canvas.hide()
            self.actions.hide()
            self._last_dynamic_dirty = self._dynamic_dirty_rect()
            self.update()
        else:
            self._last_dynamic_dirty = self._dynamic_dirty_rect()

    def mouseMoveEvent(self, event):
        if self.selection_locked:
            return
        if self.drag is None:
            if self.start is None:
                self.hover_pos = event.position()
                self.hovered_window = self._window_at(self.hover_pos)
                self.setCursor(Qt.CursorShape.CrossCursor)
                self._update_dynamic()
            else:
                if self.hover_pos is not None:
                    self.hover_pos = None
                    self._update_dynamic()
                hit = self.hit_test_selection(event.position())
                self.setCursor(self.cursor_for_hit(hit))
            return
        self.move_drag(event.position())

    def leaveEvent(self, event):
        if self.hover_pos is not None or self.hovered_window is not None:
            self.hover_pos = None
            self.hovered_window = None
            self._update_dynamic()
        super().leaveEvent(event)

    def move_drag(self, position):
        if self.selection_locked or self.drag is None:
            return
        point = QPointF(max(0, min(self.width(), position.x())), max(0, min(self.height(), position.y())))
        if not self._drag_moved and self.press is not None and (point - self.press).manhattanLength() >= 2:
            self._drag_moved = True
            # Never call self.canvas.hide() mid-drag when canvas may hold the mouse grab;
            # suppress its painting instead so Qt's implicit mouse grab stays uninterrupted.
            if self.canvas:
                self.canvas.set_drag_hidden(True)
            if self.actions.isVisible():
                shadow_rect = self.actions.geometry().adjusted(-12, -12, 12, 16)
                self.actions.hide()
                self.update(shadow_rect)
        if self.drag == 'new':
            self.end = point
        else:
            r = QRectF(self.origin)
            if self.drag == 'move':
                delta = point - self.press
                delta = QPointF(
                    max(-r.left(), min(self.width() - r.right(), delta.x())),
                    max(-r.top(), min(self.height() - r.bottom(), delta.y())),
                )
                r.translate(delta)
            else:
                if 'w' in self.drag:
                    r.setLeft(min(point.x(), r.right() - 2))
                if 'e' in self.drag:
                    r.setRight(max(point.x(), r.left() + 2))
                if 'n' in self.drag:
                    r.setTop(min(point.y(), r.bottom() - 2))
                if 's' in self.drag:
                    r.setBottom(max(point.y(), r.top() + 2))
            self.start, self.end = r.topLeft(), r.bottomRight()
        self._update_dynamic()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.drag is None:
            return
        self.end_drag(event.position())

    def end_drag(self, point):
        if self.drag is None:
            return
        reset = self.drag == 'new'
        self.move_drag(point)
        was_moved = self._drag_moved
        self.drag = None
        if self.canvas:
            self.canvas.set_drag_hidden(False)
        r = self.selection_rect()
        if reset and r.width() < 4 and r.height() < 4 and self._click_candidate_window is not None:
            r = self._click_candidate_window.intersected(QRectF(self.rect()))
            self._click_candidate_window = None
        if r.width() < 2 or r.height() < 2:
            self.start = self.end = None
            self.refresh_options()
            self.position_actions()
            self.update()
            return
        r = QRectF(r.toAlignedRect()).intersected(QRectF(self.rect()))
        self.start, self.end = r.topLeft(), r.bottomRight()
        if not reset and not was_moved and self.canvas is not None and self.canvas.isVisible():
            # Simple click inside selection without moving: avoid flickering canvas/toolbar.
            self._update_dynamic()
            return
        self.refresh_canvas(reset)
        self.refresh_toolbar()
        self.position_actions()
        self.update()
        if self.mode == 'long':
            self.confirm()

    def rendered(self):
        if self.canvas:
            self.canvas.finish_text()
            return self.canvas.rendered()
        return crop_selection(self.image, self.selection_rect(), self.size())

    def save(self):
        if self.mode == 'photo' and not self.selection_locked and self.start is not None:
            self.save_selected.emit(self.rendered())

    def save_as(self):
        if self.mode == 'photo' and not self.selection_locked and self.start is not None:
            self.save_as_selected.emit(self.rendered())

    def pin(self):
        if self.mode == 'photo' and not self.selection_locked and self.start is not None:
            try:
                image = self.rendered()
            except ValueError:
                return
            self.pin_selected.emit(image)

    def beautify(self):
        if self.mode == 'photo' and not self.selection_locked and self.start is not None:
            try:
                image = self.rendered()
            except ValueError:
                return
            self.beautify_selected.emit(image)

    def confirm(self, keyboard=False):
        if self.selection_locked:
            return
        if self.start is None:
            return
        if self.mode == 'video':
            if self.selection_rect().width() >= 2 and self.selection_rect().height() >= 2:
                self.video_selected.emit(self.selection_rect())
            return
        if self.mode == 'long':
            if self.long_submitted:
                return
            if self.selection_rect().width() >= 80 and self.selection_rect().height() >= 80:
                self.long_submitted = True
                self.lock_selection()
                self.long_selected.emit(self.selection_rect())
            else:
                self.show_error('长截图请框选至少 80 × 80 的正文区域')
            return
        if keyboard and self.canvas and self.canvas.text_editor is not None:
            self.canvas.finish_text()
            self.setFocus()
            return
        try:
            image = self.rendered()
        except ValueError:
            return
        self.selected.emit(image)

    def _nudge_selection(self, dx, dy):
        r = self.selection_rect()
        nx = max(-r.left(), min(self.width() - r.right(), dx))
        ny = max(-r.top(), min(self.height() - r.bottom(), dy))
        if nx == 0 and ny == 0:
            return
        r.translate(nx, ny)
        self.start, self.end = r.topLeft(), r.bottomRight()
        self.refresh_canvas(reset=False)
        self.position_actions()
        self.update()

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key.Key_Escape:
            self.handle_escape()
            return
        if self.canvas and self.canvas.text_editor is not None:
            super().keyPressEvent(event)
            return

        # Pre-selection eyedropper controls
        if self.start is None:
            if key == Qt.Key.Key_Shift:
                self.color_format = 'rgb' if self.color_format == 'hex' else 'hex'
                self.update()
                return
            if key == Qt.Key.Key_C and not (mods & Qt.KeyboardModifier.ControlModifier):
                pos = self.hover_pos
                if pos is None:
                    local = QPointF(self.mapFromGlobal(QCursor.pos()))
                    if QRectF(self.rect()).contains(local):
                        pos = local
                color = self.sample_color(pos)
                if color is not None:
                    formatted = self.format_color(color)
                    QApplication.clipboard().setText(formatted)
                    self.color_picked.emit(formatted)
                return
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
                step = 10 if (mods & Qt.KeyboardModifier.ShiftModifier) else 1
                dx = (-step if key == Qt.Key.Key_Left else step if key == Qt.Key.Key_Right else 0)
                dy = (-step if key == Qt.Key.Key_Up else step if key == Qt.Key.Key_Down else 0)
                QCursor.setPos(QCursor.pos() + QPoint(dx, dy))
                local = QPointF(self.mapFromGlobal(QCursor.pos()))
                if QRectF(self.rect()).contains(local):
                    self.hover_pos = local
                    self.hovered_window = self._window_at(local)
                    self.update()
                return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.confirm(True)
            return
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.canvas:
            self.canvas.delete_selected()
            return
        if key == Qt.Key.Key_C and (mods & Qt.KeyboardModifier.ControlModifier) and self.start is not None:
            self.confirm(True)
            return

        if self.start is not None and not self.selection_locked:
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
                step = 10 if (mods & Qt.KeyboardModifier.ShiftModifier) else 1
                dx = (-step if key == Qt.Key.Key_Left else step if key == Qt.Key.Key_Right else 0)
                dy = (-step if key == Qt.Key.Key_Up else step if key == Qt.Key.Key_Down else 0)
                self._nudge_selection(dx, dy)
                return
            if self.mode == 'photo' and not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
                tool_keys = {
                    Qt.Key.Key_V: 'view',
                    Qt.Key.Key_B: 'pen',
                    Qt.Key.Key_P: 'pen',
                    Qt.Key.Key_H: 'highlighter',
                    Qt.Key.Key_R: 'rectangle',
                    Qt.Key.Key_A: 'arrow',
                    Qt.Key.Key_T: 'text',
                    Qt.Key.Key_N: 'step',
                    Qt.Key.Key_S: 'step',
                    Qt.Key.Key_M: 'mask',
                }
                if key in tool_keys:
                    self.set_tool(tool_keys[key])
                    return
                if key == Qt.Key.Key_F:
                    self.pin()
                    return
                if key == Qt.Key.Key_BracketLeft:
                    self.adjust_active_size(-1)
                    return
                if key == Qt.Key.Key_BracketRight:
                    self.adjust_active_size(1)
                    return
        super().keyPressEvent(event)
