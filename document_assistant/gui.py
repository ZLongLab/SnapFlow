"""SnapFlow visual gallery studio with Mist Light & Slate Dark rounded-box themes."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QFileSystemWatcher,
    QLibraryInfo,
    QPointF,
    QRectF,
    QSize,
    QStandardPaths,
    QTimer,
    QTranslator,
    QUrl,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QImage,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .capture_hud import CaptureHistory
from .capture_icons import line_icon
from .startup_registration import StartupRegistration
from .windows_identity import ICON_PATH, apply_titlebar_theme, configure_process, tag_window


def _build_qss(theme_name: str) -> str:
    dark = theme_name == "dark"
    if dark:
        t = {
            "bg": "#131926",
            "text": "#eef5fc",
            "muted": "#94a7c0",
            "bar_bg": "#1a2233",
            "bar_border": "#2b3850",
            "card_bg": "#1c2537",
            "card_hover": "#212c42",
            "card_border": "#2d3b54",
            "card_hover_border": "#60a5fa",
            "btn_bg": "#232e44",
            "btn_border": "#33435e",
            "btn_hover": "#2a3853",
            "btn_hover_border": "#60a5fa",
            "btn_text": "#e4eef8",
            "seg_bg": "#131926",
            "seg_active": "#26344d",
            "seg_active_border": "#4c72a8",
            "seg_active_text": "#ffffff",
            "badge_bg": "#202e47",
            "badge_border": "#38527d",
            "badge_text": "#93c5fd",
            "inactive_bg": "#362717",
            "inactive_border": "#7c5124",
            "inactive_text": "#fbbf24",
            "startup_bg": "#14302a",
            "startup_border": "#1f6f58",
            "empty_bg": "#172031",
            "empty_border": "#31415c",
            "scroll": "rgba(148, 167, 192, 70)",
            "status_bg": "#101521",
            "status_border": "#232e42",
            "tip_bg": "#1f293d",
            "tip_border": "#475d80",
            "del_hover": "#3f1d28",
        }
    else:
        t = {
            "bg": "#f3f6fb",
            "text": "#0f172a",
            "muted": "#64748b",
            "bar_bg": "#ffffff",
            "bar_border": "#dce5f2",
            "card_bg": "#ffffff",
            "card_hover": "#ffffff",
            "card_border": "#dce5f2",
            "card_hover_border": "#60a5fa",
            "btn_bg": "#f8fafd",
            "btn_border": "#d6e0ee",
            "btn_hover": "#eff6ff",
            "btn_hover_border": "#60a5fa",
            "btn_text": "#1e293b",
            "seg_bg": "#eef3f9",
            "seg_active": "#ffffff",
            "seg_active_border": "#bfdbfe",
            "seg_active_text": "#2563eb",
            "badge_bg": "#eff6ff",
            "badge_border": "#bfdbfe",
            "badge_text": "#2563eb",
            "inactive_bg": "#fff7ed",
            "inactive_border": "#fdba74",
            "inactive_text": "#c2410c",
            "startup_bg": "#ecfdf5",
            "startup_border": "#6ee7b7",
            "empty_bg": "#ffffff",
            "empty_border": "#cfdbe9",
            "scroll": "rgba(100, 116, 139, 75)",
            "status_bg": "#ebf0f7",
            "status_border": "#dce5f2",
            "tip_bg": "#0f172a",
            "tip_border": "#334155",
            "del_hover": "#fee2e2",
        }

    return f"""
QMainWindow {{ background:{t['bg']}; }}
QWidget {{ font-family:'Microsoft YaHei UI'; font-size:13px; color:{t['text']}; }}
QWidget#backdropRoot, QWidget#galleryGridHost, QWidget#cardFooter {{ background:transparent; }}
QScrollArea#galleryScroll {{ border:0; background:transparent; }}
QScrollArea#galleryScroll > QWidget > QWidget {{ background:transparent; }}
QScrollBar:vertical {{ width:8px; background:transparent; margin:2px; }}
QScrollBar::handle:vertical {{ background:{t['scroll']}; border-radius:4px; min-height:28px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}

QFrame#commandBar {{
    background-color:{t['bar_bg']}; border:1px solid {t['bar_border']}; border-radius:16px;
}}
QLabel#brandName {{ font-size:15px; font-weight:700; color:{t['text']}; background:transparent; }}

QPushButton#hotkeyBadge {{
    font-size:11px; font-weight:600; color:{t['badge_text']};
    background-color:{t['badge_bg']}; border:1px solid {t['badge_border']};
    border-radius:8px; padding:4px 10px;
}}
QPushButton#hotkeyBadge:hover {{ border-color:#60a5fa; }}
QPushButton#hotkeyBadge[inactive="true"] {{
    color:{t['inactive_text']}; background-color:{t['inactive_bg']}; border-color:{t['inactive_border']};
}}

QPushButton#primaryBtn {{
    background-color:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #3b82f6, stop:1 #2563eb);
    color:#ffffff; border:1px solid #2563eb; border-radius:11px;
    padding:7px 17px; font-size:13px; font-weight:700; min-height:20px;
}}
QPushButton#primaryBtn:hover {{
    background-color:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #60a5fa, stop:1 #3b82f6);
    border-color:#60a5fa;
}}
QPushButton#primaryBtn:pressed {{ background-color:#1d4ed8; border-color:#1d4ed8; }}

QPushButton#dockBtn {{
    background-color:{t['btn_bg']}; color:{t['btn_text']};
    border:1px solid {t['btn_border']}; border-radius:11px;
    padding:7px 14px; font-size:12px; font-weight:600; min-height:20px;
}}
QPushButton#dockBtn:hover {{ background-color:{t['btn_hover']}; border-color:{t['btn_hover_border']}; }}

