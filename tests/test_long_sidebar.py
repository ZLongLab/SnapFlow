import unittest,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QRect,QRectF
from PySide6.QtGui import QPainter,QColor
from PySide6.QtWidgets import QApplication
from tests.test_long_capture import make_page
from document_assistant.long_stitch import VerticalStitcher
from document_assistant.long_capture import LongCaptureSession

class SidebarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([]);cls.page=make_page()
    def frame(self,y,seed=None):
        image=(self.page if seed is None else make_page(seed=seed)).copy(0,y,900,700)
        p=QPainter(image);p.fillRect(600,0,300,700,QColor('white'));p.setPen(QColor('#333333'))
        for row in range(18):p.drawText(620,30+row*34,f'固定侧栏 sidebar {row} unchanged')
        p.end();return image
    def test_pause_and_reverse_with_fixed_sidebar(self):
        s=VerticalStitcher(self.frame(300))
        for y in (325,380,480,480,410,200):
            result=s.append(self.frame(y));self.assertNotEqual(result.status,'no_overlap')
            self.assertEqual(s.position,y-300)
        self.assertEqual(s.height,980)
        self.assertEqual(s.image().copy(0,0,590,980),self.page.copy(0,200,590,980))
    def test_unrelated_article_with_same_fixed_sidebar_is_rejected(self):
        s=VerticalStitcher(self.frame(300));before=s.image()
        self.assertEqual(s.append(self.frame(380,seed=999)).status,'no_overlap');self.assertEqual(s.image(),before)
    def test_gap_is_rejected_despite_shared_sidebar(self):
        self.assertEqual(VerticalStitcher(self.frame(0)).append(self.frame(1500)).status,'no_overlap')
    def test_unrelated_replaced_sidebar_is_not_silently_ignored(self):
        image=self.frame(380);p=QPainter(image);p.fillRect(600,0,300,700,QColor('black'));p.end()
        self.assertEqual(VerticalStitcher(self.frame(300)).append(image).status,'no_overlap')
    def test_live_preview_follows_parts_and_stays_outside_capture(self):
        current=[self.frame(300)]
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,1280,800),availableGeometry=lambda:QRect(0,0,1280,800))
        from PySide6.QtGui import QImage
        def grab():
            full=QImage(1280,800,QImage.Format.Format_RGB32);full.fill(QColor('white'))
            p=QPainter(full);p.drawImage(0,0,current[0]);p.end();return full
        session=LongCaptureSession(screen,QRectF(0,0,900,700),'测试',grabber=grab)
        self.addCleanup(session.cancel)
        with patch('document_assistant.long_capture.CaptureKeys'):session.start()
        session.timer.stop();self.assertTrue(session.preview.isVisible())
        self.assertFalse(QRectF(session.preview.geometry()).intersects(session.global_rect))
        current[0]=self.frame(380);session.preview_updated=0;session.poll()
        self.assertEqual(session.stitcher.height,780);self.assertEqual(session.preview.total,780)
        self.assertEqual(len(session.preview.parts),2)
