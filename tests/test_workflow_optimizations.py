import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from tests.capture_fixture import TempFixture as Fixture
from document_assistant.capture_beautify import BeautifyDialog, load_beautify_prefs
from document_assistant.capture_pin import PinnedImageWindow, _MARGIN
from document_assistant.gui import MainWindow
from document_assistant.long_capture import LongCaptureSession
from document_assistant.long_editor import LongImageEditor
from document_assistant.screen_capture import CaptureController, copy_file_to_clipboard
from document_assistant.selection_overlay import SelectionOverlay
from document_assistant.settings_dialog import HotkeyRecorderEdit, SettingsDialog
from document_assistant.video_ui import VideoPreview
from tests.test_long_capture import make_page


class WorkflowOptimizationTests(Fixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _overlay(self, width=1280, height=720, window_rects=None):
        img = QImage(width, height, QImage.Format.Format_ARGB32)
        img.fill(QColor('#1e3a5f'))
        screen = SimpleNamespace(
            geometry=lambda: QRect(0, 0, width, height),
            availableGeometry=lambda: QRect(0, 0, width, height - 40),
            devicePixelRatio=lambda: 1.0,
        )
        overlay = SelectionOverlay(screen, img, window_rects=window_rects)
        overlay.show()
        self.app.processEvents()
        self.addCleanup(overlay.close)
        self.addCleanup(overlay.deleteLater)
        return overlay

    def test_window_snap_click_and_full_edge_resize_and_double_click_confirm(self):
        win_rect = QRectF(120, 80, 500, 340)
        overlay = self._overlay(window_rects=[win_rect])
        copied = []
        overlay.selected.connect(copied.append)

        # Hover detects window; single click selects it cleanly.
        overlay.hover_pos = QPointF(250, 200)
        overlay.hovered_window = overlay._window_at(overlay.hover_pos)
        self.assertEqual(overlay.hovered_window, win_rect)
        overlay.begin_drag(QPointF(250, 200))
        overlay.end_drag(QPointF(250, 200))
        self.assertEqual(overlay.selection_rect(), win_rect)

        # Full 4-edge resize away from midpoint dot works (e.g. near top of right edge).
        self.assertEqual(overlay.hit_test_selection(QPointF(620, 120)), 'e')
        self.assertEqual(overlay.cursor_for_hit('e'), Qt.CursorShape.SizeHorCursor)
        overlay.begin_drag(QPointF(620, 120))
        overlay.end_drag(QPointF(660, 120))
        self.assertEqual(overlay.selection_rect().width(), 540)

        # Double-click inside selection in smart-pointer mode copies & confirms.
        QTest.mouseDClick(overlay.canvas, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
        self.assertEqual(len(copied), 1)
        self.assertEqual(copied[0].width(), 540)

    def test_tiered_right_click_escape_text_and_single_key_shortcuts(self):
        overlay = self._overlay()
        cancelled = []
        overlay.cancelled.connect(lambda: cancelled.append(True))

        overlay.begin_drag(QPointF(100, 100))
        overlay.end_drag(QPointF(500, 380))
        self.app.processEvents()

        # Single-key shortcuts switch tools cleanly & style sub-bar opens without shifting Row 1.
        row1_x_before = overlay.confirm_button.x()
        QTest.keyClick(overlay, Qt.Key.Key_R)
        self.assertEqual(overlay.tool, 'rectangle')
        self.assertTrue(overlay.style_bar.isVisible())
        self.assertEqual(len(overlay.color_buttons), 7)
        # Main row width remains stable between tools.
        QTest.keyClick(overlay, Qt.Key.Key_M)
        self.assertEqual(overlay.tool, 'mask')
        self.assertEqual(overlay.confirm_button.x(), row1_x_before)

        # Inline text Escape cancels text only, NOT the whole capture.
        QTest.keyClick(overlay, Qt.Key.Key_T)
        overlay.canvas.begin_text(QPointF(60, 60))
        self.assertIsNotNone(overlay.canvas.text_editor)
        overlay.handle_escape()
        self.assertIsNone(overlay.canvas.text_editor)
        self.assertFalse(cancelled)

        # Tiered right-click: drawing tool -> view -> clear selection -> cancel capture.
        overlay.handle_right_click()
        self.assertEqual(overlay.tool, 'view')
        self.assertIsNotNone(overlay.start)
        self.assertFalse(cancelled)

        overlay.handle_right_click()
        self.assertIsNone(overlay.start)
        self.assertFalse(cancelled)

        overlay.handle_right_click()
        self.assertEqual(len(cancelled), 1)

    def test_arrow_nudge_ctrl_a_and_eyedropper_rgb_toggle(self):
        overlay = self._overlay()
        picked = []
        overlay.color_picked.connect(picked.append)
        overlay.hover_pos = QPointF(50, 50)
        QTest.keyClick(overlay, Qt.Key.Key_Shift)
        self.assertEqual(overlay.color_format, 'rgb')
        QTest.keyClick(overlay, Qt.Key.Key_C)
        self.assertTrue(picked and picked[0].startswith('rgb('))

        # Selection arrow nudge by 1px and 10px with Shift.
        overlay.begin_drag(QPointF(100, 100))
        overlay.end_drag(QPointF(300, 260))
        QTest.keyClick(overlay, Qt.Key.Key_Right)
        self.assertEqual(overlay.selection_rect().left(), 101)
        QTest.keyClick(overlay, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(overlay.selection_rect().top(), 110)

        # Ctrl+A selects full screen.
        overlay.select_full_screen()
        self.assertEqual(overlay.selection_rect(), QRectF(overlay.rect()))

    def test_in_place_high_dpi_pin_and_double_click_collapse(self):
        # 450x300 physical pixels on a 150% DPI screen == 300x200 logical pixels.
        img = QImage(450, 300, QImage.Format.Format_ARGB32)
        img.fill(QColor('#2563eb'))
        screen = SimpleNamespace(
            availableGeometry=lambda: QRect(0, 0, 1920, 1040),
            devicePixelRatio=lambda: 1.5,
        )
        target = QRectF(800, 220, 300, 200)
        pin = PinnedImageWindow(img, screen=screen, target_rect=target)
        self.addCleanup(pin.close)
        # Logical size matches 300x200 + margins, positioned in-place at (800, 220).
        self.assertEqual(pin.width(), 300 + _MARGIN * 2)
        self.assertEqual(pin.height(), 200 + _MARGIN * 2)
        self.assertEqual(pin.x(), 800 - _MARGIN)
        self.assertEqual(pin.y(), 220 - _MARGIN)

        # Double-click folds into compact badge instead of closing; second double-click restores.
        pin.show()
        self.app.processEvents()
        QTest.mouseDClick(pin, Qt.MouseButton.LeftButton, pos=QPoint(60, 60))
        self.assertTrue(pin.compact)
        self.assertTrue(pin.isVisible())
        QTest.mouseDClick(pin, Qt.MouseButton.LeftButton, pos=QPoint(30, 30))
        self.assertFalse(pin.compact)
        self.assertEqual(pin.width(), 300 + _MARGIN * 2)

    def test_copy_history_anti_loss_and_gallery_history_tab(self):
        home = self.root / 'settings'
        captures = self.root / 'captures'
        window = MainWindow(home)
        controller = CaptureController(window, activate=False)
        controller.settings['directory'] = str(captures)
        try:
            img = QImage(120, 90, QImage.Format.Format_ARGB32)
            img.fill(QColor('#10b981'))
            overlay = self._overlay(400, 300)
            controller.overlays = [overlay]
            controller.capturing = True
            controller.complete_inline(img, overlay)
            # Copy-only never pollutes the user's save directory, but saves to home/history.
            self.assertFalse(captures.exists())
            self.assertEqual(len(controller.history.entries()), 1)

            window.set_gallery_filter('history')
            self.assertEqual(window.recent_count.text(), '最近 1 项')
            self.assertEqual(len(window._gallery_cards), 1)
        finally:
            controller.shutdown()
            window.close()
            self.app.processEvents()

    def test_beautify_persists_preferences_and_fast_slider_renders_full_res_on_export(self):
        home = self.root / 'settings'
        window = MainWindow(home)
        controller = CaptureController(window, activate=False)
        try:
            large = QImage(1600, 1000, QImage.Format.Format_ARGB32)
            large.fill(QColor('#334155'))
            dialog = BeautifyDialog(large, controller)
            self.addCleanup(dialog.close)
            dialog._set_option('preset', 'paper')
            dialog._set_option('padding', 32)
            dialog._set_option('window_chrome', True)
            dialog.close()

            loaded = load_beautify_prefs(home)
            self.assertEqual(loaded['preset'], 'paper')
            self.assertEqual(loaded['padding'], 32)
            self.assertTrue(loaded['window_chrome'])

            # New dialog automatically remembers previous style.
            dialog2 = BeautifyDialog(large, controller)
            self.addCleanup(dialog2.close)
            self.assertEqual(dialog2.options['preset'], 'paper')
            self.assertEqual(dialog2.options['padding'], 32)
            # Fast slider preview followed by full-res ensure.
            dialog2._on_slider_pressed()
            dialog2.sliders['padding'].setValue(48)
            dialog2._on_slider_released()
            self.assertEqual(dialog2.rendered_image.width(), 1600 + 48 * 2)
        finally:
            controller.shutdown()
            window.close()
            self.app.processEvents()

    def test_video_save_copies_file_url_and_skip_countdown_starts_recording(self):
        source = self.root / 'clip.mp4'
        source.write_bytes(b'synthetic-mp4-data' * 40)
        refreshed = []
        controller = SimpleNamespace(
            settings={'directory': str(self.root / 'saved')},
            notify=lambda *a, **kw: None,
            _notify_window_refresh=lambda: refreshed.append(True),
        )
        preview = VideoPreview(source, controller)
        preview.save()
        self.assertTrue(preview.saved_path.is_file())
        self.assertTrue(refreshed)
        urls = QApplication.clipboard().mimeData().urls()
        self.assertTrue(urls and urls[0].toLocalFile().endswith('.mp4'))
        preview.release_player()
        preview.deleteLater()
        self.app.processEvents()

        # Verify skip_video_countdown immediately launches and displays RegionOutline outside crop.
        home = self.root / 'vid_settings'
        window = MainWindow(home)
        ctrl = CaptureController(window, activate=False)
        screen = SimpleNamespace(
            geometry=lambda: QRect(0, 0, 1280, 720),
            availableGeometry=lambda: QRect(0, 0, 1280, 680),
            devicePixelRatio=lambda: 1.0,
        )
        img = QImage(1280, 720, QImage.Format.Format_RGB32)
        img.fill(QColor('#112233'))
        overlay = SelectionOverlay(screen, img)
        ctrl.overlays = [overlay]
        ctrl.capturing = True
        overlay.start = QPointF(100, 100)
        overlay.end = QPointF(500, 380)
        overlay.set_mode('video')
        overlay.show()
        try:
            with patch('document_assistant.screen_capture.QTimer.singleShot'):
                ctrl.begin_video(screen, overlay.selection_rect())
                self.assertTrue(overlay.skip_countdown_button.isVisible())
                self.assertTrue(ctrl.video_countdown.isActive())
                ctrl.skip_video_countdown()
                self.assertFalse(ctrl.video_countdown.isActive())
                self.assertIsNotNone(ctrl.record_outline)
                self.assertTrue(ctrl.record_outline.isVisible())
        finally:
            ctrl.cancel()
            QTest.qWait(260)
            ctrl.shutdown()
            window.close()

    def test_long_auto_scroll_ignores_cursor_moving_onto_controls_panel(self):
        page = make_page(width=600, height=2000)
        screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 1280, 720), availableGeometry=lambda: QRect(0, 0, 1280, 680))
        session = LongCaptureSession(screen, QRectF(50, 50, 600, 400), 'Alt+S', grabber=lambda: page.copy(0, 0, 600, 400))
        self.addCleanup(session.cancel)
        with patch('document_assistant.long_capture.CaptureKeys'):
            session.start()
            session.timer.stop()
            session.set_auto_scroll(True)
            ctrl_center = session.controls.geometry().center()
            with patch('document_assistant.long_capture.QCursor.pos', return_value=ctrl_center):
                session._auto_scroll_step()
                for _ in range(70):
                    session.poll()
            # Moving mouse to controls panel (e.g. to click 完成) must NOT falsely pause or hit bottom.
            self.assertTrue(session.auto_scrolling)
            self.assertEqual(session._auto_unchanged_ticks, 0)
            self.assertNotIn('底部', session.controls.status.text())
            # Moving mouse far away outside both region and controls pauses cleanly.
            with patch('document_assistant.long_capture.QCursor.pos', return_value=QPoint(1250, 10)):
                session._auto_scroll_step()
            self.assertFalse(session.auto_scrolling)

    def test_long_auto_scroll_positions_cursor_via_qt_logical_coords_not_raw_win32(self):
        page = make_page(width=600, height=1200)
        screen = SimpleNamespace(
            geometry=lambda: QRect(0, 0, 1707, 1067),
            availableGeometry=lambda: QRect(0, 0, 1707, 1027),
            devicePixelRatio=lambda: 1.5,
        )
        session = LongCaptureSession(screen, QRectF(800, 300, 600, 400), 'Alt+S', grabber=lambda: page.copy(0, 0, 600, 400))
        self.addCleanup(session.cancel)
        moved = []
        with patch('document_assistant.long_capture.CaptureKeys'), \
             patch('document_assistant.long_capture.QCursor.pos', return_value=QPoint(10, 10)), \
             patch('document_assistant.long_capture.QCursor.setPos', side_effect=lambda *args: moved.append(args)):
            session.start()
            session.timer.stop()
            session.set_auto_scroll(True)
        # Logical center of (800, 300, 600, 400) is (1100, 500); QCursor.setPos handles 150% DPI cleanly.
        self.assertEqual(moved, [(1100, 500)])

    def test_save_as_does_not_clobber_existing_png_without_confirmation(self):
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from document_assistant.screen_capture import choose_save_image_path, resolve_save_image_path, save_image_to_path

        existing_png = self.root / 'example.png'
        existing_png.write_bytes(b'original-example-png')
        existing_backup_png = self.root / 'example.backup.png'
        existing_backup_png.write_bytes(b'original-backup-png')

        # 1) 'example.backup' resolves to 'example.backup.png', NEVER hijacking 'example.png'.
        resolved, fmt = resolve_save_image_path(self.root / 'example.backup')
        self.assertEqual(resolved, existing_backup_png.resolve())
        self.assertEqual(fmt, 'PNG')

        # 2) When resolved target already exists after suffix normalization, cancelling overwrite preserves it.
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(self.root / 'example.backup'), 'PNG 图片 (*.png)')), \
             patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Cancel) as ask:
            picked = choose_save_image_path(None, '另存为', self.root / 'default.png')
            self.assertIsNone(picked)
            ask.assert_called_once()
        self.assertEqual(existing_png.read_bytes(), b'original-example-png')
        self.assertEqual(existing_backup_png.read_bytes(), b'original-backup-png')

        img = QImage(32, 24, QImage.Format.Format_ARGB32)
        img.fill(QColor('#2563eb'))
        with self.assertRaises(FileExistsError):
            save_image_to_path(img, self.root / 'example.backup')
        self.assertEqual(existing_backup_png.read_bytes(), b'original-backup-png')

        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(existing_backup_png), 'PNG (*.png)')), \
             patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes) as ask:
            target, approved = choose_save_image_path(None, '另存为', self.root / 'default.png')
            ask.assert_called_once()
        save_image_to_path(img, target, overwrite=approved)
        self.assertEqual(QImage(str(existing_backup_png)).size(), img.size())
        self.assertEqual(existing_png.read_bytes(), b'original-example-png')

    def test_save_as_preserves_file_created_after_dialog_closes(self):
        from document_assistant import screen_capture as capture

        selected = self.root / 'sync.png'
        image = QImage(32, 24, QImage.Format.Format_ARGB32)
        image.fill(QColor('#2563eb'))
        overlay = Mock()
        controller = SimpleNamespace(settings={'directory': str(self.root)}, overlays=[overlay],
                                     close_overlays=Mock(), finished=Mock(), notify=Mock(),
                                     _notify_window_refresh=Mock())
        real_save = capture.save_image_to_path

        def create_file_before_writing(rendered, target, **options):
            target.write_bytes(b'new file from another application')
            return real_save(rendered, target, **options)

        with patch.object(capture.QFileDialog, 'getSaveFileName', return_value=(str(selected), 'PNG (*.png)')), \
             patch.object(capture, 'save_image_to_path', side_effect=create_file_before_writing), \
             patch.object(capture, 'copy_image') as copy:
            CaptureController.save_as_inline(controller, image, overlay)

        self.assertEqual(selected.read_bytes(), b'new file from another application')
        self.assertIn('文件已存在', overlay.show_error.call_args.args[0])
        overlay.show.assert_called_once()
        controller.close_overlays.assert_not_called()
        copy.assert_not_called()

    def test_save_as_keeps_capture_open_when_clipboard_is_busy(self):
        from document_assistant import screen_capture as capture

        image = QImage(32, 24, QImage.Format.Format_ARGB32)
        image.fill(QColor('#2563eb'))
        for entry in (CaptureController, capture.CaptureEditor, LongImageEditor):
            with self.subTest(entry=entry.__name__):
                selected = self.root / f'{entry.__name__}.png'
                overlay = Mock()
                controller = SimpleNamespace(settings={'directory': str(self.root)}, overlays=[overlay],
                                             close_overlays=Mock(), finished=Mock(), notify=Mock(),
                                             _notify_window_refresh=Mock())
                error = Mock()
                dialog = SimpleNamespace(controller=controller, destination=self.root,
                                         canvas=SimpleNamespace(rendered=lambda: image, finish_text=Mock()),
                                         show_error=error, error=error, accept=Mock())
                with patch.object(capture.QFileDialog, 'getSaveFileName', return_value=(str(selected), 'PNG (*.png)')), \
                     patch.object(capture, 'copy_image', side_effect=OSError('剪贴板被占用')):
                    if entry is CaptureController:
                        entry.save_as_inline(controller, image, overlay)
                        overlay.show.assert_called_once()
                        controller.close_overlays.assert_not_called()
                        self.assertIn('复制失败', overlay.show_error.call_args.args[0])
                        self.assertEqual(overlay.saved_path, selected)
                    else:
                        entry.save_as(dialog)
                        dialog.accept.assert_not_called()
                        self.assertIn('复制失败', error.call_args.args[0])
                        self.assertEqual(dialog.saved_path, selected)
                self.assertEqual(QImage(str(selected)).size(), image.size())
                self.assertIn('复制失败', controller.notify.call_args.args[0])

    def test_copy_history_setting_can_disable_disk_writes_and_clear_history(self):
        home = self.root / 'privacy_home'
        window = MainWindow(home)
        controller = CaptureController(window, activate=False)
        try:
            service = SimpleNamespace(state=False, enabled=lambda: False, set_enabled=lambda v: None)
            dialog = SettingsDialog(window, service=service, controller=controller)
            self.addCleanup(dialog.close)
            self.assertTrue(dialog.copy_history_switch.isChecked())
            dialog.copy_history_switch.setChecked(False)
            with patch.object(controller.hotkey, 'prepare', return_value=(101, 'Alt+S')), \
                 patch.object(controller.hotkey, 'commit'):
                dialog.save_settings()
            self.assertFalse(controller.settings['save_copy_history'])

            img = QImage(80, 60, QImage.Format.Format_ARGB32)
            img.fill(QColor('#ef4444'))
            overlay = self._overlay(400, 300)
            overlay.set_copy_history_enabled(False)
            self.assertIn('不写入磁盘', overlay.confirm_button.toolTip())
            controller.overlays = [overlay]
            controller.capturing = True
            controller.complete_inline(img, overlay)
            # Zero files written to home/history when save_copy_history is False.
            self.assertEqual(controller.history.entries(), [])
            self.assertFalse((home / 'history').exists())

            # Re-enable, record one, then clear via clear_copy_history().
            controller.settings['save_copy_history'] = True
            self.assertTrue(controller.record_copy_history(img))
            self.assertEqual(len(controller.history.entries()), 1)
            self.assertEqual(controller.clear_copy_history(), 1)
            self.assertEqual(controller.history.entries(), [])
        finally:
            controller.shutdown()
            window.close()
            self.app.processEvents()

    def test_long_editor_has_highlighter_step_pin_beautify_and_inline_text(self):
        img = QImage(400, 700, QImage.Format.Format_ARGB32)
        img.fill(QColor('white'))
        controller = SimpleNamespace(
            tool_preferences={},
            is_desktop_destination=lambda: True,
            remember_tools=lambda _: None,
            settings={'directory': str(self.root)},
            notify=lambda *a: None,
        )
        editor = LongImageEditor(img, controller)
        self.addCleanup(editor.close)
        for tool in ('highlighter', 'step', 'text', 'mask'):
            self.assertIn(tool, editor.tool_buttons)
        self.assertTrue(hasattr(editor, 'pin_button'))
        self.assertTrue(hasattr(editor, 'beautify_button'))
        editor.show()
        self.app.processEvents()
        editor.canvas.begin_text(QPointF(40, 40), 'inline note')
        self.assertIsNotNone(editor.canvas.text_editor)
        editor.canvas.finish_text()
        self.assertEqual(editor.canvas.marks[0][3], 'inline note')

    def test_unified_settings_dialog_and_hotkey_recorder_and_tray_click(self):
        recorder = HotkeyRecorderEdit()
        QTest.keyClick(recorder, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(recorder.text(), 'Ctrl+Shift+D')

        home = self.root / 'settings'
        window = MainWindow(home)
        controller = CaptureController(window, activate=False)
        try:
            service = SimpleNamespace(state=False, enabled=lambda: False, set_enabled=lambda v: None)
            dialog = SettingsDialog(window, service=service, controller=controller)
            self.addCleanup(dialog.close)
            dialog.system_notify_switch.setChecked(True)
            dialog.skip_countdown_switch.setChecked(True)
            dialog.tray_action_combo.setCurrentIndex(1)
            with patch.object(controller.hotkey, 'prepare', return_value=(99, 'Alt+S')), \
                 patch.object(controller.hotkey, 'commit'):
                dialog.save_settings()
            self.assertTrue(controller.settings['system_notifications'])
            self.assertTrue(controller.settings['skip_video_countdown'])
            self.assertEqual(controller.settings['tray_click_action'], 'capture')

            # Tray single-click dispatches according to configured tray_click_action.
            with patch.object(controller, 'begin') as mock_begin, patch.object(controller, 'show_main') as mock_show:
                controller._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
                mock_begin.assert_called_once()
                mock_show.assert_not_called()
        finally:
            controller.shutdown()
            window.close()
            self.app.processEvents()

    def test_frameless_snapflow_icon_and_clean_tray_tooltip(self):
        from PySide6.QtGui import QIcon
        from document_assistant.windows_identity import ICON_PATH
        icon = QIcon(str(ICON_PATH))
        self.assertFalse(icon.isNull())
        for sz in (16, 24, 32, 48, 128):
            pm = icon.pixmap(sz, sz)
            img = pm.toImage()
            self.assertEqual(round(pm.width() / pm.devicePixelRatio()), sz)
            # Frameless icon keeps transparent corners instead of a solid square box.
            self.assertEqual(img.pixelColor(0, 0).alpha(), 0)

        home = self.root / 'tray_tip'
        window = MainWindow(home)
        controller = CaptureController(window, activate=False)
        fake_tray = SimpleNamespace(tip='', setToolTip=lambda t: setattr(fake_tray, 'tip', t))
        controller.tray = fake_tray
        try:
            with patch.object(controller.hotkey, 'prepare', return_value=(77, 'Alt+A')), \
                 patch.object(controller.hotkey, 'commit'):
                controller.configure('Alt+A', str(self.root / 'caps'))
            self.assertEqual(fake_tray.tip, 'SnapFlow')
        finally:
            controller.tray = None
            controller.shutdown()
            window.close()
            self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