QFrame#audioBox {{
    background-color:{t['seg_bg']}; border:1px solid {t['bar_border']}; border-radius:11px;
}}
QPushButton#audioSeg {{
    background-color:transparent; color:{t['muted']}; border:1px solid transparent; border-radius:8px;
    padding:4px 11px; font-size:12px; font-weight:500;
}}
QPushButton#audioSeg:hover {{ color:{t['text']}; }}
QPushButton#audioSeg:checked {{
    background-color:{t['seg_active']}; border-color:{t['seg_active_border']};
    color:{t['seg_active_text']}; font-weight:700;
}}

QPushButton#iconBtn {{
    background-color:{t['btn_bg']}; border:1px solid {t['btn_border']};
    border-radius:10px; padding:0;
}}
QPushButton#iconBtn:hover {{ background-color:{t['btn_hover']}; border-color:{t['btn_hover_border']}; }}
QPushButton#iconBtn[active="true"] {{
    background-color:{t['startup_bg']}; border-color:{t['startup_border']};
}}

QFrame#filterBox {{
    background-color:{t['seg_bg']}; border:1px solid {t['bar_border']}; border-radius:11px;
}}
QPushButton#filterTab {{
    background-color:transparent; color:{t['muted']}; border:1px solid transparent; border-radius:8px;
    padding:4px 12px; font-size:12px; font-weight:500;
}}
QPushButton#filterTab:hover {{ color:{t['text']}; }}
QPushButton#filterTab:checked {{
    background-color:{t['seg_active']}; border-color:{t['seg_active_border']};
    color:{t['seg_active_text']}; font-weight:700;
}}

QLabel#countLabel {{ font-size:12px; color:{t['muted']}; background:transparent; }}
QPushButton#subtleBoxBtn {{
    background-color:{t['bar_bg']}; color:{t['btn_text']};
    border:1px solid {t['btn_border']}; border-radius:10px; padding:5px 12px; font-size:12px; font-weight:500;
}}
QPushButton#subtleBoxBtn:hover {{ background-color:{t['btn_hover']}; border-color:{t['btn_hover_border']}; }}

QFrame#galleryCard {{
    background-color:{t['card_bg']}; border:1px solid {t['card_border']}; border-radius:16px;
}}
QFrame#galleryCard:hover {{
    background-color:{t['card_hover']}; border-color:{t['card_hover_border']};
}}
QLabel#cardTitle {{ font-size:12px; font-weight:700; color:{t['text']}; background:transparent; }}
QLabel#cardTime {{ font-size:11px; color:{t['muted']}; background:transparent; }}
QPushButton#cardAction {{
    background-color:{t['btn_bg']}; color:{t['btn_text']};
    border:1px solid {t['btn_border']}; border-radius:8px;
    padding:4px 8px; font-size:11px; font-weight:600;
}}
QPushButton#cardAction:hover {{ background-color:{t['btn_hover']}; border-color:{t['btn_hover_border']}; color:{t['seg_active_text']}; }}
QPushButton#cardDelete {{
    background-color:transparent; border:1px solid transparent; border-radius:6px; padding:0;
}}
QPushButton#cardDelete:hover {{ background-color:{t['del_hover']}; border-color:#f87171; }}

QFrame#emptyCard {{
    background-color:{t['empty_bg']}; border:1.5px dashed {t['empty_border']}; border-radius:18px;
}}
QLabel#emptyTitle {{ font-size:18px; font-weight:700; color:{t['text']}; background:transparent; }}
QLabel#emptySub {{ font-size:13px; color:{t['muted']}; background:transparent; }}
QPushButton#featureTileBlue {{
    background-color:{'rgba(59,130,246,34)' if dark else '#eff6ff'}; color:{'#93c5fd' if dark else '#1d4ed8'};
    border:1px solid {'rgba(96,165,250,70)' if dark else '#bfdbfe'}; border-radius:12px; padding:9px 14px; font-size:12px; font-weight:600;
}}
QPushButton#featureTileGreen {{
    background-color:{'rgba(16,185,129,30)' if dark else '#ecfdf5'}; color:{'#6ee7b7' if dark else '#047857'};
    border:1px solid {'rgba(52,211,153,65)' if dark else '#a7f3d0'}; border-radius:12px; padding:9px 14px; font-size:12px; font-weight:600;
}}
QPushButton#featureTileViolet {{
    background-color:{'rgba(139,92,246,34)' if dark else '#f5f3ff'}; color:{'#c4b5fd' if dark else '#6d28d9'};
    border:1px solid {'rgba(167,139,250,70)' if dark else '#ddd6fe'}; border-radius:12px; padding:9px 14px; font-size:12px; font-weight:600;
}}
QPushButton#featureTileAmber {{
    background-color:{'rgba(245,158,11,30)' if dark else '#fffbeb'}; color:{'#fcd34d' if dark else '#b45309'};
    border:1px solid {'rgba(251,191,36,65)' if dark else '#fde68a'}; border-radius:12px; padding:9px 14px; font-size:12px; font-weight:600;
}}
QPushButton#featureTileBlue:hover, QPushButton#featureTileGreen:hover, QPushButton#featureTileViolet:hover, QPushButton#featureTileAmber:hover {{
    border-color:#60a5fa;
}}

