"""Coordinated light glass materials for the existing ocean and rose themes."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath, QLinearGradient, QRadialGradient

PALETTES = {'ocean': {'sidebar': '#e9f3f8',
           'page_bg': '#edf5f9',
           'text': '#19334b',
           'muted': '#526d82',
           'nav_text': '#46667c',
           'nav_active': '#236b94',
           'sidebar_footer': '#e3eef5',
           'footer_text': '#526d82',
           'footer_hover': '#d5e7f2',
           'accent': '#247da4',
           'accent_light': '#dceef6',
           'primary_bg': '#246685',
           'primary_hover': '#317d9e',
           'addfile_bg': '#247da4',
           'addfile_hover': '#3597bd',
           'border': '#c6dce8',
           'card_border': '#d3e3ec',
           'selection_bg': '#dcecf5',
           'header_bg': '#e7f1f7',
           'sidebar_separator': '#c6dce8',
           'sidebar_footer_border': '#c6dce8',
           'statusbar_bg': '#e8f2f8',
           'statusbar_text': '#526d82',
           'input_focus': '#4b96b5'},
 'rose': {'sidebar': '#f7eeea',
          'page_bg': '#faf2ee',
          'text': '#4b3038',
          'muted': '#805f66',
          'nav_text': '#795761',
          'nav_active': '#a35c70',
          'sidebar_footer': '#f3e4de',
          'footer_text': '#805f66',
          'footer_hover': '#ebd8d4',
          'accent': '#b06b78',
          'accent_light': '#f2dfe2',
          'primary_bg': '#9d576d',
          'primary_hover': '#b36c81',
          'addfile_bg': '#b06b78',
          'addfile_hover': '#c17e8b',
          'border': '#e3c9c8',
          'card_border': '#ecd7d2',
          'selection_bg': '#f1e0e2',
          'header_bg': '#f7eae7',
          'sidebar_separator': '#e3c9c8',
          'sidebar_footer_border': '#e3c9c8',
          'statusbar_bg': '#f7ece6',
          'statusbar_text': '#805f66',
          'input_focus': '#b87f85'}}


def light_qss(c, name):
    end = '#409eb9' if name == 'ocean' else '#c78c80'
    return f'''
QFrame#sidebar, QFrame#sidebarFooter, QFrame#list, QFrame#workflowBand, QFrame#actionbar {{ background:transparent; border:0; border-radius:16px; }}
QFrame#sidebar {{ border-radius:0; }}
QFrame#topbar, QFrame#topbar[library="true"] {{ background:transparent; border:0; }}
QLabel#brand, QLabel#sidebarPath {{ color:{c['text']}; font-size:12px; }}
QLabel#sidebarNote {{ color:{c['muted']}; font-size:12px; }}
QLabel#pageTitle {{ font-family:"Noto Serif SC","SimSun"; color:{c['text']}; font-size:28px; font-weight:600; }}
QLabel#subtitle, QLabel#muted {{ color:{c['muted']}; font-size:13px; }}
QPushButton {{ background:rgba(255,255,255,170); border:1px solid {c['border']}; border-radius:9px; color:{c['text']}; }}
QPushButton:hover {{ background:rgba(255,255,255,240); border-color:{c['accent']}; }}
QPushButton:focus {{ border-color:{c['input_focus']}; }}
QPushButton#nav {{ background:transparent; text-align:left; font-size:13px; color:{c['nav_text']}; border:1px solid transparent; padding:10px 12px; }}
QPushButton#nav:hover {{ background:{c['accent_light']}; }}
QPushButton#nav:checked {{ background:{c['nav_active']}; color:white; border-color:{c['nav_active']}; }}
QPushButton#primary, QPushButton#addFile, QPushButton[prominent="true"] {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {c['primary_bg']},stop:1 {end}); color:white; border:1px solid transparent; border-radius:14px; font-weight:600; }}
QPushButton#primary:hover, QPushButton#addFile:hover {{ background:{c['primary_hover']}; }}
QPushButton:disabled, QPushButton#primary:disabled, QPushButton#addFile:disabled {{ background:{c['disabled_bg']}; color:{c['disabled_text']}; border-color:transparent; }}
QPushButton#captureLaunch, QPushButton#captureLaunch[secondary="true"] {{ text-align:left; background:rgba(255,255,255,90); color:{c['text']}; border:1px solid {c['border']}; font-size:13px; }}
QPushButton#footerAction {{ background:transparent; border:0; color:{c['footer_text']}; text-align:left; }}
QPushButton#footerAction:hover {{ background:{c['footer_hover']}; }}
QLineEdit, QComboBox, QPlainTextEdit, QSpinBox {{ background:rgba(255,255,255,205); color:{c['text']}; border:1px solid {c['border']}; border-radius:8px; }}
QLineEdit:focus, QComboBox:focus {{ border-color:{c['input_focus']}; }}
QTableWidget#libraryTable {{ background:transparent; alternate-background-color:rgba(255,255,255,25); border:0; gridline-color:transparent; }}
QTableWidget#libraryTable::item {{ border:0; border-bottom:1px solid {c['card_border']}; }}
QTableWidget#libraryTable::item:selected {{ background:{c['selection_bg']}; color:{c['text']}; }}
QHeaderView::section, QTableWidget#libraryTable QHeaderView::section {{ background:transparent; color:{c['muted']}; border:0; border-bottom:1px solid {c['border']}; font-size:11px; padding:7px 12px; }}
QStatusBar {{ background:{c['statusbar_bg']}; color:{c['statusbar_text']}; border:0; }}
'''

def draw_light_sky(image, name):
    width, height = image.width(), image.height()
    rose = name == 'rose'
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    base = QLinearGradient(0, 0, width, height)
    stops = (
        (0, '#faf3ed' if rose else '#eaf4fa'),
        (.52, '#f8e8e5' if rose else '#eff8fa'),
        (1, '#f8f2e8' if rose else '#e0edf6'),
    )
    for position, color in stops:
        base.setColorAt(position, QColor(color))
    painter.fillRect(image.rect(), base)
    lights = (
        (.78, .12, (211, 151, 143) if rose else (95, 173, 208)),
        (.22, .85, (226, 191, 129) if rose else (102, 191, 195)),
    )
    for x, y, rgb in lights:
        glow = QRadialGradient(width * x, height * y, width * .58)
        glow.setColorAt(0, QColor(*rgb, 48))
        glow.setColorAt(1, QColor(*rgb, 0))
        painter.fillRect(image.rect(), glow)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if rose:
        painter.save()
        painter.translate(width * .77, height * .46)
        painter.rotate(-25)
        for index in range(5):
            painter.setPen(QPen(QColor(175, 125, 78, 24 + index * 3), .8))
            painter.drawEllipse(QRectF(
                -width * (.38 + index * .025), -height * (.18 + index * .025),
                width * (.76 + index * .05), height * (.36 + index * .05),
            ))
        painter.restore()
    else:
        for index in range(8):
            path = QPainterPath()
            path.moveTo(-width * .1, height * (.48 + index * .045))
            path.cubicTo(
                width * .32, height * (.05 + index * .06),
                width * .6, height * (1.15 - index * .02),
                width * 1.1, height * (.42 + index * .05),
            )
            painter.setPen(QPen(QColor(44, 124, 167, 22 + index * 2), .8))
            painter.drawPath(path)
    painter.end()


def draw_light_emblem(painter, rect, name):
    rose = name == 'rose'
    size = min(170, rect.width(), rect.height())
    painter.save()
    painter.translate(rect.center())
    painter.scale(size / 180, size / 180)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    accent = QColor('#b46f7c' if rose else '#2e8db1')
    orbit_color = QColor('#bf965b' if rose else '#79b5c9')
    glow = QRadialGradient(0, 0, 78)
    translucent = QColor(accent)
    translucent.setAlpha(40)
    glow.setColorAt(0, translucent)
    glow.setColorAt(1, QColor(255, 255, 255, 0))
    painter.setBrush(glow)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(-78, -78, 156, 156))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for tilt in (-35, 35):
        painter.save()
        painter.rotate(tilt)
        translucent = QColor(orbit_color)
        translucent.setAlpha(130)
        painter.setPen(QPen(translucent, 1))
        painter.drawEllipse(QRectF(-74, -30, 148, 60))
        painter.restore()
    crystal = QPainterPath()
    crystal.moveTo(0, -45)
    crystal.lineTo(34, 0)
    crystal.lineTo(0, 45)
    crystal.lineTo(-34, 0)
    crystal.closeSubpath()
    gradient = QLinearGradient(-35, -40, 35, 45)
    gradient.setColorAt(0, QColor('#ffffff'))
    gradient.setColorAt(.5, QColor('#ead2c6' if rose else '#b3deed'))
    gradient.setColorAt(1, accent)
    painter.setPen(QPen(accent, .8))
    painter.setBrush(gradient)
    painter.drawPath(crystal)
    painter.drawLine(QPointF(0, -45), QPointF(0, 45))
    painter.drawLine(QPointF(-34, 0), QPointF(34, 0))
    painter.setBrush(orbit_color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(56, -33, 7, 7))
    painter.drawEllipse(QRectF(-65, 27, 5, 5))
    painter.restore()
