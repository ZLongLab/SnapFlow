"""Scrollable long-image preview, full inline annotations, pin/beautify, copy and optional PNG save."""
import copy
import math
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QEvent, QPointF, Qt, QTimer, QSize
from PySide6.QtGui import QColor, QCursor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from .capture_canvas import AnnotationCanvas
from .capture_icons import line_icon
from .capture_markup import style_of
from .capture_style import build_capture_qss
from .capture_tools import COLOR_CHOICES, COLORS, normalize_tools
from .selection_overlay import PANEL_STYLE
from .windows_identity import apply_titlebar_theme


class LongCanvas(AnnotationCanvas):
    def __init__(self, image, scroll):
        super().__init__(image)
        self.scroll = scroll
        self.brush_position = None
        self.text_editor = None
        self.text_anchor = None
        self.editing_mark = None
        self.setMinimumSize(1, 1)
        self.setMouseTracking(True)
        self.zoom = 1.0

    def set_zoom(self, value=None, anchor=None):
        self.finish_text()
        fraction = self.scroll.verticalScrollBar().value() / max(1, self.height())
        width = max(1, self.scroll.viewport().width() - 32)
        self.zoom = min(1.0, width / max(1, self.image.width())) if value is None else max(.05, min(4.0, value))
        self.pan = QPointF()
        self.resize(
            math.ceil(self.image.width() * self.zoom) + 24,
            math.ceil(self.image.height() * self.zoom) + 24,
        )
        self.scroll.verticalScrollBar().setValue(round(fraction * self.height()))
        self.zoom_changed.emit(self.zoom)
        self.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self.scale() * 1.2 ** (event.angleDelta().y() / 120))
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event):
        if self.tool == 'text' and event.button() == Qt.MouseButton.LeftButton:
            self.finish_text()
            anchor = self.image_point(event.position())
            if anchor is not None:
                self.begin_text(anchor)
            return
        self.finish_text()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.brush_position = event.position()
        if self.drag_position is not None:
            delta = event.position() - self.drag_position
            bar = self.scroll.verticalScrollBar()
            bar.setValue(bar.value() - round(delta.y()))
            self.drag_position = event.position()
            self.update()
            return
        super().mouseMoveEvent(event)
        self.update()

    def leaveEvent(self, event):
        self.brush_position = None
        self.update()
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.text_editor and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.cancel_text()
                self.setFocus()
                return True
        return super().eventFilter(watched, event)

    def begin_text(self, anchor, text='', index=None):
        self.finish_text()
        self.text_anchor = QPointF(anchor)
        self.editing_mark = index
        editor = QLineEdit(self)
        editor.setMaxLength(500)
        editor.setText(text)
        editor.setPlaceholderText('输入文字，Enter 确认 · Esc 取消')
        editor.setStyleSheet(
            'QLineEdit { color:#e8f2fa; background:#172a3b; border:1px solid #60a5fa; '
            'border-radius:4px; padding:4px; selection-background-color:#2563eb; }'
        )
        font = editor.font()
        font.setPixelSize(max(12, round(self.text_size * self.scale())))
        editor.setFont(font)
        rect = self.image_rect()
        x = round(rect.x() + anchor.x() * self.scale())
        y = round(rect.y() + anchor.y() * self.scale())
        w = max(140, min(360, self.width() - max(0, x)))
        h = max(28, min(44, self.height()))
        editor.setGeometry(max(0, min(x, max(0, self.width() - w))), max(0, min(y, max(0, self.height() - h))), w, h)
        self.text_editor = editor
        editor.installEventFilter(self)
        editor.editingFinished.connect(self.finish_text)
        editor.show()
        editor.setFocus()
        editor.selectAll()

    def cancel_text(self):
        editor = self.text_editor
        if editor is None:
            return
        self.text_editor = None
        editor.removeEventFilter(self)
        editor.blockSignals(True)
        editor.hide()
        editor.deleteLater()
        self.text_anchor = self.editing_mark = None
        self.update()

    def finish_text(self):
        editor = self.text_editor
        if editor is None:
            return
        self.text_editor = None
        text = editor.text().strip()
        editor.removeEventFilter(self)
        editor.blockSignals(True)
        editor.hide()
        editor.deleteLater()
        if text:
            if self.editing_mark is None:
                mark = (
                    'text',
                    QPointF(self.text_anchor),
                    QPointF(self.text_anchor),
                    text,
                    self.color,
                    {'width': self.line_width, 'size': self.text_size},
                )
                self.append_mark(mark)
            elif self.editing_mark < len(self.marks):
                marks = list(self.marks)
                mark = list(marks[self.editing_mark])
                mark[3] = text
                marks[self.editing_mark] = tuple(mark)
                self.commit(marks)
        self.text_anchor = self.editing_mark = None
        self.update()

    def edit_text(self):
        if self.selected_index is not None and self.marks[self.selected_index][0] == 'text':
            mark = self.marks[self.selected_index]
            self.begin_text(mark[1], mark[3], self.selected_index)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.tool == 'mask' and self.brush_position is not None and self.image_point(self.brush_position) is not None:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            radius = self.brush_size * self.scale() / 2
            p.setPen(QPen(QColor('#172b32'), 3))
            p.drawEllipse(self.brush_position, radius, radius)
            p.setPen(QPen(QColor('white'), 1))
            p.drawEllipse(self.brush_position, radius, radius)
            p.end()


