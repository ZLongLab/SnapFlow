"""Local screen selection, editable annotations, PNG export and tray lifecycle."""
import json
import math
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QMimeData,
    QPointF,
    QRectF,
    QSize,
    QStandardPaths,
    QTimer,
    QUrl,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .capture_focus import foreground_window, restore_foreground, visible_window_rects_by_screen, window_owner
from .capture_hotkey import GlobalHotkey, parse_hotkey
from .capture_hud import CaptureHistory, ToastHud
from .capture_icons import line_icon
from .capture_markup import draw_annotation, render_annotations
from .capture_pixels import crop_selection
from .capture_style import CAPTURE_QSS, build_capture_qss
from .ui_flow import FlowLayout
from .windows_identity import ICON_PATH, apply_dark_titlebar, apply_titlebar_theme


def save_png(image, directory, now=None):
    if image.isNull():
        raise ValueError('截图内容为空')
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, 'PNG'):
        raise OSError('无法编码 PNG 图片')
    buffer.close()
    payload = bytes(data)
    stamp = (now or datetime.now()).strftime('%Y%m%d_%H%M%S')
    for index in range(10000):
        target = directory / f'截图_{stamp}{"_" + str(index) if index else ""}.png'
        try:
            handle = target.open('xb')
        except FileExistsError:
            continue
        try:
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return target
    raise OSError('同一时间的截图文件过多，请更换保存目录')


def resolve_save_image_path(target_path, selected_filter=''):
    """Determine exact output path and format without silently stripping custom suffixes."""
    target = Path(target_path).expanduser().resolve()
    ext = target.suffix.lower()
    if ext == '.png':
        return target, 'PNG'
    if ext in ('.jpg', '.jpeg'):
        return target, 'JPG'
    wants_jpg = 'jpg' in str(selected_filter or '').lower() or 'jpeg' in str(selected_filter or '').lower()
    suffix = '.jpg' if wants_jpg else '.png'
    fmt = 'JPG' if wants_jpg else 'PNG'
    # Append rather than replace suffix so 'example.backup' becomes 'example.backup.png'
    # instead of colliding with an existing 'example.png'.
    return target.with_name(target.name + suffix), fmt


def choose_save_image_path(parent, title, default_path):
    """Return the final path and whether the user approved replacing that file."""
    chosen, selected_filter = QFileDialog.getSaveFileName(
        parent,
        title,
        str(default_path),
        'PNG 图片 (*.png);;JPEG 图片 (*.jpg *.jpeg)',
        options=QFileDialog.Option.DontConfirmOverwrite,
    )
    if not chosen:
        return None
    final_path, _ = resolve_save_image_path(chosen, selected_filter)
    overwrite = final_path.exists()
    if overwrite:
        reply = QMessageBox.question(
            parent,
            '确认覆盖文件',
            f'目标文件已存在，是否覆盖？\n{final_path}',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return None
    return final_path, overwrite


def save_image_to_path(image, target_path, *, overwrite=False, selected_filter=''):
    if image.isNull():
        raise ValueError('截图内容为空')
    target, fmt = resolve_save_image_path(target_path, selected_filter)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    ok = image.save(buffer, fmt, 95 if fmt == 'JPG' else -1)
    buffer.close()
    if not ok:
        raise OSError(f'无法编码 {fmt} 图片')
    payload = bytes(data)
    if not overwrite:
        try:
            handle = target.open('xb')
        except FileExistsError as exc:
            raise FileExistsError(f'文件已存在：{target}') from exc
        try:
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return target
    tmp = target.with_name(f'.{target.name}.{uuid.uuid4().hex[:8]}.tmp')
    try:
        with tmp.open('wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return target


def copy_image(image):
    clipboard = QApplication.clipboard()
    for attempt in range(4):
        clipboard.setImage(image)
        actual = clipboard.image()
        if not actual.isNull() and actual.size() == image.size():
            return
        if attempt < 3:
            time.sleep(0.03)
            QApplication.processEvents()
    raise OSError('剪贴板写入失败，请关闭占用剪贴板的程序后重试')


_OFFSCREEN_CLIPBOARD_HOOKED = False


def _ensure_offscreen_clipboard_cleanup():
    """Clear offscreen QPlatformClipboard before Python/Shiboken teardown to avoid QMimeData dtor crash."""
    global _OFFSCREEN_CLIPBOARD_HOOKED
    if _OFFSCREEN_CLIPBOARD_HOOKED or QApplication.platformName() != 'offscreen':
        return
    import atexit

    def _clear_offscreen_clipboard():
        inst = QApplication.instance()
        if inst is not None:
            try:
                inst.clipboard().clear()
            except Exception:
                pass

    atexit.register(_clear_offscreen_clipboard)
    _OFFSCREEN_CLIPBOARD_HOOKED = True


def copy_file_to_clipboard(path):
    target = Path(path).resolve()
    if not target.is_file():
        raise OSError('文件不存在，无法复制到剪贴板')
    _ensure_offscreen_clipboard_cleanup()
    url = QUrl.fromLocalFile(str(target))
    clipboard = QApplication.clipboard()
    for attempt in range(4):
        mime = QMimeData()
        mime.setUrls([url])
        clipboard.setMimeData(mime)
        current = clipboard.mimeData()
        if current is not None and any(u.toLocalFile() for u in current.urls()):
            return
        if attempt < 3:
            time.sleep(0.03)
            QApplication.processEvents()
    raise OSError('无法将文件写入剪贴板，请稍后重试')


from .selection_overlay import SelectionOverlay
from .capture_canvas import AnnotationCanvas
from .capture_tools import COLOR_CHOICES, load_tools, normalize_tools, save_tools


class ColorDot(QPushButton):
    def __init__(self, color, title, parent):
        super().__init__('', parent)
        self.color = color
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setFixedSize(28, 32)
        self.setToolTip(title)
        self.setAccessibleName(title)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        p.setPen(QPen(QColor(148, 163, 184, 90), 1))
        p.setBrush(QColor(self.color))
        p.drawEllipse(center, 8, 8)
        if self.isChecked() or self.hasFocus():
            ring = QColor('#3b82f6') if self.color.lower() in ('#f8fafc', '#1e293b') else QColor(self.color)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(ring, 2))
            p.drawEllipse(center, 12, 12)
        p.end()


class PathLabel(QLabel):
    def __init__(self, path):
        super().__init__()
        self.full_text = '保存到 ' + str(path)
        self.setToolTip(str(path))
        self.setObjectName('capturePath')
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(80)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideMiddle, self.width()))


