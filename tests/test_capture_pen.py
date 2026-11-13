import unittest
from types import SimpleNamespace
from PySide6.QtCore import QPoint,QPointF,QRect,Qt
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from document_assistant.selection_overlay import SelectionOverlay
from document_assistant.capture_markup import render_annotations,mark_bounds
from document_assistant.capture_tools import normalize_tools
from document_assistant.long_editor import LongImageEditor

class PenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def image(self,w=1280,h=720):
        image=QImage(w,h,QImage.Format.Format_ARGB32);image.fill(QColor('white'));return image

    def overlay(self,w=1280):
        overlay=SelectionOverlay(SimpleNamespace(geometry=lambda:QRect(0,0,w,720)),self.image(w))
        overlay.show();overlay.begin_drag(QPointF(40,80));overlay.end_drag(QPointF(w-40,430))
        self.app.processEvents();self.addCleanup(overlay.close);return overlay

    def stroke(self,canvas,points):
        QTest.mousePress(canvas,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,points[0])
        for point in points[1:]:QTest.mouseMove(canvas,point)
        QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,points[-1])
        self.app.processEvents()

    def test_pen_follows_all_bends_not_endpoint_chord_and_preserves_source(self):
        image=self.image(240,240);before=image.copy()
        mark=('pen',QPointF(40,40),QPointF(160,160),'','#377fde',{'width':8,'path':[(0,0),(120,0),(120,120)]})
        result=render_annotations(image,[mark])
        self.assertEqual(result.pixelColor(100,40),QColor('#377fde'))
        self.assertEqual(result.pixelColor(160,100),QColor('#377fde'))
        self.assertEqual(result.pixelColor(100,100),QColor('white'))
        self.assertEqual(image,before)
        self.assertTrue(mark_bounds(mark,image.size()).contains(QPointF(100,40)))

    def test_click_dot_closed_stroke_undo_redo_and_hit_testing(self):
        overlay=self.overlay();overlay.set_tool('pen');overlay.change_style(color='#377fde',width=7)
        canvas=overlay.canvas
        points=[QPoint(70,70),QPoint(200,70),QPoint(200,180),QPoint(70,180),QPoint(70,70)]
        self.stroke(canvas,points)
        self.assertEqual(len(canvas.marks),1)
        self.assertGreaterEqual(len(canvas.marks[0][5]['path']),5)
        result=canvas.rendered().copy();self.assertEqual(canvas.pick(QPointF(130,70)),0)
        self.assertIsNone(canvas.pick(QPointF(130,130)))
        canvas.undo();self.assertEqual(canvas.marks,[]);canvas.redo();self.assertEqual(canvas.rendered(),result)
        self.stroke(canvas,[QPoint(300,200)])
        self.assertEqual(len(canvas.marks),2)
        self.assertEqual(canvas.rendered().pixelColor(300,200),QColor('#377fde'))

    def test_pen_style_is_independent_and_compatible_with_existing_settings(self):
        prefs=normalize_tools({'rectangle':{'color':'#24825c','width':5}})
        self.assertEqual(prefs['pen'],{'color':'#e34f45','width':3})
        overlay=self.overlay();overlay.set_tool('pen');overlay.change_style(color='#377fde',width=9)
        overlay.set_tool('rectangle');self.assertEqual(overlay.width_spin.value(),3)
        overlay.set_tool('pen');self.assertEqual(overlay.width_spin.value(),9)
        self.assertTrue(overlay.color_buttons[2].isChecked())

    def test_modes_are_to_right_of_editing_actions_when_inline(self):
        overlay=self.overlay(1600)
        for tool in ('view','pen','mask','text'):
            overlay.set_tool(tool);overlay.position_actions();self.app.processEvents()
            self.assertFalse(overlay._modes_stacked)
            self.assertGreaterEqual(overlay.modes.x(),overlay.save_button.geometry().right())
            self.assertGreater(overlay.cancel_button.x(),overlay.modes.geometry().right())

    def test_right_aligned_stacked_modes_and_controls_remain_reachable(self):
        for width in (640,800,948,1280):
            overlay=self.overlay(width)
            for mode in ('photo','video','long'):
                overlay.set_mode(mode)
                for tool in (('pen','mask','text') if mode=='photo' else ('view',)):
                    if mode=='photo':overlay.set_tool(tool)
                    overlay.position_actions();self.app.processEvents()
                    self.assertTrue(overlay.rect().contains(overlay.actions.geometry()))
                    widgets=[*overlay.mode_buttons.values(),overlay.confirm_button,overlay.cancel_button]
                    if mode=='photo':widgets += list(overlay.tool_buttons.values())+[overlay.save_button]
                    for widget in widgets:
                        rect=QRect(widget.mapTo(overlay.actions,QPoint()),widget.size())
                        self.assertTrue(overlay.actions.rect().contains(rect),(width,mode,tool,widget.toolTip(),rect))
                    if overlay._modes_stacked:
                        self.assertGreater(overlay.modes.y(),overlay.confirm_button.y())
                        self.assertLessEqual(overlay.actions.width()-overlay.modes.geometry().right(),14)
            overlay.close()

    def test_long_preview_pen_uses_same_pixel_stroke_and_undo(self):
        controller=SimpleNamespace(tool_preferences={},is_desktop_destination=lambda:True,remember_tools=lambda _:None)
        editor=LongImageEditor(self.image(600,1000),controller);self.addCleanup(editor.close)
        editor.show();self.app.processEvents();editor.actual();editor.set_tool('pen')
        editor.style(color='#24825c',width=5)
        self.stroke(editor.canvas,[QPoint(70,70),QPoint(150,120),QPoint(230,70)])
        self.assertEqual(len(editor.canvas.marks),1)
        image=editor.canvas.rendered().copy();editor.canvas.undo();editor.canvas.redo()
        self.assertEqual(editor.canvas.rendered(),image)

    def test_pen_pixels_follow_native_scale_and_can_move_with_undo(self):
        for ratio in (1,1.5,2):
            overlay=SelectionOverlay(SimpleNamespace(geometry=lambda:QRect(0,0,1000,720)),self.image(int(1000*ratio),int(720*ratio)))
            self.addCleanup(overlay.close);overlay.show()
            overlay.begin_drag(QPointF(40,80));overlay.end_drag(QPointF(900,430));overlay.set_tool('pen')
            overlay.change_style(color='#377fde',width=6)
            self.stroke(overlay.canvas,[QPoint(100,100),QPoint(200,100)])
            mark=overlay.canvas.marks[0]
            self.assertEqual(mark[1],QPointF(100*ratio,100*ratio))
            self.assertEqual(overlay.canvas.rendered().pixelColor(round(150*ratio),round(100*ratio)),QColor('#377fde'))
            before=overlay.canvas.rendered().copy();overlay.set_tool('select')
            self.stroke(overlay.canvas,[QPoint(150,100),QPoint(150,130)])
            self.assertAlmostEqual(overlay.canvas.marks[0][1].y(),130*ratio)
            overlay.canvas.undo();self.assertEqual(overlay.canvas.rendered(),before)
            overlay.close()
