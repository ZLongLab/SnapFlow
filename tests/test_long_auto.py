import unittest
from tests import test_capture_unified as shared
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint,QPointF,Qt
from PySide6.QtTest import QTest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtCore import QRect
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

class AutoLongTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    overlay=shared.UnifiedCaptureToolbarTests.overlay
    select=shared.UnifiedCaptureToolbarTests.select
    def test_click_long_after_selection_starts_once_without_confirm(self):
        overlay=self.overlay();self.select(overlay);calls=[]
        overlay.long_selected.connect(calls.append)
        QTest.mouseClick(overlay.mode_buttons['long'],Qt.MouseButton.LeftButton)
        self.assertEqual(calls,[overlay.selection_rect()]);self.assertTrue(overlay.selection_locked)
        overlay.confirm();overlay.set_mode('long',True)
        self.assertEqual(len(calls),1)

    def test_choose_long_then_release_selection_starts_once(self):
        overlay=self.overlay();calls=[];overlay.long_selected.connect(calls.append)
        QTest.mouseClick(overlay.mode_buttons['long'],Qt.MouseButton.LeftButton)
        self.assertEqual(calls,[])
        QTest.mousePress(overlay,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(80,100))
        QTest.mouseMove(overlay,QPoint(600,400))
        QTest.mouseRelease(overlay,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(600,400))
        self.assertEqual(len(calls),1);self.assertTrue(overlay.selection_locked)

    def test_small_region_can_be_reselected_before_start(self):
        overlay=self.overlay();calls=[];overlay.long_selected.connect(calls.append)
        overlay.begin_drag(QPointF(70,100));overlay.end_drag(QPointF(100,120))
        QTest.mouseClick(overlay.mode_buttons['long'],Qt.MouseButton.LeftButton)
        self.assertEqual(calls,[]);self.assertFalse(overlay.selection_locked)
        self.assertIn('80',overlay.error_text)
        overlay.begin_drag(QPointF(400,150));overlay.end_drag(QPointF(700,430))
        self.assertEqual(len(calls),1)

    def test_photo_and_video_still_wait_for_explicit_confirmation(self):
        overlay=self.overlay();calls=[];overlay.video_selected.connect(calls.append)
        self.select(overlay);self.assertFalse(overlay.selection_locked)
        QTest.mouseClick(overlay.mode_buttons['video'],Qt.MouseButton.LeftButton)
        self.assertEqual(calls,[]);overlay.confirm();self.assertEqual(len(calls),1)

    def test_click_enters_controller_and_starts_timer_without_second_action(self):
        from document_assistant.screen_capture import CaptureController
        overlay=self.overlay();self.select(overlay);screen=overlay.screen_ref
        screen.availableGeometry=lambda:QRect(0,0,948,650)
        screen.devicePixelRatio=lambda:1.
        screen.grabWindow=lambda handle,x=0,y=0,w=948,h=650:QPixmap.fromImage(overlay.image.copy(x,y,w,h))
        window=QWidget();self.addCleanup(window.close)
        controller=SimpleNamespace(window=window,long_capture=None,recording=None,hotkey=SimpleNamespace(ident=None),overlays=[overlay],long_stop=None,tray=None,from_hotkey=False,
                                   long_completed=Mock(),long_failed=Mock(),long_cancelled=Mock())
        controller.close_overlays=lambda:(overlay.hide(),controller.overlays.clear())
        overlay.long_selected.connect(lambda rect:CaptureController.begin_long(controller,screen,rect))
        with patch('document_assistant.long_capture.CaptureKeys'):
            QTest.mouseClick(overlay.mode_buttons['long'],Qt.MouseButton.LeftButton)
            self.assertIsNotNone(controller.long_capture)
            self.addCleanup(controller.long_capture.cancel)
            QTest.qWait(150)
            self.assertIsNotNone(controller.long_capture.stitcher)
            self.assertTrue(controller.long_capture.timer.isActive())
            controller.long_failed.assert_not_called()