class CaptureEditor(QDialog):
    def __init__(self, image, controller):
        super().__init__(None)
        self.controller = controller
        self.destination = Path(controller.settings['directory']).resolve()
        dark = getattr(getattr(controller, 'window', None), 'theme_name', 'light') == 'dark'
        self.setWindowTitle('截图编辑 · SnapFlow')
        width = max(860, min(1180, image.width() + 96))
        height = max(500, min(850, round(image.height() * min((width - 64) / max(1, image.width()), 1)) + 280))
        self.resize(width, height)
        self.setMinimumSize(560, 400)
        self.setStyleSheet(build_capture_qss(dark))
        apply_titlebar_theme(self, dark=dark)

        icon_ink = '#cfe0f2' if dark else '#334155'
        accent_ink = '#60a5fa' if dark else '#2563eb'

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName('captureHeader')
        head = QHBoxLayout(header)
        head.setContentsMargins(22, 14, 22, 12)
        head.setSpacing(14)
        icon = QLabel()
        icon.setPixmap(line_icon('capture', accent_ink).pixmap(28, 28))
        head.addWidget(icon)
        heading = QVBoxLayout()
        heading.setSpacing(3)
        title = QLabel('截图编辑')
        title.setObjectName('captureTitle')
        heading.addWidget(title)
        meta = QLabel(f'已就绪  ·  {image.width()} × {image.height()} 像素  ·  PNG')
        meta.setObjectName('captureMeta')
        heading.addWidget(meta)
        head.addLayout(heading)
        head.addStretch()
        badge = QLabel('本地标注')
        badge.setObjectName('captureBadge')
        head.addWidget(badge)
        layout.addWidget(header)

        self.toolbar_frame = QWidget()
        toolbar = FlowLayout(self.toolbar_frame, 6)
        toolbar.setContentsMargins(20, 8, 20, 8)
        layout.addWidget(self.toolbar_frame)
        self.tools = QComboBox(self)
        self.tools.hide()
        group = QFrame()
        group.setObjectName('toolGroup')
        group_layout = QHBoxLayout(group)
        group_layout.setContentsMargins(4, 4, 4, 4)
        group_layout.setSpacing(3)
        self.tool_buttons = {}
        self.tool_group = QButtonGroup(self)
        for index, (name, key, icon_name) in enumerate([
            ('查看', 'view', 'cursor'),
            ('选择', 'select', 'cursor'),
            ('画笔', 'pen', 'pen'),
            ('荧光笔', 'highlighter', 'highlighter'),
            ('矩形', 'rectangle', 'rectangle'),
            ('箭头', 'arrow', 'arrow'),
            ('文字', 'text', 'text'),
            ('序号', 'step', 'step'),
            ('马赛克', 'mask', 'mask'),
        ]):
            self.tools.addItem(name, key)
            button = QPushButton(name)
            button.setObjectName('tool')
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setIcon(line_icon(icon_name, icon_ink))
            button.setIconSize(QSize(17, 17))
            button.setToolTip(name + '工具')
            self.tool_group.addButton(button, index)
            button.clicked.connect(lambda checked=False, i=index: self.tools.setCurrentIndex(i))
            self.tool_buttons[key] = button
            group_layout.addWidget(button)
        toolbar.addWidget(group)

        options = QWidget()
        option_row = QHBoxLayout(options)
        option_row.setContentsMargins(0, 0, 0, 0)
        option_row.setSpacing(4)
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet('color:#33435e;' if dark else 'color:#dce5f2;')
        divider.setFixedHeight(26)
        option_row.addWidget(divider)
        self.colors = QComboBox(self)
        self.colors.hide()
        self.color_group = QButtonGroup(self)
        self.color_buttons = []
        for index, (color, name) in enumerate(COLOR_CHOICES):
            self.colors.addItem(name, color)
            dot = ColorDot(color, name, self)
            self.color_group.addButton(dot, index)
            dot.clicked.connect(lambda checked=False, i=index: self.colors.setCurrentIndex(i))
            self.color_buttons.append(dot)
            option_row.addWidget(dot)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 16)
        self.width_spin.setValue(3)
        self.width_spin.setPrefix('线 ')
        self.size_spin = QSpinBox()
        self.size_spin.setRange(12, 96)
        self.size_spin.setValue(22)
        self.size_spin.setPrefix('字 ')
        for spin in (self.width_spin, self.size_spin):
            spin.setFixedWidth(70)
            option_row.addWidget(spin)
        toolbar.addWidget(options)

        zoom_group = QWidget()
        zoom_row = QHBoxLayout(zoom_group)
        zoom_row.setContentsMargins(0, 0, 0, 0)
        zoom_row.setSpacing(4)
        self.zoom_label = QLabel('100%')
        zoom_row.addWidget(self.zoom_label)
        self.fit_button = QPushButton('适应')
        self.actual_button = QPushButton('100%')
        for zoom_button in (self.fit_button, self.actual_button):
            zoom_button.setAutoDefault(False)
            zoom_button.setObjectName('zoomButton')
            zoom_row.addWidget(zoom_button)
        self.undo_button = QPushButton('撤销')
        self.undo_button.setEnabled(False)
        self.undo_button.setAutoDefault(False)
        self.undo_button.setIcon(line_icon('undo', icon_ink))
        self.undo_button.setToolTip('撤销上一个标注 · Ctrl+Z')
        zoom_row.addWidget(self.undo_button)
        self.redo_button = QPushButton('重做')
        self.redo_button.setAutoDefault(False)
        self.redo_button.setEnabled(False)
        zoom_row.addWidget(self.redo_button)
        toolbar.addWidget(zoom_group)

        edit_group = QWidget()
        self.edit_group = edit_group
        edit_row = QHBoxLayout(edit_group)
        edit_row.setContentsMargins(0, 0, 0, 0)
        edit_row.setSpacing(4)
        self.text_button = QPushButton('改文字')
        self.delete_button = QPushButton('删除标注')
        for button in (self.text_button, self.delete_button):
            button.setAutoDefault(False)
            button.setEnabled(False)
            edit_row.addWidget(button)
        toolbar.addWidget(edit_group)

        self.canvas = AnnotationCanvas(image)
        body = QHBoxLayout()
        body.setContentsMargins(20, 0, 20, 0)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.viewport().setAutoFillBackground(False)
        scroll.setWidget(self.canvas)
        body.addWidget(scroll)
        layout.addLayout(body, 1)

        self.tools.currentIndexChanged.connect(self.set_tool)
        self.colors.currentIndexChanged.connect(self.set_color)
        self.undo_button.clicked.connect(self.canvas.undo)
        self.redo_button.clicked.connect(self.canvas.redo)
        self.delete_button.clicked.connect(self.canvas.delete_selected)
        self.text_button.clicked.connect(self.canvas.edit_text)
        self.canvas.selection_changed.connect(self.selection_changed)
        self.width_spin.valueChanged.connect(lambda value: self.canvas.apply_style(width=value))
        self.size_spin.valueChanged.connect(lambda value: self.canvas.apply_style(size=value))
        self.canvas.changed.connect(self.content_changed)
        self.canvas.zoom_changed.connect(lambda value: self.zoom_label.setText(f'{value:.0%}'))
        self.canvas.setToolTip('滚轮缩放；查看工具拖动平移；标注时按住鼠标中键平移')
        self.fit_button.clicked.connect(lambda: self.canvas.set_zoom())
        self.actual_button.clicked.connect(lambda: self.canvas.set_zoom(1.0))
        self.saved_image = None
        self.saved_path = None

        for seq, handler in (
            ('Ctrl+Z', self.canvas.undo),
            ('Ctrl+Y', self.canvas.redo),
            ('Ctrl+C', self.copy),
            ('Ctrl+S', self.save),
            ('Ctrl+Shift+S', self.save_as),
        ):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(handler)
        self.set_tool()
        self.set_color()

        footer = QHBoxLayout()
        footer.setContentsMargins(22, 14, 22, 16)
        footer.setSpacing(10)
        destination = QVBoxLayout()
        destination.setSpacing(5)
        self.path_label = PathLabel(controller.settings['directory'])
        self.path_label.setParent(self)
        self.path_label.hide()
        hint = QLabel('Enter / Ctrl+C 复制  ·  Ctrl+S 保存  ·  Ctrl+Shift+S 另存为  ·  Esc 取消')
        hint.setObjectName('captureHint')
        destination.addWidget(hint)
        footer.addLayout(destination, 1)

        desktop = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)).resolve()
        save_title = '保存到桌面' if Path(controller.settings['directory']).resolve() == desktop else '保存图片'
        self.pin_button = QPushButton('贴到屏幕')
        self.pin_button.setAutoDefault(False)
        self.pin_button.setIcon(line_icon('pin', icon_ink))
        self.beautify_button = QPushButton('美化套壳')
        self.beautify_button.setAutoDefault(False)
        self.beautify_button.setIcon(line_icon('sparkle', icon_ink))
        self.save_button = QPushButton(save_title)
        self.save_button.setObjectName('saveCapture')
        self.save_button.setAutoDefault(False)
        self.save_button.setToolTip('保存 PNG 到 ' + controller.settings['directory'] + ' (Ctrl+S)')
        self.copy_button = QPushButton('仅复制')
        self.copy_button.setObjectName('copyCapture')
        self.copy_button.setIcon(line_icon('copy', '#ffffff'))
        self.copy_button.setDefault(True)
        save_hist = controller.settings.get('save_copy_history', True) if isinstance(getattr(controller, 'settings', None), dict) else False
        self.copy_button.setToolTip(
            '复制到剪贴板，并在本机剪贴历史暂存最近 20 张（可在设置中关闭）'
            if save_hist
            else '仅复制到剪贴板，不写入磁盘文件'
        )
        cancel = QPushButton('取消')
        cancel.setObjectName('cancelCapture')
        cancel.setAutoDefault(False)
        self.pin_button.clicked.connect(self.pin_capture)
        self.beautify_button.clicked.connect(self.beautify_capture)
        self.save_button.clicked.connect(self.save)
        self.copy_button.clicked.connect(self.copy)
        cancel.clicked.connect(self.reject)
        for widget in (cancel, self.pin_button, self.beautify_button, self.save_button, self.copy_button):
            footer.addWidget(widget)

        self.message = QLabel()
        self.message.setObjectName('captureError')
        self.message.setWordWrap(True)
        self.message.hide()
        self.message_container = QHBoxLayout()
        self.message_container.setContentsMargins(20, 10, 20, 0)
        self.message_container.addWidget(self.message)
        layout.addLayout(self.message_container)
        layout.addLayout(footer)
        self.copy_button.setFocus()

    def set_tool(self, *_):
        self.canvas.start = self.canvas.end = None
        self.canvas.tool = self.tools.currentData()
        if self.canvas.tool != 'select':
            self.canvas.selected_index = None
            self.selection_changed()
        for key, button in self.tool_buttons.items():
            button.setChecked(key == self.canvas.tool)
        self.canvas.update()

    def set_color(self, *_):
        self.canvas.apply_style(color=self.colors.currentData())
        for index, button in enumerate(self.color_buttons):
            button.setChecked(index == self.colors.currentIndex())
            button.update()

    def selection_changed(self):
        index = self.canvas.selected_index
        self.edit_group.setVisible(index is not None)
        self.delete_button.setEnabled(index is not None)
        self.text_button.setEnabled(index is not None and self.canvas.marks[index][0] == 'text')
        if index is not None:
            from .capture_markup import style_of
            mark = self.canvas.marks[index]
            style = style_of(mark)
            for spin, value in ((self.width_spin, style.get('width', 3)), (self.size_spin, style.get('size', 22))):
                blocked = spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(blocked)
            self.canvas.line_width = self.width_spin.value()
            self.canvas.text_size = self.size_spin.value()
            self.canvas.color = mark[4]
            blocked = self.colors.blockSignals(True)
            self.colors.setCurrentIndex(self.colors.findData(mark[4]))
            self.colors.blockSignals(blocked)
            for i, button in enumerate(self.color_buttons):
                button.setChecked(i == self.colors.currentIndex())
                button.update()

    def content_changed(self):
        self.undo_button.setEnabled(bool(self.canvas.marks) or bool(self.canvas.history))
        self.redo_button.setEnabled(bool(self.canvas.future))
        self.save_button.setEnabled(True)
        self.message.hide()

    def show_error(self, text):
        self.message.setText(text)
        self.message.show()

    def save(self):
        image = self.canvas.rendered()
        try:
            if self.saved_image is not None and image == self.saved_image and self.saved_path and self.saved_path.is_file():
                path = self.saved_path
            else:
                path = save_png(image, self.destination)
                self.saved_image = image.copy()
                self.saved_path = path
        except Exception as exc:
            self.show_error('保存失败，可重试或仅复制：' + str(exc))
            return
        self.controller.last_saved = path
        if hasattr(self.controller, '_notify_window_refresh'):
            self.controller._notify_window_refresh()
        try:
            copy_image(image)
        except Exception as exc:
            self.show_error(f'文件已保存到 {path}；{exc}')
            self.save_button.setEnabled(True)
            self.controller.notify('截图已保存，但复制失败', str(path))
            return
        self.controller.notify('截图已保存并复制', str(path))
        self.accept()

    def save_as(self):
        image = self.canvas.rendered()
        default_name = self.destination / f"截图_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        picked = choose_save_image_path(self, '另存为图片', default_name)
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
            self.show_error('另存为失败：' + str(exc))
            return
        try:
            copy_image(image)
        except Exception as exc:
            self.show_error(f'图片已保存到 {path}。复制失败，可点击复制重试。{exc}')
            self.controller.notify('截图已另存为，复制失败', str(path))
            return
        self.controller.notify('截图已另存为并复制', str(path))
        self.accept()

    def copy(self):
        image = self.canvas.rendered()
        try:
            copy_image(image)
        except Exception as exc:
            self.show_error(str(exc))
            return
        recorded = self.controller.record_copy_history(image) if hasattr(self.controller, 'record_copy_history') else False
        hint = '已同步暂存至本机剪贴历史（可在设置关闭）' if recorded else '未写入磁盘文件'
        self.controller.notify('截图已复制', hint)
        self.accept()

    def pin_capture(self):
        if hasattr(self.controller, 'pin_image'):
            self.controller.pin_image(self.canvas.rendered())
            self.accept()

    def beautify_capture(self):
        if hasattr(self.controller, 'beautify_image'):
            image = self.canvas.rendered()
            self.accept()
            self.controller.beautify_image(image)