QStatusBar {{ background:{t['status_bg']}; color:{t['muted']}; border-top:1px solid {t['status_border']}; font-size:12px; }}
QToolTip {{ background:{t['tip_bg']}; color:#f8fafc; border:1px solid {t['tip_border']}; padding:6px 9px; border-radius:8px; }}
"""


def runtime_directory() -> Path:
    project_root = Path(__file__).resolve().parents[1]
    return Path(
        os.environ.get("DOCUMENTASSISTANT_HOME", str(project_root.parent / "DocumentAssistant-local"))
    ).resolve()


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class StudioBackdrop(QWidget):
    """Soft Mist Light or Slate Dark gradient backdrop with gentle top ambient wash."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dark = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        bg = QLinearGradient(0, 0, 0, h)
        if self.dark:
            bg.setColorAt(0.0, QColor("#131926"))
            bg.setColorAt(1.0, QColor("#182032"))
            washes = (
                (w * 0.20, 0.0, max(w, h) * 0.55, QColor(59, 130, 246, 36)),
                (w * 0.80, h * 0.06, max(w, h) * 0.48, QColor(139, 92, 246, 26)),
            )
        else:
            bg.setColorAt(0.0, QColor("#f4f7fc"))
            bg.setColorAt(1.0, QColor("#e9eff8"))
            washes = (
                (w * 0.18, 0.0, max(w, h) * 0.55, QColor(147, 197, 253, 55)),
                (w * 0.82, h * 0.05, max(w, h) * 0.50, QColor(196, 181, 253, 45)),
            )
        p.fillRect(self.rect(), bg)

        for cx, cy, rad, color in washes:
            glow = QRadialGradient(QPointF(cx, cy), rad)
            glow.setColorAt(0.0, color)
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.fillRect(self.rect(), glow)
        p.end()


class ThumbnailCanvas(QWidget):
    """Clickable visual thumbnail preview for PNG screenshots and MP4 recordings."""

    clicked = Signal()

    def __init__(self, path: Path, is_video: bool, size_bytes: int, dark: bool, parent=None):
        super().__init__(parent)
        self.path = path
        self.is_video = is_video
        self.size_bytes = size_bytes
        self.dark = dark
        self.pixmap = None
        self.dims_text = ""
        self.setFixedHeight(148)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if not is_video:
            img = QImage(str(path))
            if not img.isNull():
                self.dims_text = f"{img.width()}×{img.height()}"
                scaled = img.scaled(520, 280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.pixmap = QPixmap.fromImage(scaled)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(self.rect())
        clip = QPainterPath()
        clip.moveTo(rect.left(), rect.bottom())
        clip.lineTo(rect.left(), rect.top() + 15)
        clip.quadTo(rect.left(), rect.top(), rect.left() + 15, rect.top())
        clip.lineTo(rect.right() - 15, rect.top())
        clip.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + 15)
        clip.lineTo(rect.right(), rect.bottom())
        clip.closeSubpath()

        p.save()
        p.setClipPath(clip)

        if self.is_video:
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            if self.dark:
                grad.setColorAt(0.0, QColor("#241b47"))
                grad.setColorAt(1.0, QColor("#152544"))
            else:
                grad.setColorAt(0.0, QColor("#ede9fe"))
                grad.setColorAt(1.0, QColor("#dbeafe"))
            p.fillRect(rect, grad)

            cx, cy = rect.center().x(), rect.center().y()
            p.setPen(QPen(QColor("#8b5cf6") if not self.dark else QColor("#c4b5fd"), 1.5))
            p.setBrush(QColor(139, 92, 246, 55 if self.dark else 36))
            p.drawEllipse(QPointF(cx, cy), 22, 22)
            icon_pm = line_icon("play", "#ffffff" if self.dark else "#6d28d9").pixmap(18, 18)
            p.drawPixmap(int(cx - 8), int(cy - 9), icon_pm)

            badge_text = f"MP4 · {_format_size(self.size_bytes)}"
            badge_bg = QColor(109, 40, 217, 190)
            badge_fg = QColor("#ffffff")
        else:
            p.fillRect(rect, QColor("#121826" if self.dark else "#edf2f9"))
            if self.pixmap is not None and not self.pixmap.isNull():
                inner = rect.adjusted(10, 10, -10, -10)
                sz = self.pixmap.size().scaled(inner.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
                target = QRectF(inner.center().x() - sz.width() / 2, inner.center().y() - sz.height() / 2, sz.width(), sz.height())
                p.drawPixmap(target.toRect(), self.pixmap)
            else:
                p.setPen(QColor("#64748b"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "无法预览图片")
            badge_text = self.dims_text or "PNG"
            badge_bg = QColor(15, 23, 42, 190) if self.dark else QColor(255, 255, 255, 225)
            badge_fg = QColor("#f8fafc") if self.dark else QColor("#1e293b")

        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        tw = p.fontMetrics().horizontalAdvance(badge_text) + 14
        pill = QRectF(rect.right() - tw - 10, rect.top() + 10, tw, 20)
        p.setPen(QPen(QColor(255, 255, 255, 45) if self.dark else QColor(203, 213, 225, 190), 1))
        p.setBrush(badge_bg)
        p.drawRoundedRect(pill, 7, 7)
        p.setPen(badge_fg)
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, badge_text)

        p.restore()
        p.setPen(QPen(QColor("#2c3952" if self.dark else "#e2e8f0"), 1))
        p.drawLine(QPointF(rect.left(), rect.bottom() - 0.5), QPointF(rect.right(), rect.bottom() - 0.5))
        p.end()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class GalleryCard(QFrame):
    """Rounded gallery card with thumbnail and 1-click quick actions."""

    def __init__(self, path: Path, mtime: float, size_bytes: int, dark: bool, window: MainWindow, is_history: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("galleryCard")
        is_video = path.suffix.lower() == ".mp4"
        self.setMinimumWidth(220)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        thumb = ThumbnailCanvas(path, is_video, size_bytes, dark, self)
        thumb.clicked.connect(lambda p=path: window.open_path(p) if is_video else window.pin_recent_image(p) if is_history else window.open_path(p))
        layout.addWidget(thumb)

        footer = QWidget(self)
        footer.setObjectName("cardFooter")
        f_layout = QVBoxLayout(footer)
        f_layout.setContentsMargins(12, 9, 12, 11)
        f_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        name_lbl = QLabel(path.name)
        name_lbl.setObjectName("cardTitle")
        name_lbl.setToolTip(str(path))
        name_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        time_lbl = QLabel(datetime.fromtimestamp(mtime).strftime("%m-%d %H:%M"))
        time_lbl.setObjectName("cardTime")

        del_btn = QPushButton()
        del_btn.setObjectName("cardDelete")
        del_btn.setFixedSize(22, 22)
        del_btn.setIcon(line_icon("trash", "#94a7c0" if dark else "#64748b"))
        del_btn.setIconSize(QSize(13, 13))
        del_btn.setToolTip("移除该历史记录" if is_history else "删除文件")
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda _=False, p=path, h=is_history: window.delete_recent_file(p, is_history=h))

        title_row.addWidget(name_lbl, 1)
        title_row.addWidget(time_lbl)
        title_row.addWidget(del_btn)
        f_layout.addLayout(title_row)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        if is_video:
            for label, handler in (
                ("播放", lambda p=path: window.open_path(p)),
                ("复制文件", lambda p=path: window.copy_recent_file(p)),
                ("所在目录", lambda p=path: window.open_path(p.parent)),
            ):
                btn = QPushButton(label)
                btn.setObjectName("cardAction")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(handler)
                actions.addWidget(btn, 1)
        elif is_history:
            for label, handler in (
                ("复制", lambda p=path: window.copy_recent_image(p)),
                ("贴图", lambda p=path: window.pin_recent_image(p)),
                ("美化", lambda p=path: window.beautify_recent_image(p)),
                ("保存", lambda p=path: window.save_history_image(p)),
            ):
                btn = QPushButton(label)
                btn.setObjectName("cardAction")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(handler)
                actions.addWidget(btn, 1)
        else:
            for label, handler in (
                ("复制", lambda p=path: window.copy_recent_image(p)),
                ("贴图", lambda p=path: window.pin_recent_image(p)),
                ("美化", lambda p=path: window.beautify_recent_image(p)),
                ("标注", lambda p=path: window.edit_recent_image(p)),
            ):
                btn = QPushButton(label)
                btn.setObjectName("cardAction")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(handler)
                actions.addWidget(btn, 1)
        f_layout.addLayout(actions)
        layout.addWidget(footer)


class MainWindow(QMainWindow):
    def __init__(self, home=None):
        super().__init__()
        self.home = Path(home).resolve() if home else runtime_directory()
        self.home.mkdir(parents=True, exist_ok=True)
        self.closing = False
        self.capture_controller = None
        self._directory_path = Path()
        self.current_filter = "all"
        self._gallery_cards = []
        self.empty_title = None
        self.theme_name = self._load_theme()
        self._watched_dirs = set()

        self._fs_watcher = QFileSystemWatcher(self)
        self._watch_timer = QTimer(self)
        self._watch_timer.setSingleShot(True)
        self._watch_timer.setInterval(260)
        self._watch_timer.timeout.connect(self.refresh_recent)
        self._fs_watcher.directoryChanged.connect(lambda _path: self._watch_timer.start())

        self.setWindowTitle(f"SnapFlow · 轻截录屏 · {__version__}")
        self.resize(1000, 650)
        self.setMinimumSize(780, 520)

        self.backdrop = StudioBackdrop(self)
        self.backdrop.setObjectName("backdropRoot")
        root = QVBoxLayout(self.backdrop)
        root.setContentsMargins(20, 16, 20, 10)
        root.setSpacing(14)

        root.addWidget(self._build_command_bar())
        root.addLayout(self._build_filter_bar())
        root.addWidget(self._build_gallery_area(), 1)

        self.setCentralWidget(self.backdrop)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().showMessage("托盘常驻 · Ctrl+V 可粘贴剪贴板图片进行贴图/美化/标注")

        paste_sc = QShortcut(QKeySequence("Ctrl+V"), self)
        paste_sc.activated.connect(self.paste_from_clipboard)

        self.apply_theme(self.theme_name, persist=False)

    def _ui_path(self) -> Path:
        return self.home / "ui.json"

    def _load_theme(self) -> str:
        try:
            if self._ui_path().exists():
                data = json.loads(self._ui_path().read_text(encoding="utf-8"))
                if data.get("theme") in ("light", "dark"):
                    return data["theme"]
        except Exception:
            pass
        return "light"

    def _save_theme(self, theme_name: str):
        try:
            tmp = self._ui_path().with_suffix(".tmp")
            tmp.write_text(json.dumps({"theme": theme_name}, indent=2), encoding="utf-8")
            tmp.replace(self._ui_path())
        except OSError:
            pass

    def toggle_theme(self):
        next_theme = "dark" if self.theme_name == "light" else "light"
        self.apply_theme(next_theme, persist=True)

    def apply_theme(self, theme_name: str, persist: bool = True):
        self.theme_name = "dark" if theme_name == "dark" else "light"
        dark = self.theme_name == "dark"
        self.backdrop.dark = dark
        self.backdrop.update()
        self.setStyleSheet(_build_qss(self.theme_name))
        apply_titlebar_theme(self, dark=dark)

        ink = "#e2ecf8" if dark else "#1e293b"
        muted_ink = "#cfe0f2" if dark else "#475569"
        self.screenshot_button.setIcon(line_icon("capture", "#ffffff"))
        self.long_button.setIcon(line_icon("scroll", ink))
        self.video_button.setIcon(line_icon("video", ink))
        self.open_dir_btn.setIcon(line_icon("folder", muted_ink))
        self.cfg_btn.setIcon(line_icon("settings", muted_ink))
        self.theme_button.setIcon(line_icon("sun" if dark else "moon", muted_ink))
        self.theme_button.setToolTip("切换到晨雾浅色" if dark else "切换到深蓝暗色")
        self.directory_button.setIcon(line_icon("folder", "#60a5fa" if dark else "#2563eb"))
        self.paste_clip_btn.setIcon(line_icon("pin", "#60a5fa" if dark else "#2563eb"))
        self.beautify_pick.setIcon(line_icon("sparkle", "#c4b5fd" if dark else "#7c3aed"))
        self.refresh_btn.setIcon(line_icon("refresh", muted_ink))

        if persist:
            self._save_theme(self.theme_name)
        self.refresh_summary()

    def _build_command_bar(self):
        bar = QFrame()
        bar.setObjectName("commandBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(QIcon(str(ICON_PATH)).pixmap(28, 28))
        layout.addWidget(icon)

        brand = QLabel("SnapFlow")
        brand.setObjectName("brandName")
        layout.addWidget(brand)

        self.hotkey_badge = QPushButton("Alt+S")
        self.hotkey_badge.setObjectName("hotkeyBadge")
        self.hotkey_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hotkey_badge.setToolTip("点击打开设置与快捷键")
        self.hotkey_badge.clicked.connect(self.screenshot_settings)
        layout.addWidget(self.hotkey_badge)

        layout.addStretch(1)

        self.screenshot_button = QPushButton("框选截图")
        self.screenshot_button.setObjectName("primaryBtn")
        self.screenshot_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.screenshot_button.clicked.connect(self.take_screenshot)
        layout.addWidget(self.screenshot_button)

        self.long_button = QPushButton("长截图")
        self.long_button.setObjectName("dockBtn")
        self.long_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.long_button.clicked.connect(self.take_long_screenshot)
        layout.addWidget(self.long_button)

        self.video_button = QPushButton("录屏")
        self.video_button.setObjectName("dockBtn")
        self.video_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.video_button.clicked.connect(self.take_video_recording)
        layout.addWidget(self.video_button)

        capsule = QFrame()
        capsule.setObjectName("audioBox")
        cap_layout = QHBoxLayout(capsule)
        cap_layout.setContentsMargins(3, 3, 3, 3)
        cap_layout.setSpacing(2)

        self.audio_group = QButtonGroup(self)
        self.audio_group.setExclusive(True)
        self.audio_buttons = {}
        for mode, label in (("silent", "无声"), ("system", "电脑声音")):
            btn = QPushButton(label)
            btn.setObjectName("audioSeg")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, m=mode: self._select_audio_mode(m))
            self.audio_group.addButton(btn)
            self.audio_buttons[mode] = btn
            cap_layout.addWidget(btn)
        self.audio_buttons["silent"].setChecked(True)
        layout.addWidget(capsule)

        layout.addStretch(1)

        self.open_dir_btn = QPushButton()
        self.open_dir_btn.setObjectName("iconBtn")
        self.open_dir_btn.setFixedSize(34, 34)
        self.open_dir_btn.setToolTip("打开保存目录")
        self.open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_dir_btn.clicked.connect(self.open_save_directory)

        self.cfg_btn = QPushButton()
        self.cfg_btn.setObjectName("iconBtn")
        self.cfg_btn.setFixedSize(34, 34)
        self.cfg_btn.setToolTip("设置与快捷键")
        self.cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cfg_btn.clicked.connect(self.screenshot_settings)

        self.startup_button = QPushButton()
        self.startup_button.setObjectName("iconBtn")
        self.startup_button.setFixedSize(34, 34)
        self.startup_button.setToolTip("开机自启动与运行设置")
        self.startup_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.startup_button.clicked.connect(self.show_settings)

        self.theme_button = QPushButton()
        self.theme_button.setObjectName("iconBtn")
        self.theme_button.setFixedSize(34, 34)
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.clicked.connect(self.toggle_theme)

        layout.addWidget(self.open_dir_btn)
        layout.addWidget(self.cfg_btn)
        layout.addWidget(self.startup_button)
        layout.addWidget(self.theme_button)
        return bar

    def _build_filter_bar(self):
        row = QHBoxLayout()
        row.setSpacing(10)

        capsule = QFrame()
        capsule.setObjectName("filterBox")
        c_layout = QHBoxLayout(capsule)
        c_layout.setContentsMargins(3, 3, 3, 3)
        c_layout.setSpacing(2)

        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        self.filter_buttons = {}
        for key, label in (("all", "全部"), ("image", "截图"), ("video", "录屏"), ("history", "剪贴历史")):
            btn = QPushButton(label)
            btn.setObjectName("filterTab")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.set_gallery_filter(k))
            self.filter_group.addButton(btn)
            self.filter_buttons[key] = btn
            c_layout.addWidget(btn)
        self.filter_buttons["all"].setChecked(True)
        row.addWidget(capsule)

        self.recent_count = QLabel("暂无记录")
        self.recent_count.setObjectName("countLabel")
        row.addWidget(self.recent_count)

        self.directory_button = QPushButton("桌面")
        self.directory_button.setObjectName("subtleBoxBtn")
        self.directory_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.directory_button.clicked.connect(self.open_save_directory)
        row.addWidget(self.directory_button)

        row.addStretch(1)

        self.paste_clip_btn = QPushButton("贴图剪贴板")
        self.paste_clip_btn.setObjectName("subtleBoxBtn")
        self.paste_clip_btn.setToolTip("直接把剪贴板里的图片贴到桌面，或在窗口内按 Ctrl+V 选择操作")
        self.paste_clip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.paste_clip_btn.clicked.connect(self.pin_from_clipboard)

        self.beautify_pick = QPushButton("美化图片")
        self.beautify_pick.setObjectName("subtleBoxBtn")
        self.beautify_pick.setToolTip("选择本地截图进行渐变套壳美化")
        self.beautify_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        self.beautify_pick.clicked.connect(self.beautify_from_file)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("subtleBoxBtn")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(lambda _=False: self.refresh_recent())

        row.addWidget(self.paste_clip_btn)
        row.addWidget(self.beautify_pick)
        row.addWidget(self.refresh_btn)
        return row

    def _build_gallery_area(self):
        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setObjectName("galleryScroll")
        self.gallery_scroll.setWidgetResizable(True)
        self.gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.gallery_host = QWidget()
        self.gallery_host.setObjectName("galleryGridHost")
        self.gallery_layout = QGridLayout(self.gallery_host)
        self.gallery_layout.setContentsMargins(2, 2, 6, 8)
        self.gallery_layout.setSpacing(14)

        self.gallery_scroll.setWidget(self.gallery_host)
        return self.gallery_scroll

    def _sync_directory_watcher(self):
        desired = set()
        if self._directory_path and self._directory_path.is_dir():
            desired.add(str(self._directory_path))
        hist_dir = self.home / "history"
        if hist_dir.is_dir():
            desired.add(str(hist_dir))
        to_remove = self._watched_dirs - desired
        if to_remove:
            self._fs_watcher.removePaths(list(to_remove))
        to_add = desired - self._watched_dirs
        if to_add:
            self._fs_watcher.addPaths(list(to_add))
        self._watched_dirs = desired

    def set_gallery_filter(self, kind: str):
        if kind not in ("all", "image", "video", "history"):
            kind = "all"
        self.current_filter = kind
        if kind in self.filter_buttons:
            blocked = self.filter_buttons[kind].blockSignals(True)
            self.filter_buttons[kind].setChecked(True)
            self.filter_buttons[kind].blockSignals(blocked)
        self.refresh_recent()

    @property
    def audio_mode(self) -> str:
        for mode, btn in self.audio_buttons.items():
            if btn.isChecked():
                return mode
        return "silent"

    def set_audio_mode(self, mode: str):
        target = "system" if mode == "system" else "silent"
        for key, btn in self.audio_buttons.items():
            blocked = btn.blockSignals(True)
            btn.setChecked(key == target)
            btn.blockSignals(blocked)

    def _select_audio_mode(self, mode: str):
        self.set_audio_mode(mode)
        if self.capture_controller is not None:
            self.capture_controller.change_video_audio_mode(mode)

    def _configured_settings(self, controller=None):
        ctrl = controller or self.capture_controller
        if ctrl is not None:
            return dict(ctrl.settings)
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        settings = {"hotkey": "Alt+S", "directory": desktop or str(Path.home() / "Desktop"), "save_copy_history": True}
        config_path = self.home / "screenshot.json"
        try:
            if config_path.exists():
                saved = json.loads(config_path.read_text(encoding="utf-8"))
                if isinstance(saved.get("hotkey"), str) and saved["hotkey"].strip():
                    settings["hotkey"] = saved["hotkey"].strip()
                if isinstance(saved.get("directory"), str) and Path(saved["directory"]).is_absolute():
                    settings["directory"] = saved["directory"]
                if isinstance(saved.get("save_copy_history"), bool):
                    settings["save_copy_history"] = saved["save_copy_history"]
        except Exception:
            pass
        return settings

    def refresh_summary(self, controller=None):
        ctrl = controller or self.capture_controller
        settings = self._configured_settings(ctrl)
        directory = Path(settings["directory"]).resolve()
        self._directory_path = directory
        self._sync_directory_watcher()
        folder_label = directory.name or str(directory)
        self.directory_button.setText(folder_label)
        self.directory_button.setToolTip(f"当前保存目录（点击打开）：\n{directory}")

        hotkey = settings["hotkey"]
        if ctrl is not None:
            active = hasattr(ctrl, "hotkey") and ctrl.hotkey.ident is not None
            self.hotkey_badge.setText(f"{hotkey}" if active else f"{hotkey} 未启用")
            self.hotkey_badge.setProperty("inactive", not active)
            self.set_audio_mode(getattr(ctrl, "video_audio_mode", "silent"))
        else:
            active = True
            self.hotkey_badge.setText(f"{hotkey}")
            self.hotkey_badge.setProperty("inactive", False)
            self.screenshot_button.setText(f"框选截图  {hotkey}" if len(hotkey) <= 7 else "框选截图")

        self.hotkey_badge.style().unpolish(self.hotkey_badge)
        self.hotkey_badge.style().polish(self.hotkey_badge)

        try:
            enabled = StartupRegistration(self.home).enabled()
        except Exception:
            enabled = False
        dark = self.theme_name == "dark"
        self.startup_button.setProperty("active", enabled)
        self.startup_button.setIcon(
            line_icon("power", "#10b981" if enabled else ("#cfe0f2" if dark else "#475569"))
        )
        self.startup_button.setToolTip("开机自启动：已开启（点击管理）" if enabled else "开机自启动：已关闭（点击开启）")
        self.startup_button.style().unpolish(self.startup_button)
        self.startup_button.style().polish(self.startup_button)

        self.refresh_recent(hotkey=hotkey, hotkey_active=active)

    def refresh_recent(self, _checked=False, *, hotkey=None, hotkey_active=None):
        self._gallery_cards = []
        self.empty_title = None
        while self.gallery_layout.count():
            item = self.gallery_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if hotkey is None:
            hotkey = self._configured_settings()["hotkey"]
        if hotkey_active is None:
            if self.capture_controller is not None and hasattr(self.capture_controller, "hotkey"):
                hotkey_active = self.capture_controller.hotkey.ident is not None
            else:
                hotkey_active = True

        self._sync_directory_watcher()
        is_history = self.current_filter == "history"
        entries = []
        if is_history:
            entries = CaptureHistory(self.home).entries()
        else:
            directory = self._directory_path or Path(self._configured_settings()["directory"]).resolve()
            if directory.is_dir():
                try:
                    for child in directory.iterdir():
                        if not child.is_file():
                            continue
                        ext = child.suffix.lower()
                        if ext not in (".png", ".mp4"):
                            continue
                        if self.current_filter == "image" and ext != ".png":
                            continue
                        if self.current_filter == "video" and ext != ".mp4":
                            continue
                        stat = child.stat()
                        entries.append((stat.st_mtime, stat.st_size, child))
                except OSError:
                    entries = []
            entries.sort(key=lambda item: item[0], reverse=True)

        items = entries[:18]
        self.recent_count.setText(f"最近 {len(items)} 项" if items else "暂无记录")

        dark = self.theme_name == "dark"
        if not items:
            empty = QFrame()
            empty.setObjectName("emptyCard")
            e_layout = QVBoxLayout(empty)
            e_layout.setContentsMargins(28, 36, 28, 36)
            e_layout.setSpacing(12)
            e_layout.addStretch(1)

            icon_lbl = QLabel()
            icon_lbl.setPixmap(QIcon(str(ICON_PATH)).pixmap(52, 52))
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_layout.addWidget(icon_lbl)

            if is_history:
                hist_enabled = self._configured_settings().get("save_copy_history", True)
                title_text = "还没有暂存的剪贴历史" if hist_enabled else "已关闭复制时暂存剪贴历史"
                sub_text = (
                    "复制截图后会自动在本机运行目录 history 暂存最近 20 张（可在设置中随时关闭或清空）"
                    if hist_enabled
                    else "当前「仅复制」不会向磁盘写入任何文件；如需防覆盖找回，可在设置中开启"
                )
            elif hotkey_active and self.current_filter != "video":
                title_text = f"按下 {hotkey}，捕获你的第一张画面"
                sub_text = "支持智能窗口吸附、框选标注、滚动长截图、区域录屏与桌面原位贴图"
            else:
                title_text = "当前分类下还没有记录"
                sub_text = "支持框选标注、滚动长截图、区域录屏与桌面悬浮贴图"

            title = QLabel(title_text)
            title.setObjectName("emptyTitle")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.empty_title = title
            e_layout.addWidget(title)

            sub = QLabel(sub_text)
            sub.setObjectName("emptySub")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_layout.addWidget(sub)

            tiles_row = QHBoxLayout()
            tiles_row.setSpacing(10)
            tiles_row.addStretch(1)
            for label, obj_name, handler in (
                ("框选标注 · 窗口吸附", "featureTileBlue", self.take_screenshot),
                ("滚动长截图 · 自动拼接", "featureTileGreen", self.take_long_screenshot),
                ("区域录屏 · 电脑声音", "featureTileViolet", self.take_video_recording),
                ("美化套壳 · 渐变圆角", "featureTileAmber", self.beautify_from_file),
            ):
                tile = QPushButton(label)
                tile.setObjectName(obj_name)
                tile.setCursor(Qt.CursorShape.PointingHandCursor)
                tile.clicked.connect(handler)
                tiles_row.addWidget(tile)
            tiles_row.addStretch(1)
            e_layout.addSpacing(4)
            e_layout.addLayout(tiles_row)

            cta_row = QHBoxLayout()
            cta_row.addStretch(1)
            cta = QPushButton("立即框选截图")
            cta.setObjectName("primaryBtn")
            cta.setIcon(line_icon("capture", "#ffffff"))
            cta.setCursor(Qt.CursorShape.PointingHandCursor)
            cta.clicked.connect(self.take_screenshot)
            cta_row.addWidget(cta)
            cta_row.addStretch(1)
            e_layout.addSpacing(6)
            e_layout.addLayout(cta_row)
            e_layout.addStretch(2)

            self.gallery_layout.addWidget(empty, 0, 0, 1, 3)
            return

        for idx, (mtime, size_bytes, path) in enumerate(items):
            card = GalleryCard(path, mtime, size_bytes, dark, self, is_history=is_history)
            self._gallery_cards.append(card)
            self.gallery_layout.addWidget(card, idx // 3, idx % 3)
        for col in range(3):
            self.gallery_layout.setColumnStretch(col, 1)
        self.gallery_layout.setRowStretch((len(items) - 1) // 3 + 1, 1)

    def _load_image_or_warn(self, path: Path) -> QImage | None:
        if not path.is_file():
            QMessageBox.warning(self, "文件不存在", f"图片可能已被移动或删除：\n{path}")
            self.refresh_recent()
            return None
        image = QImage(str(path))
        if image.isNull():
            QMessageBox.warning(self, "读取失败", f"无法读取图片内容：\n{path}")
            return None
        return image

    def copy_recent_image(self, path: Path):
        image = self._load_image_or_warn(path)
        if image is None:
            return
        try:
            from .screen_capture import copy_image
            copy_image(image)
        except Exception as exc:
            QMessageBox.warning(self, "复制失败", str(exc))
            return
        self.statusBar().showMessage(f"已复制到剪贴板：{path.name}", 6000)

    def copy_recent_file(self, path: Path):
        try:
            from .screen_capture import copy_file_to_clipboard
            copy_file_to_clipboard(path)
        except Exception as exc:
            QMessageBox.warning(self, "复制文件失败", str(exc))
            return
        self.statusBar().showMessage(f"已复制文件，可直接 Ctrl+V 发送：{path.name}", 6000)

    def save_history_image(self, path: Path):
        image = self._load_image_or_warn(path)
        if image is None:
            return
        try:
            from .screen_capture import save_png
            target_dir = self._directory_path or Path(self._configured_settings()["directory"]).resolve()
            saved = save_png(image, target_dir)
            if self.capture_controller:
                self.capture_controller.last_saved = saved
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.statusBar().showMessage(f"已保存到 {saved}", 6000)
        self.refresh_recent()

    def delete_recent_file(self, path: Path, *, is_history: bool = False):
        if is_history:
            CaptureHistory(self.home).delete(path)
            self.statusBar().showMessage(f"已移除历史记录：{path.name}", 4000)
            self.refresh_recent()
            return
        reply = QMessageBox.question(
            self,
            "删除文件",
            f"确定永久删除该文件？\n{path.name}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "删除失败", str(exc))
            return
        self.statusBar().showMessage(f"已删除：{path.name}", 5000)
        self.refresh_recent()

    def pin_recent_image(self, path: Path):
        image = self._load_image_or_warn(path)
        if image is None:
            return
        self.ensure_capture().pin_image(image)
        self.statusBar().showMessage(f"已贴到桌面：{path.name}（拖动移动 · 滚轮缩放 · 双击收起 · Esc 关闭）", 6000)

    def pin_from_clipboard(self):
        self.ensure_capture().pin_clipboard()

    def paste_from_clipboard(self):
        image = QApplication.clipboard().image()
        if image.isNull():
            self.statusBar().showMessage("剪贴板中没有图片", 4000)
            return
        menu = QMenu(self)
        act_pin = menu.addAction("贴到桌面")
        act_beautify = menu.addAction("美化套壳")
        act_edit = menu.addAction("标注编辑")
        chosen = menu.exec(self.mapToGlobal(self.rect().center()))
        ctrl = self.ensure_capture()
        if chosen is act_pin:
            ctrl.pin_image(image)
        elif chosen is act_beautify:
            ctrl.beautify_image(image)
        elif chosen is act_edit:
            ctrl.edit_image(image)

    def beautify_recent_image(self, path: Path):
        image = self._load_image_or_warn(path)
        if image is None:
            return
        self.ensure_capture().beautify_image(image)

    def edit_recent_image(self, path: Path):
        image = self._load_image_or_warn(path)
        if image is None:
            return
        self.ensure_capture().edit_image(image)

    def beautify_from_file(self):
        start_dir = str(self._directory_path or self._configured_settings()["directory"])
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "选择要美化的图片",
            start_dir,
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not chosen:
            return
        self.beautify_recent_image(Path(chosen))

    def showEvent(self, event):
        super().showEvent(event)
        apply_titlebar_theme(self, dark=(self.theme_name == "dark"))

    def open_path(self, path: Path) -> bool:
        target = Path(path).resolve()
        if not target.exists():
            QMessageBox.warning(self, "路径不存在", f"文件或目录可能已被移动或删除：\n{target}")
            return False
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))):
            QMessageBox.warning(self, "无法打开", "Windows 未能打开该路径，请检查默认应用关联。")
            return False
        return True

    def open_save_directory(self):
        self.ensure_capture().open_directory()

    def ensure_capture(self):
        if self.capture_controller is None:
            from .screen_capture import CaptureController
            self.capture_controller = CaptureController(self)
        return self.capture_controller

    def take_screenshot(self):
        self.ensure_capture().begin(mode="photo")

    def take_long_screenshot(self):
        self.ensure_capture().begin(mode="long")

    def take_video_recording(self):
        controller = self.ensure_capture()
        controller.change_video_audio_mode(self.audio_mode)
        controller.begin(mode="video")

    def screenshot_settings(self):
        self.ensure_capture().show_settings()

    def show_settings(self):
        self.ensure_capture().show_settings()
        self.refresh_summary()

    def closeEvent(self, event):
        capture = self.capture_controller
        if capture and capture.tray and not capture.exiting:
            self.hide()
            if not getattr(capture, '_tray_close_notified', False):
                capture._tray_close_notified = True
                capture.notify("已在托盘运行", "快捷键 " + capture.settings["hotkey"] + " · 单击托盘图标可重新打开")
            event.ignore()
            return
        self.closing = True
        if capture:
            capture.shutdown()
            QTimer.singleShot(0, QApplication.instance().quit)
        event.accept()


def configure_app(app):
    configure_process()
    app.setApplicationName("SnapFlow")
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setStyle("Fusion")
    translator = QTranslator(app)
    if translator.load("qtbase_zh_CN", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    app._chinese_translator = translator


def main(start_in_tray=False):
    configure_process()
    app = QApplication([])
    configure_app(app)
    from .app_instance import AppInstance

    instance = None
    try:
        instance = AppInstance(runtime_directory(), app)
        if not instance.start(activate=not start_in_tray):
            return 0
        window = MainWindow()
    except Exception as exc:
        if instance:
            instance.shutdown()
        QMessageBox.critical(None, "启动失败", f"无法初始化 SnapFlow：\n{exc}\n请检查运行目录的写权限。")
        return 1
    tag_window(int(window.winId()))
    if not start_in_tray:
        window.show()
    window.ensure_capture()
    if start_in_tray and not window.capture_controller.tray:
        window.show()
    instance.activated.connect(window.capture_controller.show_main)
    result = app.exec()
    instance.shutdown()
    if window.capture_controller:
        window.capture_controller.shutdown()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    return result
