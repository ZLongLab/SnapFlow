import json
import unittest
from types import SimpleNamespace
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from tests.capture_fixture import TempFixture as Fixture
from document_assistant.capture_beautify import BEAUTIFY_PRESETS, BeautifyDialog, render_beautified
from document_assistant.capture_canvas import AnnotationCanvas
from document_assistant.capture_markup import render_annotations
from document_assistant.capture_pin import PinnedImageWindow
from document_assistant.gui import MainWindow
from document_assistant.screen_capture import CaptureController
from document_assistant.selection_overlay import SelectionOverlay


class SnapFlowFeaturesTests(Fixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_beautify_presets_ratio_chrome_and_source_immutability(self):
        source = QImage(300, 180, QImage.Format.Format_ARGB32)
        source.fill(QColor('#1e293b'))
        snapshot = source.copy()

        for preset in BEAUTIFY_PRESETS:
            out = render_beautified(source, {'preset': preset['id'], 'padding': 40, 'radius': 12, 'shadow': 20})
            self.assertEqual(out.width(), 380)
            self.assertEqual(out.height(), 260)
            self.assertEqual(out.devicePixelRatio(), 1)
            if preset.get('transparent'):
                self.assertEqual(out.pixelColor(2, 2).alpha(), 0)
            else:
                self.assertEqual(out.pixelColor(2, 2).alpha(), 255)

        wide = render_beautified(source, {'ratio': '16:9', 'window_chrome': True, 'padding': 30})
        self.assertAlmostEqual(wide.width() / wide.height(), 16 / 9, places=1)
        self.assertEqual(source, snapshot)

        dialog = BeautifyDialog(source)
        self.assertEqual(dialog.rendered_image.width(), 300 + 56 * 2)
        dialog.close()

    def test_pin_window_zoom_opacity_reset_and_controller_tracking(self):
        image = QImage(240, 160, QImage.Format.Format_ARGB32)
        image.fill(QColor('#3b82f6'))
        window = MainWindow(self.root / 'settings')
        controller = CaptureController(window, activate=False)
        try:
            pin = controller.pin_image(image)
            self.assertIn(pin, controller.pins)
            pin.set_zoom(2.0)
            self.assertEqual(pin.zoom, 2.0)
            pin.set_zoom(10.0)
            self.assertEqual(pin.zoom, 3.0)
            pin.set_opacity_level(0.5)
            self.assertEqual(pin.opacity_level, 0.5)
            pin.set_opacity_level(0.05)
            self.assertEqual(pin.opacity_level, 0.25)
            pin.reset_view()
            self.assertEqual((pin.zoom, pin.opacity_level), (1.0, 1.0))
            controller.close_all_pins()
            self.app.processEvents()
        finally:
            controller.shutdown()
            window.close()
            self.app.processEvents()

    def test_step_badges_and_translucent_highlighter_render_and_undo(self):
        image = QImage(320, 220, QImage.Format.Format_ARGB32)
        image.fill(QColor('white'))
        canvas = AnnotationCanvas(image)
        canvas.resize(400, 300)
        canvas.show()
        self.app.processEvents()

        canvas.tool = 'step'
        canvas.append_mark(canvas.new_mark(QPointF(60, 60), QPointF(60, 60)))
        canvas.append_mark(canvas.new_mark(QPointF(140, 60), QPointF(140, 60)))
        self.assertEqual([m[3] for m in canvas.marks], ['1', '2'])

        canvas.tool = 'highlighter'
        canvas.color = '#ec9b21'
        canvas.stroke = [QPointF(40, 140), QPointF(220, 140)]
        canvas.append_mark(canvas.new_mark(canvas.stroke[0], canvas.stroke[-1]))

        rendered = canvas.rendered()
        pixel = rendered.pixelColor(130, 140)
        # Translucent orange over white should blend cleanly (neither solid white nor solid black)
        self.assertGreater(pixel.red(), 200)
        self.assertLess(pixel.blue(), 200)
        self.assertIsNotNone(canvas.pick(QPointF(60, 60)))
        self.assertIsNotNone(canvas.pick(QPointF(130, 140)))

        canvas.undo()
        self.assertEqual(len(canvas.marks), 2)
        canvas.close()

    def test_overlay_eyedropper_samples_and_copies_hex_on_c_key(self):
        image = QImage(400, 300, QImage.Format.Format_ARGB32)
        image.fill(QColor('#1a73e8'))
        screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 400, 300))
        overlay = SelectionOverlay(screen, image)
        picked = []
        overlay.color_picked.connect(picked.append)
        overlay.show()
        self.app.processEvents()
        overlay.hover_pos = QPointF(120, 120)
        self.assertEqual(overlay.sample_color().name().upper(), '#1A73E8')
        QTest.keyClick(overlay, Qt.Key.Key_C)
        self.assertEqual(picked, ['#1A73E8'])
        self.assertEqual(self.app.clipboard().text(), '#1A73E8')
        overlay.close()

    def test_gallery_filters_and_cards_render_cleanly(self):
        home = self.root / 'settings'
        home.mkdir(parents=True, exist_ok=True)
        captures = self.root / 'captures'
        captures.mkdir(parents=True, exist_ok=True)
        (home / 'screenshot.json').write_text(json.dumps({'hotkey': 'Alt+A', 'directory': str(captures)}), encoding='utf-8')

        img = QImage(160, 100, QImage.Format.Format_ARGB32)
        img.fill(QColor('#2563eb'))
        img.save(str(captures / 'shot_1.png'), 'PNG')
        (captures / 'rec_1.mp4').write_bytes(b'synthetic-video')

        window = MainWindow(home)
        try:
            self.assertEqual(window.recent_count.text(), '最近 2 项')
            window.set_gallery_filter('image')
            self.assertEqual(window.recent_count.text(), '最近 1 项')
            window.set_gallery_filter('video')
            self.assertEqual(window.recent_count.text(), '最近 1 项')
            window.set_gallery_filter('all')
            self.assertEqual(len(window._gallery_cards), 2)
        finally:
            window.close()
            self.app.processEvents()

    def test_refresh_button_preserves_hotkey_and_theme_toggles(self):
        home = self.root / 'settings'
        home.mkdir(parents=True, exist_ok=True)
        empty = self.root / 'empty'
        empty.mkdir(parents=True, exist_ok=True)
        (home / 'screenshot.json').write_text(json.dumps({'hotkey': 'Alt+A', 'directory': str(empty)}), encoding='utf-8')

        window = MainWindow(home)
        try:
            self.assertEqual(window.theme_name, 'light')
            QTest.mouseClick(window.refresh_btn, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertIsNotNone(window.empty_title)
            self.assertIn('Alt+A', window.empty_title.text())
            self.assertNotIn('False', window.empty_title.text())

            window.toggle_theme()
            self.assertEqual(window.theme_name, 'dark')
            self.assertEqual(json.loads((home / 'ui.json').read_text(encoding='utf-8'))['theme'], 'dark')
        finally:
            window.close()
            self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