def _capture_dialog_qss(dark: bool) -> str:
    if dark:
        return """
        QDialog { background:#131926; color:#eef5fc; font-family:'Microsoft YaHei UI'; font-size:13px; }
        QLabel { color:#cbd9ea; background:transparent; }
        QLineEdit { background:#1d2638; color:#eef5fc; border:1px solid #32425e; border-radius:10px; padding:9px 12px; selection-background-color:#2563eb; }
        QLineEdit:focus { border-color:#60a5fa; }
        QPushButton { background:#232e44; color:#e4eff9; border:1px solid #32425e; border-radius:10px; padding:8px 15px; font-weight:500; }
        QPushButton:hover { background:#2b3954; border-color:#60a5fa; }
        QPushButton:default { background:#2563eb; border-color:#3b82f6; color:#ffffff; font-weight:600; }
        QPushButton:default:hover { background:#3b82f6; }
        """
    return """
    QDialog { background:#f4f7fb; color:#0f172a; font-family:'Microsoft YaHei UI'; font-size:13px; }
    QLabel { color:#475569; background:transparent; }
    QLineEdit { background:#ffffff; color:#0f172a; border:1px solid #d5e0ee; border-radius:10px; padding:9px 12px; selection-background-color:#2563eb; }
    QLineEdit:focus { border-color:#3b82f6; }
    QPushButton { background:#ffffff; color:#1e293b; border:1px solid #d5e0ee; border-radius:10px; padding:8px 15px; font-weight:500; }
    QPushButton:hover { background:#eff6ff; border-color:#60a5fa; }
    QPushButton:default { background:#2563eb; border-color:#2563eb; color:#ffffff; font-weight:600; }
    QPushButton:default:hover { background:#3b82f6; }
    """


