import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QRect, QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication
from tests.capture_fixture import TempFixture as Fixture
from tests.test_long_capture import make_page
from document_assistant.gui import MainWindow
from document_assistant.long_capture import LongCaptureSession
from document_assistant.long_stitch import VerticalStitcher
from document_assistant.screen_capture import CaptureController


def _composite_sticky_frame(body_page, scroll_y, view_h=600, header_h=64, footer_h=60):
    w = body_page.width()
    frame = QImage(w, view_h, QImage.Format.Format_RGB32)
    p = QPainter(frame)
    # Moving interior body
    body_h = view_h - header_h - footer_h
    p.drawImage(0, header_h, body_page.copy(0, scroll_y, w, body_h))
    # Fixed top header
    p.fillRect(0, 0, w, header_h, QColor('#1e293b'))
    p.setPen(QColor('#f8fafc'))
    p.drawText(20, 38, 'FIXED TOP HEADER BAR')
    # Fixed bottom footer
    p.fillRect(0, view_h - footer_h, w, footer_h, QColor('#f1f5f9'))
    p.setPen(QColor('#0f172a'))
    p.drawText(20, view_h - 24, 'FIXED BOTTOM INPUT BAR')
    p.end()
    return frame


class LongAndTrayImprovementsTests(Fixture):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.page = make_page(900, 3000)

    def test_sticky_header_and_footer_stitch_cleanly_without_duplication(self):
        f0 = _composite_sticky_frame(self.page, 0)
        f1 = _composite_sticky_frame(self.page, 200)
        f2 = _composite_sticky_frame(self.page, 400)

        stitcher = VerticalStitcher(f0)
        r1 = stitcher.append(f1)
        r2 = stitcher.append(f2)
        self.assertEqual((r1.status, r1.added), ('appended', 200))
        self.assertEqual((r2.status, r2.added), ('appended', 200))

        out = stitcher.image()
        self.assertEqual(out.height(), 600 + 400)
        # Header kept once at top, footer kept once at bottom, no footer bar inside middle body
        self.assertEqual(out.copy(0, 0, 900, 64), f0.copy(0, 0, 900, 64))
        self.assertEqual(out.copy(0, out.height() - 60, 900, 60), f2.copy(0, 540, 900, 60))
        # Middle slice matches scrolled body pixels (header_h=64 + 476 body = 540, which in raw body_page is offset 476)
        self.assertEqual(out.copy(0, 64, 900, 876), self.page.copy(0, 0, 900, 876))

    def test_subpixel_tint_with_zero_exact_rows_still_matches(self):
        first = self.page.copy(0, 0, 900, 900)
        shifted = self.page.copy(0, 220, 900, 900)
        p = QPainter(shifted)
        p.fillRect(shifted.rect(), QColor(255, 255, 255, 3))
        p.end()
        stitcher = VerticalStitcher(first)
        res = stitcher.append(shifted)
        self.assertEqual((res.status, res.added), ('appended', 220))

    def test_auto_scroll_ticks_and_stops_at_bottom(self):
        current = [self.page.copy(0, 0, 900, 900)]
        screen = SimpleNamespace(geometry=lambda: QRect(0, 0, 900, 900), availableGeometry=lambda: QRect(0, 0, 900, 1100))
        ticks = []
        with patch('document_assistant.long_capture.CaptureKeys'):
            session = LongCaptureSession(
                screen, QRectF(0, 0, 900, 900), 'Alt+A',
                grabber=lambda: current[0],
                wheel_scroller=lambda: ticks.append(1),
            )
            self.addCleanup(session.cancel)
            session.start()
            session.timer.stop()
            session._auto_timer.stop()

            session.set_auto_scroll(True)
            self.assertTrue(session.auto_scrolling)
            self.assertTrue(session.controls.auto_scroll_button.isChecked())
            session._auto_scroll_step()
            self.assertEqual(len(ticks), 1)

            for _ in range(60):
                session.poll()
            self.assertFalse(session.auto_scrolling)
            self.assertFalse(session.controls.auto_scroll_button.isChecked())
            self.assertIn('底部', session.controls.status.text())

    def test_tray_menu_hides_inactive_items_and_follows_theme(self):
        window = MainWindow(self.root / 'settings')
        controller = CaptureController(window, activate=False)
        try:
            menu = controller._build_tray_menu()
            controller._prepare_tray_menu()
            self.assertFalse(controller.video_stop.isVisible())
            self.assertFalse(controller.long_stop.isVisible())
            self.assertFalse(controller.pin_clear.isVisible())
            self.assertFalse(controller.act_last_img.isVisible())
            self.assertIn('#ffffff', menu.styleSheet())

            png = self.root / 'shot.png'
            self.page.copy(0, 0, 100, 100).save(str(png), 'PNG')
            controller.last_saved = png
            controller.pins.append(SimpleNamespace(close=lambda: None))
            window.toggle_theme()
            controller._prepare_tray_menu()
            self.assertTrue(controller.act_last_img.isVisible())
            self.assertTrue(controller.pin_clear.isVisible())
            self.assertIn('#1c2537', menu.styleSheet())
            controller.pins.clear()
        finally:
            controller.shutdown()
            window.close()
            self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
