"""Shared Mist Light & Slate Dark styling for CaptureEditor, LongImageEditor, and VideoPreview."""
from pathlib import Path

_CHEVRON_UP = Path(__file__).with_name('chevron-up.svg').as_posix()
_CHEVRON_DOWN = Path(__file__).with_name('chevron-down.svg').as_posix()


def build_capture_qss(dark: bool = False) -> str:
    if dark:
        t = {
            'bg': '#131926',
            'surface': '#1a2233',
            'border': '#2b3850',
            'text': '#eef5fc',
            'title': '#f1f5f9',
            'muted': '#94a7c0',
            'badge_bg': '#202e47',
            'badge_fg': '#93c5fd',
            'group_bg': '#172031',
            'btn_bg': '#232e44',
            'btn_hover': '#2a3853',
            'btn_pressed': '#1e293b',
            'btn_border': '#33435e',
            'btn_hover_border': '#60a5fa',
            'disabled_fg': '#64748b',
            'disabled_bg': '#182032',
            'tool_hover': '#26344d',
            'tool_checked_bg': '#26344d',
            'tool_checked_border': '#4c72a8',
            'tool_checked_fg': '#ffffff',
            'primary': '#2563eb',
            'primary_hover': '#3b82f6',
            'primary_pressed': '#1d4ed8',
            'primary_disabled': '#334155',
            'cancel_fg': '#94a7c0',
            'cancel_hover': '#232e44',
            'err_bg': '#3b1d24',
            'err_fg': '#fca5a5',
            'input_bg': '#1d2638',
            'spin_btn': '#26344d',
            'tip_bg': '#1f293d',
        }
    else:
        t = {
            'bg': '#f3f6fb',
            'surface': '#ffffff',
            'border': '#dce5f2',
            'text': '#0f172a',
            'title': '#0f172a',
            'muted': '#64748b',
            'badge_bg': '#eff6ff',
            'badge_fg': '#2563eb',
            'group_bg': '#eef3f9',
            'btn_bg': '#ffffff',
            'btn_hover': '#eff6ff',
            'btn_pressed': '#dbeafe',
            'btn_border': '#d6e0ee',
            'btn_hover_border': '#60a5fa',
            'disabled_fg': '#94a3b8',
            'disabled_bg': '#f1f5f9',
            'tool_hover': '#e2ebf6',
            'tool_checked_bg': '#ffffff',
            'tool_checked_border': '#bfdbfe',
            'tool_checked_fg': '#2563eb',
            'primary': '#2563eb',
            'primary_hover': '#3b82f6',
            'primary_pressed': '#1d4ed8',
            'primary_disabled': '#93c5fd',
            'cancel_fg': '#64748b',
            'cancel_hover': '#e2e8f0',
            'err_bg': '#fef2f2',
            'err_fg': '#b91c1c',
            'input_bg': '#ffffff',
            'spin_btn': '#eef3f9',
            'tip_bg': '#0f172a',
        }

    return f"""
QDialog {{ background:{t['bg']}; }}
QWidget {{ font-family:'Microsoft YaHei UI'; font-size:13px; color:{t['text']}; }}
QFrame#captureHeader {{ background:{t['surface']}; border-bottom:1px solid {t['border']}; }}
QLabel#captureTitle {{ font-size:19px; font-weight:700; color:{t['title']}; background:transparent; }}
QLabel#captureMeta {{ color:{t['muted']}; font-size:12px; background:transparent; }}
QLabel#captureBadge {{ color:{t['badge_fg']}; background:{t['badge_bg']}; padding:6px 12px; border-radius:9px; font-size:12px; font-weight:600; }}
QFrame#toolGroup {{ background:{t['group_bg']}; border-radius:12px; }}
QPushButton {{ background:{t['btn_bg']}; color:{t['text']}; border:1px solid {t['btn_border']}; border-radius:10px; padding:8px 14px; font-weight:500; }}
QPushButton:hover {{ background:{t['btn_hover']}; border-color:{t['btn_hover_border']}; }}
QPushButton:pressed {{ background:{t['btn_pressed']}; }}
QPushButton:focus {{ border-color:#3b82f6; }}
QPushButton:disabled {{ color:{t['disabled_fg']}; background:{t['disabled_bg']}; border-color:{t['border']}; }}
QPushButton#zoomButton {{ padding:6px 8px; font-size:12px; }}
QPushButton#tool {{ border:1px solid transparent; background:transparent; border-radius:9px; padding:7px 8px; }}
QPushButton#tool:hover {{ background:{t['tool_hover']}; }}
QPushButton#tool:checked {{ background:{t['tool_checked_bg']}; border-color:{t['tool_checked_border']}; color:{t['tool_checked_fg']}; font-weight:600; }}
QPushButton#copyCapture {{ background:{t['primary']}; border-color:{t['primary']}; color:#ffffff; font-weight:600; padding:10px 20px; }}
QPushButton#copyCapture:hover {{ background:{t['primary_hover']}; border-color:{t['primary_hover']}; }}
QPushButton#copyCapture:pressed {{ background:{t['primary_pressed']}; }}
QPushButton#copyCapture:disabled {{ background:{t['primary_disabled']}; border-color:{t['primary_disabled']}; color:#e2e8f0; }}
QPushButton#cancelCapture {{ background:transparent; border-color:transparent; color:{t['cancel_fg']}; }}
QPushButton#cancelCapture:hover {{ background:{t['cancel_hover']}; color:{t['text']}; }}
QPushButton#saveCapture {{ background:{t['btn_bg']}; border-color:{t['btn_border']}; color:{t['text']}; font-size:12px; font-weight:600; padding:8px 12px; }}
QPushButton#saveCapture:hover {{ color:{t['badge_fg']}; background:{t['btn_hover']}; border-color:{t['btn_hover_border']}; }}
QLabel#capturePath {{ color:{t['muted']}; font-size:12px; background:transparent; }}
QLabel#captureHint {{ color:{t['muted']}; font-size:11px; background:transparent; }}
QLabel#captureError {{ color:{t['err_fg']}; background:{t['err_bg']}; border-radius:8px; padding:8px 12px; }}
QLineEdit {{ background:{t['input_bg']}; color:{t['text']}; border:1px solid {t['btn_border']}; padding:9px 12px; border-radius:9px; selection-background-color:#2563eb; }}
QLineEdit:focus {{ border-color:#3b82f6; }}
QSpinBox {{ background:{t['input_bg']}; color:{t['text']}; border:1px solid {t['btn_border']}; border-radius:8px; padding:4px 18px 4px 6px; font-size:12px; min-height:20px; }}
QSpinBox:focus {{ border-color:#3b82f6; }}
QSpinBox::up-button {{ subcontrol-origin:border; subcontrol-position:top right; width:16px; border:0; background:{t['spin_btn']}; border-top-right-radius:8px; }}
QSpinBox::down-button {{ subcontrol-origin:border; subcontrol-position:bottom right; width:16px; border:0; background:{t['spin_btn']}; border-bottom-right-radius:8px; }}
QSpinBox::up-arrow {{ width:10px; height:10px; image:url("{_CHEVRON_UP}"); }}
QSpinBox::down-arrow {{ width:10px; height:10px; image:url("{_CHEVRON_DOWN}"); }}
QScrollArea {{ border:0; background:transparent; }}
QPushButton#filterChip {{ background:{t['badge_bg']}; color:{t['badge_fg']}; padding:5px 9px; }}
QWidget#captureCanvas {{ background:transparent; }}
QToolTip {{ background:{t['tip_bg']}; color:#f8fafc; border:1px solid #334155; padding:6px 9px; border-radius:8px; }}
"""


CAPTURE_QSS = build_capture_qss(False)