class CaptureSettingsDialog(QDialog):
    """Compatibility wrapper for capture-only settings; UI opens unified SettingsDialog."""

    def __init__(self, controller):
        super().__init__(controller.window)
        self.controller = controller
        dark = getattr(controller.window, 'theme_name', 'light') == 'dark'
        self.setWindowTitle('截图设置 · SnapFlow')
        self.resize(620, 300)
        self.setStyleSheet(_capture_dialog_qss(dark))
        apply_titlebar_theme(self, dark=dark)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        from .settings_dialog import HotkeyRecorderEdit
        self.hotkey = HotkeyRecorderEdit(controller.settings['hotkey'])
        self.directory = QLineEdit(controller.settings['directory'])
        directory_row = QHBoxLayout()
        directory_row.addWidget(self.directory)
        choose = QPushButton('选择文件夹')
        directory_row.addWidget(choose)
        choose.clicked.connect(self.choose)
        form.addRow('截图快捷键', self.hotkey)
        form.addRow('保存到', directory_row)
        layout.addLayout(form)
        description = QLabel('点击快捷键输入框直接按下组合键（如 Alt+S）。关闭主窗口后截图功能在托盘运行；退出程序后快捷键释放。')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose(self):
        path = QFileDialog.getExistingDirectory(self, '选择截图保存目录', self.directory.text())
        if path:
            self.directory.setText(path)

    def save(self):
        try:
            self.controller.configure(self.hotkey.text(), self.directory.text())
        except Exception as exc:
            self.error.setText(str(exc))
            return
        self.accept()


def _tray_menu_qss(dark: bool) -> str:
    if dark:
        return """
        QMenu {
            background-color:#1c2537; color:#e6eef8; border:1px solid #32425e;
            border-radius:12px; padding:6px; font-family:'Microsoft YaHei UI'; font-size:13px;
        }
        QMenu::item { padding:7px 14px 7px 10px; border-radius:8px; margin:1px 2px; }
        QMenu::item:selected { background-color:#283752; color:#ffffff; }
        QMenu::item:disabled { color:#64748b; }
        QMenu::separator { height:1px; background:#2b3850; margin:5px 8px; }
        """
    return """
    QMenu {
        background-color:#ffffff; color:#1e293b; border:1px solid #d5e0ee;
        border-radius:12px; padding:6px; font-family:'Microsoft YaHei UI'; font-size:13px;
    }
    QMenu::item { padding:7px 14px 7px 10px; border-radius:8px; margin:1px 2px; }
    QMenu::item:selected { background-color:#eff6ff; color:#2563eb; }
    QMenu::item:disabled { color:#94a3b8; }
    QMenu::separator { height:1px; background:#e2e8f0; margin:5px 8px; }
    """


