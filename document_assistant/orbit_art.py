"""Native Orbit artwork adapted from the provided HTML; no remote resources."""
from pathlib import Path
from PySide6.QtCore import QRectF,Qt
from PySide6.QtGui import QColor,QPainter,QPen,QRadialGradient,QLinearGradient
from PySide6.QtSvg import QSvgRenderer
from .cards import ShelfArtwork

class OrbitSidebar(ShelfArtwork):
    def __init__(self):
        super().__init__();self.renderer=QSvgRenderer(str(Path(__file__).with_name('orbit-sidebar.svg')))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    def paintEvent(self,event):
        from .theme import CURRENT_THEME
        if CURRENT_THEME!='starry':
            from .theme_variants import draw_light_emblem
            painter=QPainter(self);draw_light_emblem(painter,QRectF(self.rect()),CURRENT_THEME);painter.end();return
        if self.height()<90:return
        p=QPainter(self);size=min(184,self.width(),self.height())
        self.renderer.render(p,QRectF((self.width()-size)/2,(self.height()-size)/2,size,size));p.end()

def draw_orbit_sky(image,stars):
    w,h=image.width(),image.height();p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing)
    base=QLinearGradient(0,0,0,h);base.setColorAt(0,QColor('#101d30'));base.setColorAt(.7,QColor('#132239'));base.setColorAt(1,QColor('#0b1526'));p.fillRect(image.rect(),base)
    for x,y,r,color in ((.68,.22,.55,'#243e5e'),(.5,.8,.48,'#172c47')):
        glow=QRadialGradient(w*x,h*y,w*r);c=QColor(color);c.setAlpha(110)
        glow.setColorAt(0,c);glow.setColorAt(1,QColor(0,0,0,0));p.fillRect(image.rect(),glow)
    for x,y,r,b in stars:
        px,py=x*w,y*h
        if b>.78:
            halo=QRadialGradient(px,py,9+b*6);halo.setColorAt(0,QColor(200,227,255,75));halo.setColorAt(1,QColor(160,210,255,0))
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(halo);p.drawEllipse(QRectF(px-16,py-16,32,32))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(220,234,253,int(45+b*145)));p.drawEllipse(QRectF(px-r/2,py-r/2,r,r))
    cx=224+(w-224)*.53;cy=h*.52;span=max(420,w-224)
    for rx,ry,tilt in ((.48,.29,-13),(.4,.25,16),(.52,.33,-5)):
        p.save();p.translate(cx,cy);p.rotate(tilt);p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(215,228,251,23),.8));p.drawEllipse(QRectF(-span*rx,-h*ry,2*span*rx,2*h*ry));p.restore()
    for x,y,color in ((.88,.22,'#38bdf8'),(.96,.22,'#f59e0b'),(.70,.31,'#10b981'),(.67,.1,'#e2e8f0')):
        x=224+(w-224)*x;y=h*y;c=QColor(color);glow=QRadialGradient(x,y,26);c.setAlpha(60)
        glow.setColorAt(0,c);glow.setColorAt(1,QColor(0,0,0,0));p.setPen(Qt.PenStyle.NoPen);p.setBrush(glow);p.drawEllipse(QRectF(x-26,y-26,52,52))
        c=QColor(color);c.setAlpha(150);p.setPen(QPen(c,.8));p.setBrush(QColor('#0b1625'));p.drawEllipse(QRectF(x-12,y-12,24,24))
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(color));p.drawEllipse(QRectF(x-2,y-2,4,4))
    p.end()
