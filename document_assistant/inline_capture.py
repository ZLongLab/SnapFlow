"""Edit screenshot annotations directly inside the selected screen region."""
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QLineEdit
from .capture_canvas import AnnotationCanvas
from .capture_markup import draw_annotation, mark_bounds
from .capture_material import SELECTION_COLOR, HANDLE_COLOR

_RESIZE_HITS = ('nw', 'ne', 'sw', 'se', 'n', 's', 'w', 'e')


class InlineAnnotationCanvas(AnnotationCanvas):
    def __init__(self, image, parent):
        super().__init__(image)
        self.setParent(parent)
        self.setMinimumSize(0, 0)
        self.setObjectName('inlineCaptureCanvas')
        self.text_editor = None
        self.text_anchor = None
        self.editing_mark = None
        self.brush_position = None
        self._drag_hidden = False
        self.setMouseTracking(True)
        self.set_tool('view')

    def set_drag_hidden(self, hidden: bool):
        if self._drag_hidden == hidden:
            return
        self._drag_hidden = hidden
        self.update()

    def _sync_mouse_passthrough(self):
        # When in smart-pointer mode with zero marks, let SelectionOverlay receive
        # press/move/double-click directly for zero-overhead native region dragging.
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            self.tool == 'view' and not self.marks and self.text_editor is None,
        )

    def scale(self):
        if hasattr(self, 'pixel_mapping'):
            sx, sy, _, _ = self.pixel_mapping
            return min(1 / sx, 1 / sy)
        return min(self.width() / max(1, self.image.width()), self.height() / max(1, self.image.height()))

    def image_rect(self):
        if hasattr(self, 'pixel_mapping'):
            sx, sy, x, y = self.pixel_mapping
            return QRectF(x, y, self.image.width() / sx, self.image.height() / sy)
        return QRectF(self.rect())

    def image_point(self, point):
        if not QRectF(self.rect()).contains(point):
            return None
        rect = self.image_rect()
        return QPointF(
            (point.x() - rect.x()) * self.image.width() / max(.01, rect.width()),
            (point.y() - rect.y()) * self.image.height() / max(.01, rect.height()),
        )

    def set_tool(self, tool):
        self.finish_text()
        self.tool = tool
        self.start = self.end = None
        self.stroke = []
        self.selected_index = None
        self._sync_mouse_passthrough()
        self.brush_position = None
        if tool == 'mask':
            point = self.mapFromGlobal(QCursor.pos())
            if self.rect().contains(point):
                self.brush_position = QPointF(point)
        self._update_hover_cursor(QPointF(self.mapFromGlobal(QCursor.pos())))
        self.selection_changed.emit()
        self.update()

    def _update_hover_cursor(self, local_pos):
        parent = self.parentWidget()
        if parent is not None and hasattr(parent, 'hit_test_selection'):
            overlay_pos = local_pos + QPointF(self.pos())
            edge_only = self.tool not in ('view', 'select')
            hit = parent.hit_test_selection(overlay_pos, edge_margin=5 if edge_only else 7)
            if hit in _RESIZE_HITS:
                self.setCursor(parent.cursor_for_hit(hit))
                return
        if self.tool == 'mask':
            self.setCursor(Qt.CursorShape.BlankCursor)
        elif self.tool in ('view', 'select'):
            img_pt = self.image_point(local_pos)
            if img_pt is not None and self.pick(img_pt) is not None:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif self.tool == 'view':
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

    def wheelEvent(self, event):
        parent = self.parentWidget()
        delta = event.angleDelta().y()
        if delta and parent is not None and hasattr(parent, 'adjust_active_size') and self.tool not in ('view', 'select'):
            step = 1 if delta > 0 else -1
            if parent.adjust_active_size(step):
                event.accept()
                return
        event.ignore()

    def resizeEvent(self, event):
        self.zoom_changed.emit(self.scale())

    def paintEvent(self, event):
        if self._drag_hidden:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.image_rect()
        if self.moving is not None and self._drag_base_pixmap is not None and self.selected_index is not None:
            painter.drawPixmap(rect, self._drag_base_pixmap, QRectF(self._drag_base_pixmap.rect()))
        else:
            pm = self.rendered_pixmap()
            painter.drawPixmap(rect, pm, QRectF(pm.rect()))
        painter.save()
        painter.translate(rect.topLeft())
        painter.scale(rect.width() / max(1, self.image.width()), rect.height() / max(1, self.image.height()))
        if self.moving is not None and self.selected_index is not None and self.selected_index < len(self.marks):
            mark = self.marks[self.selected_index]
            draw_annotation(
                painter,
                mark,
                self.image.size(),
                self.mosaic_source() if mark[0] == 'mask' else None,
            )
        if self.start is not None and self.end is not None:
            draw_annotation(
                painter,
                self.new_mark(self.start, self.end),
                self.image.size(),
                self.mosaic_source() if self.tool == 'mask' else None,
            )
        if self.selected_index is not None and self.selected_index < len(self.marks):
            painter.setPen(QPen(QColor(SELECTION_COLOR), 1.5 / max(.01, self.scale()), Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(mark_bounds(self.marks[self.selected_index], self.image.size()).adjusted(-4, -4, 4, 4))
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(SELECTION_COLOR), 1.5))
        painter.drawRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5))
        painter.setPen(QPen(QColor(HANDLE_COLOR), 1.2))
        painter.setBrush(QColor('#e5f5ff'))
        x, y = self.width() / 2, self.height() / 2
        for point in (
            QPointF(0, 0), QPointF(x, 0), QPointF(self.width(), 0), QPointF(self.width(), y),
            QPointF(self.width(), self.height()), QPointF(x, self.height()), QPointF(0, self.height()), QPointF(0, y),
        ):
            painter.drawEllipse(point, 3.5, 3.5)
        if self.tool == 'mask' and self.brush_position is not None:
            radius = self.brush_size * self.scale() / 2
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor('#16232c'), 3))
            painter.drawEllipse(self.brush_position, radius, radius)
            painter.setPen(QPen(QColor('white'), 1))
            painter.drawEllipse(self.brush_position, radius, radius)
        painter.end()

    def enterEvent(self, event):
        if self.tool == 'mask':
            self.brush_position = QPointF(self.mapFromGlobal(QCursor.pos()))
            self.update()
        self._update_hover_cursor(QPointF(self.mapFromGlobal(QCursor.pos())))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.brush_position = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        parent = self.parentWidget()
        if event.button() == Qt.MouseButton.RightButton:
            if parent is not None and hasattr(parent, 'handle_right_click'):
                parent.handle_right_click()
            elif parent is not None:
                parent.cancelled.emit()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        overlay_point = event.position() + QPointF(self.pos())
        if parent is not None and hasattr(parent, 'hit_test_selection'):
            edge_only = self.tool not in ('view', 'select')
            hit = parent.hit_test_selection(overlay_point, edge_margin=5 if edge_only else 7)
            if hit in _RESIZE_HITS:
                parent.begin_drag(overlay_point)
                return
        if self.tool == 'text':
            self.finish_text()
            anchor = self.image_point(event.position())
            if anchor is not None:
                self.begin_text(anchor)
            return
        if self.tool in ('view', 'select'):
            self.setFocus()
            img_pt = self.image_point(event.position())
            picked = self.pick(img_pt) if img_pt is not None else None
            if picked is not None:
                self.selected_index = picked
                self.selection_changed.emit()
                self.update()
                self.moving = img_pt
                import copy
                self.move_before = copy.deepcopy(self.marks)
                self._prepare_drag_base(picked)
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                return
            if self.selected_index is not None:
                self.selected_index = None
                self.selection_changed.emit()
                self.update()
            if self.tool == 'view' and parent is not None:
                parent.begin_drag(overlay_point)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.tool == 'mask':
            self.brush_position = event.position()
            self.update()
        parent = self.parentWidget()
        if parent is not None and parent.drag is not None:
            parent.move_drag(event.position() + QPointF(self.pos()))
            return
        if self.moving is None and self.start is None and self.drag_position is None:
            self._update_hover_cursor(event.position())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        parent = self.parentWidget()
        if parent is not None and parent.drag is not None:
            parent.end_drag(event.position() + QPointF(self.pos()))
            return
        was_moving = self.moving is not None
        super().mouseReleaseEvent(event)
        if was_moving:
            self._update_hover_cursor(event.position())

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        parent = self.parentWidget()
        if self.tool in ('view', 'select'):
            img_pt = self.image_point(event.position())
            if img_pt is not None:
                picked = self.pick(img_pt)
                if picked is not None and self.marks[picked][0] == 'text':
                    self.selected_index = picked
                    self.selection_changed.emit()
                    self.edit_text()
                    return
            if self.tool == 'view' and parent is not None:
                # Cancel any drag started by the first click before confirming.
                parent.drag = None
                parent.confirm()
                return
        super().mouseDoubleClickEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.text_editor and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.cancel_text()
                if self.parentWidget() is not None:
                    self.parentWidget().setFocus()
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
            'QLineEdit { color:#e8f2fa; background:#172a3b; border:1px solid #85c9ee; '
            'border-radius:4px; padding:4px; selection-background-color:#2c81ac; }'
        )
        font = editor.font()
        font.setPixelSize(max(12, round(self.text_size * self.scale())))
        editor.setFont(font)
        rect = self.image_rect()
        x = round(rect.x() + anchor.x() * rect.width() / self.image.width())
        y = round(rect.y() + anchor.y() * rect.height() / self.image.height())
        w = max(120, min(360, self.width() - max(0, x)))
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