class CaptureController:
    def __init__(self, window, activate=True):
        self.window = window
        self.app = QApplication.instance()
        self.path = window.home / 'screenshot.json'
        self.tools_path = window.home / 'capture-tools.json'
        self.tool_preferences = load_tools(self.tools_path)
        self.history = CaptureHistory(window.home, limit=20)
        self.hud = ToastHud()
        self._tray_close_notified = False
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        self.settings = {
            'hotkey': 'Alt+S',
            'directory': desktop or str(Path.home() / 'Desktop'),
            'system_notifications': False,
            'tray_click_action': 'gallery',
            'skip_video_countdown': False,
            'save_copy_history': True,
        }
        try:
            if self.path.exists():
                saved = json.loads(self.path.read_text(encoding='utf-8'))
                hotkey, _, _ = parse_hotkey(saved['hotkey'])
                directory = saved['directory']
                if not isinstance(directory, str) or not Path(directory).is_absolute():
                    raise ValueError('保存目录需要完整路径')
                self.settings.update({
                    'hotkey': hotkey,
                    'directory': directory,
                    'system_notifications': bool(saved.get('system_notifications', False)),
                    'tray_click_action': saved.get('tray_click_action') if saved.get('tray_click_action') in ('gallery', 'capture') else 'gallery',
                    'skip_video_countdown': bool(saved.get('skip_video_countdown', False)),
                    'save_copy_history': bool(saved.get('save_copy_history', True)),
                })
        except Exception as exc:
            window.statusBar().showMessage('截图设置读取失败，使用默认设置：' + str(exc))
        self.update_entry()
        self.shortcut_frame = None
        self.shortcut_expiry = QTimer(window)
        self.shortcut_expiry.setSingleShot(True)
        self.shortcut_expiry.timeout.connect(self.clear_shortcut_frame)
        self.hotkey = GlobalHotkey(
            self.app,
            lambda: self.begin(from_hotkey=True),
            self.freeze_shortcut_frame,
            self.clear_shortcut_frame,
        )
        self.overlays = []
        self.editor = None
        self.capturing = False
        self.restore_main = False
        self.initial_mode = 'photo'
        self.pins = []
        self.pin_clear = None
        self.exiting = False
        self.exit_pending = False
        self.stopped = False
        self.last_saved = None
        self.from_hotkey = False
        self.previous_foreground = None
        self.recording = None
        self.record_controls = None
        self.record_outline = None
        self.record_region_global = None
        self.video_stop = None
        self.last_video = None
        self.video_audio_mode = 'silent'
        self.long_capture = None
        self.long_stop = None
        self.video_countdown = QTimer(window)
        self.video_countdown.setInterval(1000)
        self.video_countdown.timeout.connect(self.countdown_video)
        self.tray = None
        self.tray_menu = None
        self.act_capture = self.act_long = self.act_video = self.act_pin_clip = None
        self.act_panel = self.act_settings = self.act_startup = self.act_folder = None
        self.act_last_img = self.act_last_vid = self.act_exit = None
        self._tray_recent_sep = None
        if activate:
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.tray = QSystemTrayIcon(QIcon(str(ICON_PATH)), window)
                self.tray.setToolTip('SnapFlow')
                menu = self._build_tray_menu()
                self.tray.setContextMenu(menu)
                self.tray.activated.connect(self._on_tray_activated)
                self.tray.show()
                self.app.setQuitOnLastWindowClosed(False)
            try:
                self.hotkey.commit(self.hotkey.prepare(self.settings['hotkey']))
            except ValueError as exc:
                window.statusBar().showMessage(str(exc))
                QTimer.singleShot(500, lambda message=str(exc): self.notify('截图快捷键未启用', message, error=True))

        self.update_entry()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.begin()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.settings.get('tray_click_action') == 'capture':
                self.begin()
            else:
                self.show_main()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_main()

    def configure(
        self,
        hotkey,
        directory,
        *,
        system_notifications=None,
        tray_click_action=None,
        skip_video_countdown=None,
        save_copy_history=None,
    ):
        if self.long_capture and not self.long_capture.done:
            raise ValueError('请先完成或取消当前长截图')
        if self.recording and not self.recording.done:
            raise ValueError('请先完成或取消当前录制，再修改截图设置')
        path = Path(directory).expanduser()
        if not directory.strip() or not path.is_absolute():
            raise ValueError('请填写完整的截图保存目录')
        if path.exists() and not path.is_dir():
            raise ValueError('保存位置必须是文件夹')
        canonical, _, _ = parse_hotkey(hotkey)
        prepared = None if self.hotkey.ident is not None and canonical == self.hotkey.text else self.hotkey.prepare(canonical)
        data = {
            'hotkey': canonical,
            'directory': str(path.resolve()),
            'system_notifications': self.settings.get('system_notifications', False) if system_notifications is None else bool(system_notifications),
            'tray_click_action': self.settings.get('tray_click_action', 'gallery') if tray_click_action is None else ('capture' if tray_click_action == 'capture' else 'gallery'),
            'skip_video_countdown': self.settings.get('skip_video_countdown', False) if skip_video_countdown is None else bool(skip_video_countdown),
            'save_copy_history': self.settings.get('save_copy_history', True) if save_copy_history is None else bool(save_copy_history),
        }
        try:
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.path)
        except Exception:
            if prepared:
                self.hotkey.rollback(prepared)
            raise
        if prepared:
            self.hotkey.commit(prepared)
        self.settings = data
        self.update_entry()
        if self.tray:
            self.tray.setToolTip('SnapFlow')

    def _build_tray_menu(self):
        menu = QMenu(self.window)
        menu.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Popup | Qt.WindowType.NoDropShadowWindowHint)
        menu.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.tray_menu = menu
        self.act_capture = menu.addAction('框选截图', self.begin)
        self.act_long = menu.addAction('滚动长截图', lambda: self.begin(mode='long'))
        self.act_video = menu.addAction('区域录屏', lambda: self.begin(mode='video'))
        self.act_pin_clip = menu.addAction('贴图剪贴板图片', self.pin_clipboard)
        self.video_stop = menu.addAction('停止视频录制', self.stop_recording)
        self.video_stop.setEnabled(False)
        self.long_stop = menu.addAction('结束长截图', self.finish_long)
        self.long_stop.setEnabled(False)
        self.pin_clear = menu.addAction('关闭全部贴图', self.close_all_pins)
        self.pin_clear.setEnabled(False)
        menu.addSeparator()
        self.act_panel = menu.addAction('打开 SnapFlow 画廊', self.show_main)
        self.act_settings = menu.addAction('设置与快捷键', self.show_settings)
        self.act_folder = menu.addAction('打开保存目录', self.open_directory)
        self._tray_recent_sep = menu.addSeparator()
        self.act_last_img = menu.addAction('打开最近保存的截图', self.open_last)
        self.act_last_vid = menu.addAction('打开最近保存的视频', self.open_last_video)
        menu.addSeparator()
        self.act_exit = menu.addAction('退出 SnapFlow', self.exit)
        menu.aboutToShow.connect(self._prepare_tray_menu)
        self._prepare_tray_menu()
        return menu

    def _prepare_tray_menu(self):
        menu = self.tray_menu
        if menu is None:
            return
        dark = getattr(self.window, 'theme_name', 'light') == 'dark'
        menu.setStyleSheet(_tray_menu_qss(dark))
        ink = '#cbd9ea' if dark else '#334155'
        accent = '#60a5fa' if dark else '#2563eb'
        if self.act_capture:
            self.act_capture.setText(f"框选截图  {self.settings['hotkey']}")
            self.act_capture.setIcon(line_icon('capture', accent))
        if self.act_long:
            self.act_long.setIcon(line_icon('scroll', ink))
        if self.act_video:
            self.act_video.setIcon(line_icon('video', ink))
        if self.act_pin_clip:
            self.act_pin_clip.setIcon(line_icon('pin', ink))
        recording_active = bool(getattr(self, 'recording', None) and not self.recording.done)
        long_active = bool(getattr(self, 'long_capture', None) and not self.long_capture.done)
        has_pins = bool(getattr(self, 'pins', None))
        if self.video_stop:
            self.video_stop.setEnabled(recording_active)
            self.video_stop.setVisible(recording_active)
            self.video_stop.setIcon(line_icon('video', '#ef4444'))
        if self.long_stop:
            self.long_stop.setEnabled(long_active)
            self.long_stop.setVisible(long_active)
            self.long_stop.setIcon(line_icon('scroll', '#10b981'))
        if self.pin_clear:
            self.pin_clear.setEnabled(has_pins)
            self.pin_clear.setVisible(has_pins)
            self.pin_clear.setText(f'关闭全部贴图 ({len(self.pins)})' if has_pins else '关闭全部贴图')
            self.pin_clear.setIcon(line_icon('pin', ink))
        if self.act_panel:
            self.act_panel.setIcon(line_icon('open', ink))
        if self.act_settings:
            self.act_settings.setIcon(line_icon('settings', ink))
        if self.act_folder:
            self.act_folder.setIcon(line_icon('folder', ink))
        has_img = bool(self.last_saved and self.last_saved.is_file())
        has_vid = bool(self.last_video and self.last_video.is_file())
        if self.act_last_img:
            self.act_last_img.setVisible(has_img)
            self.act_last_img.setIcon(line_icon('capture', ink))
        if self.act_last_vid:
            self.act_last_vid.setVisible(has_vid)
            self.act_last_vid.setIcon(line_icon('video', ink))
        if self._tray_recent_sep:
            self._tray_recent_sep.setVisible(has_img or has_vid)
        if self.act_exit:
            self.act_exit.setIcon(line_icon('close', '#ef4444'))

    def _notify_window_refresh(self):
        if hasattr(self.window, 'refresh_summary'):
            self.window.refresh_summary(self)

    def update_entry(self):
        key = self.settings['hotkey']
        active = hasattr(self, 'hotkey') and self.hotkey.ident is not None
        self.window.screenshot_button.setText(
            ('框选截图  ' + key if len(key) <= 7 else '框选截图') if active else '框选截图 · 热键未启用'
        )
        self.window.screenshot_button.setToolTip(
            ('截图快捷键 ' + key if active else key + ' 未启用，可能被占用；仍可点击截图')
            + '；可切换长截图或视频，再按热键完成采集或停止录制'
        )
        self._notify_window_refresh()

    def remember_tools(self, value):
        self.tool_preferences = normalize_tools(value)
        try:
            save_tools(self.tools_path, self.tool_preferences)
        except OSError as exc:
            self.window.statusBar().showMessage('本次工具设置可用，但未能保存：' + str(exc), 10000)

    def show_settings(self):
        if self.long_capture and not self.long_capture.done:
            self.notify('请先完成长截图', '完成采集或取消后再修改设置', error=True)
            return
        if self.recording and not self.recording.done:
            self.notify('正在录制', '请先停止或取消录制，再修改设置', error=True)
            return
        from .settings_dialog import SettingsDialog
        SettingsDialog(self.window, controller=self).exec()
        self._notify_window_refresh()

    def notify(self, title, text='', *, error=False, force_tray=False):
        summary = f'{title}：{text}' if text else title
        self.window.statusBar().showMessage(summary, 10000)
        use_system = force_tray or error or self.settings.get('system_notifications', False)
        if use_system and self.tray:
            icon = QSystemTrayIcon.MessageIcon.Warning if error else QSystemTrayIcon.MessageIcon.Information
            self.tray.showMessage(title, text or title, icon, 3000)
        elif hasattr(self, 'hud') and self.hud is not None and not self.exiting:
            self.hud.show_message(title, text, duration_ms=1600 if error else 1100)

    def show_main(self):
        if self.capturing:
            return
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def clear_shortcut_frame(self):
        self.shortcut_frame = None
        self.shortcut_expiry.stop()

    def screen_layout(self):
        return [(s.name(), s.geometry(), s.devicePixelRatio()) for s in self.app.screens()]

    def freeze_shortcut_frame(self, new_gesture=True):
        if self.capturing or self.exiting or self.stopped or self.window.closing:
            return
        if self.window.isActiveWindow() or QApplication.activeModalWidget():
            return
        if new_gesture:
            self.clear_shortcut_frame()
        owner = window_owner(foreground_window())
        if not owner:
            return
        now = time.monotonic()
        if not new_gesture and self.shortcut_frame and now - self.shortcut_frame[0] < 1.0 and self.shortcut_frame[1] == owner:
            return
        if hasattr(self, 'hud') and self.hud is not None:
            self.hud.dismiss()
        layout = self.screen_layout()
        images = [s.grabWindow(0).toImage() for s in self.app.screens()]
        if images and not any(image.isNull() for image in images):
            # One short-lived frame in memory, never a background recording or file.
            self.shortcut_frame = (now, owner, layout, images)
            self.shortcut_expiry.start(1000)

    def take_shortcut_frame(self):
        saved = self.shortcut_frame
        self.clear_shortcut_frame()
        if (
            saved
            and time.monotonic() - saved[0] <= 1.0
            and saved[1] == window_owner(foreground_window())
            and saved[2] == self.screen_layout()
        ):
            return list(zip(self.app.screens(), saved[3]))
        return None

    def begin(self, *_, from_hotkey=False, mode='photo'):
        if self.long_capture and not self.long_capture.done:
            self.finish_long()
            return
        if getattr(self, 'recording', None) and not self.recording.done:
            self.stop_recording()
            return
        if self.capturing or self.exiting or self.window.closing:
            return
        if QApplication.activeModalWidget():
            self.notify('请先关闭对话框', '关闭当前设置或确认窗口后再截图', error=True)
            return
        if hasattr(self, 'hud') and self.hud is not None:
            self.hud.dismiss()
        self.capturing = True
        self.initial_mode = mode if mode in ('photo', 'long', 'video') else 'photo'
        self.from_hotkey = from_hotkey
        self.previous_foreground = foreground_window() if from_hotkey else None
        frames = self.take_shortcut_frame() if from_hotkey else None
        hide_main = not from_hotkey or self.window.isActiveWindow()
        self.restore_main = hide_main and self.window.isVisible() and not self.window.isMinimized()
        if hide_main:
            self.clear_shortcut_frame()
            self.window.hide()
            QTimer.singleShot(180, self.snapshot)
        else:
            self.snapshot(frames)

    def snapshot(self, frames=None):
        if self.exiting or not self.capturing:
            return
        try:
            if hasattr(self, 'hud') and self.hud is not None:
                self.hud.dismiss()
            if frames is None:
                frames = [(screen, screen.grabWindow(0).toImage()) for screen in self.app.screens()]
            if not frames or any(image.isNull() for _, image in frames):
                raise OSError('无法读取屏幕画面')
            win_rects = visible_window_rects_by_screen([screen for screen, _ in frames])
            directory = Path(self.settings['directory']).resolve()
            desktop = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)).resolve()
            save_label = '存桌面' if directory == desktop else '保存'
            for screen, image in frames:
                overlay = SelectionOverlay(
                    screen,
                    image,
                    self.tool_preferences,
                    window_rects=win_rects.get(id(screen), []),
                )
                overlay.set_video_audio_mode(self.video_audio_mode)
                overlay.set_copy_history_enabled(self.settings.get('save_copy_history', True))
                overlay.preferences_changed.connect(self.remember_tools)
                overlay.stop_key = self.hotkey.text if self.hotkey.ident is not None else '托盘菜单'
                overlay.refresh_toolbar()
                overlay.video_selected.connect(lambda rect, target=screen: self.begin_video(target, rect))
                overlay.long_selected.connect(lambda rect, target=screen: self.begin_long(target, rect))
                overlay.mode_changed.connect(self.change_capture_mode)
                overlay.video_audio_changed.connect(self.change_video_audio_mode)
                overlay.skip_countdown_requested.connect(self.skip_video_countdown)
                overlay.save_button.setText(save_label)
                overlay.save_label = save_label
                overlay.save_button.setToolTip('保存 PNG 到：' + str(directory) + ' 并复制 (Ctrl+S) · Ctrl+Shift+S 另存为')
                overlay.selected.connect(lambda img, target=overlay: self.complete_inline(img, target))
                overlay.save_selected.connect(lambda img, target=overlay: self.save_inline(img, target))
                overlay.save_as_selected.connect(lambda img, target=overlay: self.save_as_inline(img, target))
                overlay.pin_selected.connect(lambda img, target=overlay: self.pin_inline(img, target))
                overlay.beautify_selected.connect(lambda img, target=overlay: self.beautify_inline(img, target))
                overlay.color_picked.connect(self.color_picked)
                overlay.cancelled.connect(self.cancel)
                if getattr(self, 'initial_mode', 'photo') != 'photo':
                    overlay.set_mode(self.initial_mode)
                self.overlays.append(overlay)
            self.initial_mode = 'photo'
            # Every snapshot is taken before any selection overlay becomes visible.
            for overlay in self.overlays:
                overlay.show()
                overlay.raise_()
            active = next((o for o in self.overlays if o.geometry().contains(QCursor.pos())), self.overlays[0])
            active.activateWindow()
            active.setFocus()
        except Exception as exc:
            self.notify('截图失败', str(exc), error=True)
            self.cancel()

    def close_overlays(self):
        overlays, self.overlays = self.overlays, []
        for overlay in overlays:
            overlay.close()
            overlay.deleteLater()

    def record_copy_history(self, image) -> bool:
        if not self.settings.get('save_copy_history', True):
            return False
        if getattr(self, 'history', None) is None:
            return False
        return self.history.record(image) is not None

    def clear_copy_history(self) -> int:
        if getattr(self, 'history', None) is None:
            return 0
        count = self.history.clear()
        self._notify_window_refresh()
        return count

    def complete_inline(self, image, overlay):
        try:
            copy_image(image)
        except Exception as exc:
            overlay.show_error('复制失败，可重试或保存：' + str(exc))
            return
        recorded = self.record_copy_history(image)
        self.close_overlays()
        self.finished()
        hint = '已同步暂存至本机剪贴历史（可在设置关闭）' if recorded else '未写入磁盘文件'
        self.notify('已复制到剪贴板', hint)

    def save_inline(self, image, overlay):
        try:
            if (
                overlay.saved_image is not None
                and image == overlay.saved_image
                and overlay.saved_path
                and overlay.saved_path.is_file()
            ):
                path = overlay.saved_path
            else:
                path = save_png(image, self.settings['directory'])
                overlay.saved_image = image.copy()
                overlay.saved_path = path
            self.last_saved = path
        except Exception as exc:
            overlay.show_error('保存失败，可重试或仅复制：' + str(exc))
            return
        try:
            copy_image(image)
        except Exception as exc:
            overlay.show_error('图片已保存，复制失败，可重试：' + str(exc))
            self.notify('截图已保存', path.name)
            return
        self.close_overlays()
        self.finished()
        self._notify_window_refresh()
        self.notify('已保存并复制', path.name)

    def save_as_inline(self, image, overlay):
        def restore_overlays():
            for item in self.overlays:
                item.show()
                item.raise_()
            overlay.activateWindow()
            overlay.setFocus()

        for o in self.overlays:
            o.hide()
        default_dir = Path(self.settings['directory']).expanduser().resolve()
        default_name = default_dir / f"截图_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        picked = choose_save_image_path(None, '另存为图片', default_name)
        if not picked:
            restore_overlays()
            return
        final_path, overwrite = picked
        try:
            path = save_image_to_path(image, final_path, overwrite=overwrite)
            overlay.saved_image = image.copy()
            overlay.saved_path = path
            self.last_saved = path
        except Exception as exc:
            restore_overlays()
            overlay.show_error('另存为失败：' + str(exc))
            return
        try:
            copy_image(image)
        except Exception as exc:
            restore_overlays()
            overlay.show_error(f'图片已保存。复制失败，可按 Enter 重试。{exc}')
            self._notify_window_refresh()
            self.notify('截图已另存为，复制失败', str(path))
            return
        self.close_overlays()
        self.finished()
        self._notify_window_refresh()
        self.notify('已另存为并复制', path.name)

    def _refresh_pin_menu(self):
        if getattr(self, 'pin_clear', None):
            self.pin_clear.setEnabled(bool(self.pins))

    def pin_image(self, image, screen=None, target_rect=None):
        from .capture_pin import PinnedImageWindow
        pin = PinnedImageWindow(image, self, screen=screen, target_rect=target_rect)
        self.pins.append(pin)

        def _drop(*_):
            if pin in self.pins:
                self.pins.remove(pin)
            self._refresh_pin_menu()

        pin.destroyed.connect(_drop)
        self._refresh_pin_menu()
        pin.show()
        pin.raise_()
        return pin

    def pin_inline(self, image, overlay):
        target_screen = overlay.screen_ref
        sel = overlay.selection_rect()
        target_rect = sel.translated(overlay.geometry().topLeft()) if sel.width() >= 2 and sel.height() >= 2 else None
        self.close_overlays()
        self.finished()
        self.pin_image(image, screen=target_screen, target_rect=target_rect)
        self.notify('已原位贴到桌面', '滚轮缩放 · Ctrl+滚轮透明度 · 双击收起 · Esc/中键关闭')

    def pin_clipboard(self):
        image = QApplication.clipboard().image()
        if image.isNull():
            self.notify('剪贴板暂无图片', '请先复制一张图片后再贴图')
            return None
        pin = self.pin_image(image)
        self.notify('已贴图剪贴板图片', '滚轮缩放 · 双击收起 · Esc 关闭')
        return pin

    def beautify_image(self, image, screen=None):
        from .capture_beautify import BeautifyDialog
        dialog = BeautifyDialog(image, self)
        if screen:
            area = screen.availableGeometry()
            dialog.resize(min(dialog.width(), area.width() - 32), min(dialog.height(), area.height() - 48))
            dialog.move(area.x() + (area.width() - dialog.width()) // 2, area.y() + (area.height() - dialog.height()) // 2)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def beautify_inline(self, image, overlay):
        target_screen = overlay.screen_ref
        self.close_overlays()
        dialog = self.beautify_image(image, screen=target_screen)
        self.editor = dialog
        dialog.finished.connect(self.finished)

    def edit_image(self, image, screen=None):
        editor = CaptureEditor(image, self)
        if screen:
            area = screen.availableGeometry()
            editor.resize(min(editor.width(), area.width() - 32), min(editor.height(), area.height() - 48))
            editor.move(area.x() + (area.width() - editor.width()) // 2, area.y() + (area.height() - editor.height()) // 2)
        editor.show()
        editor.raise_()
        editor.activateWindow()
        return editor

    def color_picked(self, color_code):
        self.close_overlays()
        self.finished()
        self.notify('已复制色值', color_code)

    def close_all_pins(self):
        for pin in list(getattr(self, 'pins', [])):
            pin.close()
        self._refresh_pin_menu()

    def selected(self, image, screen=None):
        self.close_overlays()
        self.editor = CaptureEditor(image, self)
        self.editor.finished.connect(self.finished)
        if screen:
            area = screen.availableGeometry()
            self.editor.resize(min(self.editor.width(), area.width() - 32), min(self.editor.height(), area.height() - 48))
            self.editor.move(area.x() + (area.width() - self.editor.width()) // 2, area.y() + (area.height() - self.editor.height()) // 2)
        self.editor.show()
        self.editor.raise_()
        self.editor.activateWindow()

    def change_capture_mode(self, mode):
        for overlay in self.overlays:
            overlay.set_mode(mode)

    def change_video_audio_mode(self, mode):
        if self.recording:
            return
        from .video_audio import normalize_audio_mode
        self.video_audio_mode = normalize_audio_mode(mode)
        for overlay in self.overlays:
            overlay.set_video_audio_mode(self.video_audio_mode)
        self._notify_window_refresh()

    def is_desktop_destination(self):
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        return bool(desktop) and Path(self.settings['directory']).resolve() == Path(desktop).resolve()

    def begin_long(self, screen, rect):
        if self.long_capture or self.recording:
            return
        try:
            from .long_capture import LongCaptureSession
            key = self.hotkey.text if self.hotkey.ident is not None else 'Enter / 托盘菜单'
            initial = None
            for overlay in self.overlays:
                if overlay.screen_ref == screen:
                    initial = crop_selection(overlay.image, rect, screen.geometry().size())
                    break
            session = LongCaptureSession(screen, rect, key, self.window, initial_frame=initial)
            self.long_capture = session
            session.completed.connect(self.long_completed)
            session.failed.connect(self.long_failed)
            session.cancelled.connect(self.long_cancelled)
            self.close_overlays()
            if self.long_stop:
                self.long_stop.setEnabled(True)
            if self.tray:
                self.tray.setToolTip('SnapFlow')
            if self.from_hotkey:
                restore_foreground(self.previous_foreground)
            QTimer.singleShot(80, lambda: session.start() if self.long_capture is session and not session.done else None)
        except Exception as exc:
            self.long_failed(str(exc))

    def finish_long(self, *_):
        if self.long_capture:
            self.long_capture.finish()

    def long_completed(self, image, warning, segments):
        session, self.long_capture = self.long_capture, None
        if session:
            session.deleteLater()
        if self.long_stop:
            self.long_stop.setEnabled(False)
        try:
            from .long_editor import LongImageEditor
            self.editor = LongImageEditor(image, self, warning, segments)
            self.editor.finished.connect(self.finished)
            try:
                area = session.screen.availableGeometry() if session else self.app.primaryScreen().availableGeometry()
            except RuntimeError:
                area = self.app.primaryScreen().availableGeometry()
            self.editor.resize(min(self.editor.width(), area.width() - 32), min(self.editor.height(), area.height() - 48))
            self.editor.move(area.x() + (area.width() - self.editor.width()) // 2, area.y() + (area.height() - self.editor.height()) // 2)
            self.editor.show()
            self.editor.raise_()
            self.editor.activateWindow()
        except Exception as exc:
            self.long_failed(str(exc))

    def long_cancelled(self):
        self.finished()

    def long_failed(self, message):
        self.close_overlays()
        self.finished()
        self.notify('长截图未完成', message, error=True)

    def _close_record_outline(self):
        outline, self.record_outline = getattr(self, 'record_outline', None), None
        if outline is not None:
            outline.close()
            outline.deleteLater()

    def begin_video(self, screen, rect):
        if self.recording:
            return
        try:
            from .video_recording import RegionRecorder
            from .video_ui import RecordingControls, controls_position
            self.recording = RegionRecorder(screen, rect, self.window.home, self.window, audio_mode=self.video_audio_mode)
            self.recording.started.connect(self.recording_started)
            self.recording.progress.connect(self.recording_progress)
            self.recording.completed.connect(self.video_completed)
            self.recording.failed.connect(self.video_failed)
            key = self.hotkey.text if self.hotkey.ident is not None else '托盘菜单'
            self.record_controls = RecordingControls(key, self.video_audio_mode)
            self.record_controls.stop_requested.connect(self.stop_recording)
            self.record_controls.cancel_requested.connect(self.cancel)
            region = rect.toAlignedRect().translated(screen.geometry().topLeft())
            self.record_region_global = QRectF(region)
            point = controls_position(screen.availableGeometry(), region, self.record_controls.size())
            # Full-screen recording uses the hotkey/tray; no control panel is recorded.
            self.record_controls_position = point
            if point is None and self.hotkey.ident is None and not self.tray:
                raise ValueError('全屏录制需要启用截图热键，或使用系统托盘停止录制')
            if point is not None:
                self.record_controls.move(point)
            if self.video_stop:
                self.video_stop.setEnabled(True)
            if self.settings.get('skip_video_countdown', False):
                self.countdown_remaining = 0
                self._launch_recording_now()
                return
            self.countdown_remaining = 3
            for overlay in self.overlays:
                overlay.lock_selection(show_skip=True)
                overlay.confirm_button.setText('3 秒后开始 · Esc 取消')
                if overlay.start is not None:
                    overlay.position_actions()
            self.video_countdown.start()
        except Exception as exc:
            self.video_failed(str(exc))

    def skip_video_countdown(self):
        if not self.recording or not self.video_countdown.isActive():
            return
        self.video_countdown.stop()
        self.countdown_remaining = 0
        self._launch_recording_now()

    def _launch_recording_now(self):
        self.close_overlays()
        # Show a click-through border strictly OUTSIDE the recorded crop so the user sees bounds clearly.
        region = getattr(self, 'record_region_global', None)
        if region is not None and self.record_controls_position is not None:
            from .long_capture import RegionOutline
            self._close_record_outline()
            self.record_outline = RegionOutline(region, color='#ef4444', title='录屏区域 · SnapFlow')
            self.record_outline.show()
        if self.record_controls_position is not None and self.record_controls:
            self.record_controls.show()
        target = self.previous_foreground
        if self.from_hotkey:
            restore_foreground(target)
        recording = self.recording
        QTimer.singleShot(200, lambda: recording.start() if self.recording is recording and self.capturing else None)

    def countdown_video(self):
        if not self.recording or self.exiting:
            self.video_countdown.stop()
            return
        self.countdown_remaining -= 1
        for overlay in self.overlays:
            overlay.confirm_button.setText(f'{self.countdown_remaining} 秒后开始 · Esc 取消')
            if overlay.start is not None:
                overlay.position_actions()
        if self.countdown_remaining <= 0:
            self.video_countdown.stop()
            self._launch_recording_now()

    def recording_started(self):
        if self.record_controls:
            self.record_controls.started()
        if self.record_controls and self.recording.audio_device:
            self.record_controls.hint.setToolTip('正在录制电脑声音：' + self.recording.audio_device)
        if self.tray:
            self.tray.setToolTip('SnapFlow')

    def recording_progress(self, millis):
        if self.record_controls:
            self.record_controls.progress(millis)

    def stop_recording(self, *_):
        if not self.recording or self.recording.done:
            return
        if self.video_countdown.isActive() or self.recording.path is None:
            self.cancel()
            return
        if self.record_controls:
            self.record_controls.stopping()
        if self.video_stop:
            self.video_stop.setEnabled(False)
        self._close_record_outline()
        self.recording.stop()

    def video_completed(self, path):
        self._close_record_outline()
        if self.exiting:
            self.recording.keep_file = True
            self.finished()
            return
        from .video_ui import VideoPreview
        if self.record_controls:
            self.record_controls.hide()
        if self.video_stop:
            self.video_stop.setEnabled(False)
        try:
            self.editor = VideoPreview(path, self, self.recording.interruption, audio_mode=self.recording.audio_mode)
        except Exception as exc:
            self.recording.keep_file = True
            self.video_failed('无法打开预览：' + str(exc))
            return
        self.editor.finished.connect(self.finished)
        try:
            area = self.recording.screen.availableGeometry()
        except RuntimeError:
            area = self.app.primaryScreen().availableGeometry()
        self.editor.resize(min(self.editor.width(), area.width() - 32), min(self.editor.height(), area.height() - 48))
        self.editor.move(area.x() + (area.width() - self.editor.width()) // 2, area.y() + (area.height() - self.editor.height()) // 2)
        self.editor.show()
        self.editor.raise_()
        self.editor.activateWindow()

    def video_failed(self, message):
        self._close_record_outline()
        if self.recording:
            self.recording.keep_file = True
            if self.recording.path and self.recording.path.is_file():
                message += '；临时视频已保留（可能不完整）：' + str(self.recording.path)
        self.close_overlays()
        self.finished()
        self.notify('录制失败', message, error=True)

    def finished(self, *_):
        session, self.long_capture = self.long_capture, None
        if session:
            session.blockSignals(True)
            if not session.done:
                session.cancel()
            session.deleteLater()
        if self.long_stop:
            self.long_stop.setEnabled(False)
        editor, self.editor = self.editor, None
        if editor:
            editor.deleteLater()
        if getattr(self, 'recording', None):
            self.video_countdown.stop()
            recording, self.recording = self.recording, None
            recording.quiesce()

            def cleanup():
                try:
                    recording.discard()
                except OSError as exc:
                    self.notify('临时视频已保留', str(recording.path) + '；' + str(exc), error=True)
                recording.deleteLater()

            QTimer.singleShot(250, cleanup)
        if getattr(self, 'record_outline', None):
            outline, self.record_outline = self.record_outline, None
            outline.close()
            outline.deleteLater()
        if getattr(self, 'record_controls', None):
            self.record_controls.close()
            self.record_controls.deleteLater()
            self.record_controls = None
        if getattr(self, 'video_stop', None):
            self.video_stop.setEnabled(False)
        if getattr(self, 'tray', None):
            self.tray.setToolTip('SnapFlow')
        self.capturing = False
        if hasattr(self.window, 'refresh_summary'):
            self.window.refresh_summary(self)
        if self.restore_main and not self.exiting:
            if self.from_hotkey:
                self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                self.window.show()
                self.window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            else:
                self.show_main()
        if self.from_hotkey and not self.exiting:
            target = self.previous_foreground
            QTimer.singleShot(0, lambda: restore_foreground(target))

    def cancel(self):
        if self.long_capture and not self.long_capture.done:
            self.long_capture.cancel()
            return
        if self.recording and self.recording.frames and not self.recording.done:
            self.stop_recording()
            return
        self.close_overlays()
        self.finished()

    def open_directory(self):
        path = Path(self.settings['directory'])
        try:
            path.mkdir(parents=True, exist_ok=True)
            self.window.open_path(path)
        except OSError as exc:
            self.notify('目录无法打开', str(exc), error=True)

    def open_last(self):
        if self.last_saved and self.last_saved.is_file():
            self.window.open_path(self.last_saved)
        else:
            self.notify('没有可打开的截图', '本次运行尚未保存截图，或图片已经被移动')

    def open_last_video(self):
        if self.last_video and self.last_video.is_file():
            self.window.open_path(self.last_video)
        else:
            self.notify('没有可打开的视频', '本次运行尚未保存视频，或视频已经被移动')

    def exit(self):
        if self.capturing:
            self.notify('请先完成截图或录制', '录制时按截图热键停止，保存或关闭预览后再退出', error=True)
            return
        self.exiting = True
        self.window.close()

    def shutdown(self):
        self.clear_shortcut_frame()
        if self.stopped:
            return
        self.stopped = True
        self.exiting = True
        if getattr(self, 'hud', None):
            self.hud.dismiss()
            self.hud.close()
        self.close_overlays()
        self.hotkey.shutdown()
        self.close_all_pins()
        self._close_record_outline()
        if self.long_capture:
            self.long_capture.blockSignals(True)
            self.long_capture.cancel()
            self.long_capture.deleteLater()
            self.long_capture = None
        self.video_countdown.stop()
        if self.recording:
            self.recording.keep_file = True
            self.recording.timer.stop()
            self.recording.stop()
        if self.record_controls:
            self.record_controls.close()
        if self.editor:
            if hasattr(self.editor, 'release_player'):
                self.editor.release_player()
                QDialog.reject(self.editor)
            else:
                self.editor.reject()
        if self.tray:
            self.tray.hide()