class LongImageEditor(QDialog):
    def __init__(self, image, controller, warning='', segments=1):
        super().__init__(None)
        self.controller = controller
        dark = getattr(getattr(controller, 'window', None), 'theme_name', 'light') == 'dark'
        icon_ink = '#cfe0f2' if dark else '#334155'
        self.preferences = normalize_tools(controller.tool_preferences)
        self.saved_path = self.saved_image = None
        self.fit_width = True
        self.setWindowTitle('长截图 · 标注与复制')
        self.resize(1020, 760)
        self.setMinimumSize(640, 460)
        self.setStyleSheet(build_capture_qss(dark))
        apply_titlebar_theme(self, dark=dark)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel('长截图')
        title.setObjectName('captureTitle')
        header.addWidget(title)
        meta = QLabel(f'{image.width()} × {image.height()} px · {segments} 段')
        meta.setObjectName('captureMeta')
        header.addWidget(meta)
        header.addStretch()
        fit = QPushButton('适应宽度')
        fit.clicked.connect(self.fit)
        header.addWidget(fit)
        actual = QPushButton('100%')
        actual.clicked.connect(self.actual)
        header.addWidget(actual)
        layout.addLayout(header)

        self.toolbar = QFrame()
        self.toolbar.setObjectName('selectionPanel')
        self.toolbar.setStyleSheet(PANEL_STYLE)
        tools = QHBoxLayout(self.toolbar)
        tools.setContentsMargins(9, 7, 9, 7)
        tools.setSpacing(4)
        self.tool_group = QButtonGroup(self)
        self.tool_buttons = {}
        for kind, title_tip, icon in [
            ('view', '浏览 · 拖动上下查看', 'cursor'),
            ('select', '选择 / 移动标注', 'cursor'),
            ('pen', '画笔 · 按住拖动自由绘画', 'pen'),
            ('highlighter', '荧光笔 · 半透明高亮标记', 'highlighter'),
            ('rectangle', '矩形', 'rectangle'),
            ('arrow', '箭头', 'arrow'),
            ('text', '文字 · 行内输入', 'text'),
            ('step', '序号 · 点击依次标注 ①②③', 'step'),
            ('mask', '马赛克', 'mask'),
        ]:
            b = QPushButton('浏览' if kind == 'view' else '')
            b.setCheckable(True)
            b.setFixedHeight(32)
            if kind != 'view':
                b.setIcon(line_icon(icon, '#edf5f0'))
                b.setIconSize(QSize(19, 19))
                b.setFixedWidth(32)
            b.setToolTip(title_tip)
            b.setAccessibleName(title_tip)
            b.clicked.connect(lambda checked=False, value=kind: self.set_tool(value))
            self.tool_group.addButton(b)
            self.tool_buttons[kind] = b
            tools.addWidget(b)

        self.color_group = QButtonGroup(self)
        self.color_buttons = []
        for color, cname in COLOR_CHOICES:
            b = QPushButton()
            b.setObjectName('colorChoice')
            b.setCheckable(True)
            b.setFixedSize(20, 20)
            b.setStyleSheet(f'QPushButton#colorChoice {{ background:{color}; }}')
            b.setToolTip(cname)
            b.setAccessibleName(cname)
            b.clicked.connect(lambda checked=False, value=color: self.style(color=value))
            self.color_group.addButton(b)
            self.color_buttons.append(b)
            tools.addWidget(b)

        self.option_groups = {}
        self.spins = {}
        for key, caption, low, high, value in [
            ('width', '线宽', 1, 16, 3),
            ('size', '字号', 12, 64, 22),
            ('brush', '笔刷', 4, 64, 12),
            ('block', '颗粒', 2, 32, 6),
        ]:
            group = QWidget()
            row = QHBoxLayout(group)
            row.setContentsMargins(4, 0, 0, 0)
            row.setSpacing(3)
            row.addWidget(QLabel(caption))
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(value)
            spin.setFixedWidth(50)
            spin.setAccessibleName(caption)
            spin.valueChanged.connect(lambda val, name=key: self.style(**{name: val}))
            row.addWidget(spin)
            tools.addWidget(group)
            self.option_groups[key] = group
            self.spins[key] = spin
        tools.addStretch()

        self.undo_button = QPushButton()
        self.redo_button = QPushButton()
        for b, icon, tip in [(self.undo_button, 'undo', '撤销 · Ctrl+Z'), (self.redo_button, 'redo', '重做 · Ctrl+Y')]:
            b.setIcon(line_icon(icon, '#edf5f0'))
            b.setIconSize(QSize(19, 19))
            b.setFixedSize(32, 32)
            b.setToolTip(tip)
            b.setAccessibleName(tip)
            tools.addWidget(b)
        layout.addWidget(self.toolbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.viewport().installEventFilter(self)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.canvas = LongCanvas(image, self.scroll)
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll, 1)

        self.canvas.changed.connect(self.refresh)
        self.canvas.selection_changed.connect(self.refresh)
        self.undo_button.clicked.connect(self.canvas.undo)
        self.redo_button.clicked.connect(self.canvas.redo)
        self.message = QLabel(warning)
        self.message.setObjectName('captureError')
        self.message.setWordWrap(True)
        self.message.setVisible(bool(warning))
        layout.addWidget(self.message)

        footer = QHBoxLayout()
        hint = QLabel('滚轮浏览长图 · Ctrl+滚轮缩放 · Ctrl+C 复制 · Ctrl+S 保存')
        hint.setObjectName('captureHint')
        footer.addWidget(hint)
        footer.addStretch()
        cancel = QPushButton('取消')
        cancel.setObjectName('cancelCapture')
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)

        self.pin_button = QPushButton('贴到屏幕')
        self.pin_button.setIcon(line_icon('pin', icon_ink))
        self.pin_button.clicked.connect(self.pin_capture)
        footer.addWidget(self.pin_button)

        self.beautify_button = QPushButton('美化套壳')
        self.beautify_button.setIcon(line_icon('sparkle', icon_ink))
        self.beautify_button.clicked.connect(self.beautify_capture)
        footer.addWidget(self.beautify_button)

        self.save_button = QPushButton('保存到桌面' if controller.is_desktop_destination() else '保存图片')
        self.save_button.setObjectName('saveCapture')
        self.save_button.clicked.connect(self.save)
        footer.addWidget(self.save_button)

        self.copy_button = QPushButton('完成 · 复制')
        self.copy_button.setObjectName('copyCapture')
        self.copy_button.setIcon(line_icon('copy', '#ffffff'))
        self.copy_button.setDefault(True)
        save_hist = controller.settings.get('save_copy_history', True) if isinstance(getattr(controller, 'settings', None), dict) else False
        self.copy_button.setToolTip(
            '复制到剪贴板，并在本机剪贴历史暂存最近 20 张（可在设置中关闭）'
            if save_hist
            else '仅复制到剪贴板，不写入磁盘文件'
        )
        self.copy_button.clicked.connect(self.copy)
        footer.addWidget(self.copy_button)
        layout.addLayout(footer)

        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self.copy_button.setDefault(True)
        for key, handler in [
            ('Ctrl+Z', self.canvas.undo),
            ('Ctrl+Y', self.canvas.redo),
            ('Ctrl+C', self.copy),
            ('Ctrl+S', self.save),
            ('Ctrl+Shift+S', self.save_as),
        ]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(handler)
        self.set_tool('view')
        QTimer.singleShot(0, self.fit)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'canvas') and self.fit_width:
            QTimer.singleShot(0, self.fit)

    def eventFilter(self, watched, event):
        if hasattr(self, 'canvas') and watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize and self.fit_width:
            QTimer.singleShot(0, self.fit)
        return super().eventFilter(watched, event)

    def fit(self):
        self.fit_width = True
        self.canvas.set_zoom()

    def actual(self):
        self.fit_width = False
        self.canvas.set_zoom(1.0)

    def set_tool(self, kind):
        self.canvas.finish_text()
        self.canvas.tool = kind
        self.canvas.selected_index = None
        if kind in self.tool_buttons:
            self.tool_buttons[kind].setChecked(True)
        self.canvas.setCursor(
            Qt.CursorShape.BlankCursor
            if kind == 'mask'
            else Qt.CursorShape.ArrowCursor
            if kind in ('view', 'select')
            else Qt.CursorShape.CrossCursor
        )
        self.refresh()

    def effective_tool(self):
        if self.canvas.tool == 'select' and self.canvas.selected_index is not None:
            return self.canvas.marks[self.canvas.selected_index][0]
        return self.canvas.tool

    def refresh(self):
        kind = self.effective_tool()
        values = dict(self.preferences.get(kind, {}))
        if self.canvas.selected_index is not None:
            mark = self.canvas.marks[self.canvas.selected_index]
            values.update(style_of(mark))
            values['color'] = mark[4]
        visible = {
            'pen': ('width',),
            'highlighter': ('width',),
            'rectangle': ('width',),
            'arrow': ('width',),
            'text': ('size',),
            'step': ('size',),
            'mask': ('brush', 'block'),
        }.get(kind, ())
        for key, group in self.option_groups.items():
            group.setVisible(key in visible)
        for key, spin in self.spins.items():
            if key in values:
                blocked = spin.blockSignals(True)
                spin.setValue(values[key])
                spin.blockSignals(blocked)
        color = values.get('color', '#e34f45')
        for b, choice in zip(self.color_buttons, COLORS):
            b.setVisible(kind in ('pen', 'highlighter', 'rectangle', 'arrow', 'text', 'step'))
            b.setChecked(choice == color)
        self.canvas.color = color
        self.canvas.line_width = self.spins['width'].value()
        self.canvas.text_size = self.spins['size'].value()
        self.canvas.brush_size = self.spins['brush'].value()
        self.canvas.mosaic_block = self.spins['block'].value()
        self.undo_button.setEnabled(bool(self.canvas.history))
        self.redo_button.setEnabled(bool(self.canvas.future))
        self.canvas.update()

    def style(self, **values):
        kind = self.effective_tool()
        if kind in self.preferences:
            self.preferences[kind].update({key: value for key, value in values.items() if key in self.preferences[kind]})
        self.canvas.apply_style(**values)
        self.controller.remember_tools(copy.deepcopy(self.preferences))
        self.refresh()

    def error(self, text):
        self.message.setText(text)
        self.message.show()

    def pin_capture(self):
        self.canvas.finish_text()
        if hasattr(self.controller, 'pin_image'):
            self.controller.pin_image(self.canvas.rendered())
            self.accept()

    def beautify_capture(self):
        self.canvas.finish_text()
        if hasattr(self.controller, 'beautify_image'):
            image = self.canvas.rendered()
            self.accept()
            self.controller.beautify_image(image)

    def copy(self):
        from .screen_capture import copy_image
        self.canvas.finish_text()
        image = self.canvas.rendered()
        try:
            copy_image(image)
        except Exception as exc:
            self.error('复制失败，可重试或保存：' + str(exc))
            return
        recorded = self.controller.record_copy_history(image) if hasattr(self.controller, 'record_copy_history') else False
        hint = '已同步暂存至本机剪贴历史（可在设置关闭）' if recorded else '未写入磁盘文件'
        self.controller.notify('长截图已复制', hint)
        self.accept()

    def save(self):
        from .screen_capture import copy_image, save_png
        self.canvas.finish_text()
        image = self.canvas.rendered()
        try:
            if self.saved_image is not None and image == self.saved_image and self.saved_path and self.saved_path.is_file():
                path = self.saved_path
            else:
                path = save_png(image, self.controller.settings['directory'])
                self.saved_image = image.copy()
                self.saved_path = path
            self.controller.last_saved = path
            if hasattr(self.controller, '_notify_window_refresh'):
                self.controller._notify_window_refresh()
        except Exception as exc:
            self.error('保存失败，可重试或仅复制：' + str(exc))
            return
        try:
            copy_image(image)
        except Exception as exc:
            self.error('长图已保存，复制失败，可重试：' + str(exc))
            return
        self.controller.notify('长截图已保存并复制', path.name)
        self.accept()

    def save_as(self):
        from .screen_capture import choose_save_image_path, copy_image, save_image_to_path
        self.canvas.finish_text()
        image = self.canvas.rendered()
        default_dir = Path(self.controller.settings['directory']).expanduser().resolve()
        default_name = default_dir / f"长截图_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        picked = choose_save_image_path(self, '另存为长截图', default_name)
        if not picked:
            return
        final_path, overwrite = picked
        try:
            path = save_image_to_path(image, final_path, overwrite=overwrite)
            self.saved_image = image.copy()
            self.saved_path = path
            self.controller.last_saved = path
            if hasattr(self.controller, '_notify_window_refresh'):
                self.controller._notify_window_refresh()
        except Exception as exc:
            self.error('另存为失败：' + str(exc))
            return
        try:
            copy_image(image)
        except Exception as exc:
            self.error(f'长图已保存到 {path}。复制失败，可点击复制重试。{exc}')
            self.controller.notify('长截图已另存为，复制失败', str(path))
            return
        self.controller.notify('长截图已另存为并复制', path.name)
        self.accept()
