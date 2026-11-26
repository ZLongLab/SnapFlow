import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication
from tests.capture_fixture import TempFixture as Fixture
from document_assistant.screen_capture import AnnotationCanvas, CaptureEditor, CaptureController
from document_assistant.gui import MainWindow


class CapturePolishTests(Fixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_zoom_and_pan_preserve_source_and_annotation_coordinates(self):
        image = QImage(3840, 2160, QImage.Format.Format_ARGB32)
        image.fill(QColor('blue'))
        canvas = AnnotationCanvas(image)
        canvas.resize(800, 450)
        canvas.marks = [('rectangle', QPointF(100, 100), QPointF(300, 300), '', '#e34f45')]
        original = canvas.rendered().copy()
        before = canvas.scale()
        canvas.set_zoom(1.)
        self.assertLess(before, 1)
        self.assertEqual(canvas.image_rect().width(), 3840)
        canvas.pan = QPointF(200, 100)
        canvas.clamp_pan()
        rect = canvas.image_rect()
        point = QPointF(rect.x() + 250, rect.y() + 200)
        self.assertEqual(canvas.image_point(point), QPointF(250, 200))
        self.assertEqual(canvas.rendered(), original)
        self.assertEqual(canvas.image, image)
        canvas.set_zoom()
        self.assertEqual(canvas.pan, QPointF())
        self.assertEqual(canvas.rendered(), original)

    def test_copy_failure_can_retry_without_duplicate_and_save_after_edit(self):
        image = QImage(300, 200, QImage.Format.Format_ARGB32)
        image.fill(QColor('blue'))
        controller = SimpleNamespace(settings={'directory': str(self.root / 'captures')}, last_saved=None, notify=lambda *a: None)
        editor = CaptureEditor(image, controller)
        with patch('document_assistant.screen_capture.copy_image', side_effect=OSError('clipboard busy')):
            editor.save()
            first = controller.last_saved
            self.assertTrue(first.is_file())
            self.assertTrue(editor.save_button.isEnabled())
            editor.save()
            self.assertEqual(len(list(first.parent.glob('*.png'))), 1)
            editor.canvas.marks.append(('rectangle', QPointF(10, 10), QPointF(80, 80), '', '#e34f45'))
            editor.canvas.changed.emit()
            editor.save()
            self.assertNotEqual(controller.last_saved, first)
            self.assertEqual(len(list(first.parent.glob('*.png'))), 2)
            self.assertNotEqual(QImage(str(first)), QImage(str(controller.last_saved)))
        editor.reject()

    def test_hotkey_finish_restores_target_without_activating_workbench(self):
        calls = []
        window = SimpleNamespace(setAttribute=lambda *a: calls.append(a), show=lambda: calls.append('show'))
        controller = SimpleNamespace(
            editor=None,
            capturing=True,
            restore_main=True,
            exiting=False,
            from_hotkey=True,
            previous_foreground=123,
            window=window,
            show_main=lambda: calls.append('activate-main'),
            long_capture=None,
            long_stop=None,
        )
        with patch('document_assistant.screen_capture.restore_foreground') as restore:
            CaptureController.finished(controller)
            self.app.processEvents()
            restore.assert_called_once_with(123)
        self.assertNotIn('activate-main', calls)
        self.assertIn((Qt.WidgetAttribute.WA_ShowWithoutActivating, True), calls)

    def test_hotkey_status_is_honest(self):
        window = MainWindow(self.root / 'settings')
        controller = CaptureController(window, activate=False)
        self.assertIn('未启用', window.screenshot_button.text())
        self.assertIn('未启用', window.hotkey_badge.text())
        controller.shutdown()
        window.close()
        self.app.processEvents()

    def test_studio_window_launches_long_and_video_modes_and_syncs_audio(self):
        window = MainWindow(self.root / 'settings')
        window.capture_controller = CaptureController(window, activate=False)
        controller = window.capture_controller
        screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 800, 600), availableGeometry=lambda: QRect(0, 0, 800, 580))
        image = QImage(800, 600, QImage.Format.Format_RGB32)
        image.fill(QColor('#112233'))
        try:
            window.audio_buttons['system'].click()
            self.assertEqual(controller.video_audio_mode, 'system')

            with patch('document_assistant.screen_capture.QTimer.singleShot', side_effect=lambda _ms, fn: fn()), \
                 patch.object(controller.app, 'screens', return_value=[screen]), \
                 patch.object(controller, 'snapshot', wraps=lambda frames=None: CaptureController.snapshot(controller, [(screen, image)])) as snap:
                window.take_long_screenshot()
                self.assertTrue(snap.called)
                self.assertEqual(controller.overlays[0].mode, 'long')
                controller.cancel()

                window.take_video_recording()
                self.assertEqual(controller.overlays[0].mode, 'video')
                self.assertEqual(controller.overlays[0].video_audio_mode, 'system')
                controller.cancel()
        finally:
            controller.cancel()
            controller.shutdown()
            window.close()
            self.app.processEvents()

    def test_studio_window_lists_recent_captures_and_copies_png(self):
        home = self.root / 'settings'
        home.mkdir(parents=True, exist_ok=True)
        captures = self.root / 'captures'
        captures.mkdir(parents=True, exist_ok=True)
        (home / 'screenshot.json').write_text(
            json.dumps({'hotkey': 'Alt+S', 'directory': str(captures)}),
            encoding='utf-8',
        )
        png_path = captures / '截图_20261126_100000.png'
        img = QImage(40, 30, QImage.Format.Format_ARGB32)
        img.fill(QColor('#2c81ac'))
        self.assertTrue(img.save(str(png_path), 'PNG'))
        mp4_path = captures / '录屏_20261126_100100.mp4'
        mp4_path.write_bytes(b'synthetic-mp4')

        window = MainWindow(home)
        try:
            self.assertEqual(window.recent_count.text(), '最近 2 项')
            window.copy_recent_image(png_path)
            self.assertEqual(self.app.clipboard().image().size(), img.size())
        finally:
            window.close()
            self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
