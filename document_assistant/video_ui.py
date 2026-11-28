"""Compact recording controls and a themed local video preview/save-and-copy dialog."""
from pathlib import Path
from PySide6.QtCore import QRect, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QPainterPath, QShortcut
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from .capture_style import build_capture_qss
from .video_recording import save_video
from .video_audio import audio_label, normalize_audio_mode
from .windows_identity import apply_titlebar_theme


def controls_position(area, region, size):
    """Find room fully outside the captured area; return None for a full screen."""
    gap = 12
    w, h = size.width(), size.height()
    candidates = [
        (region.right() - w, region.bottom() + gap),
        (region.right() - w, region.top() - h - gap),
        (region.right() + gap, region.top()),
        (region.left() - w - gap, region.top()),
    ]
    for x, y in candidates:
        x = max(area.left() + 8, min(area.right() - w - 8, x))
        y = max(area.top() + 8, min(area.bottom() - h - 8, y))
        rect = QRect(int(x), int(y), w, h)
        if area.contains(rect) and not region.intersects(rect):
            return rect.topLeft()
    return None


class RecordingControls(QWidget):
    stop_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, hotkey, audio_mode='silent'):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('视频录制 · SnapFlow')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(
            'QWidget{background:#161e2e;color:#e8f2fa;font-family:"Microsoft YaHei UI";font-size:13px;border-radius:13px;} '
            'QLabel#recordClock{font-size:17px;font-weight:700;color:#fca5a5;} '
            'QPushButton{background:#ef4444;color:#fff;border:0;border-radius:9px;padding:8px 15px;font-weight:600;} '
            'QPushButton:hover{background:#dc2626;} '
            'QPushButton:disabled{background:#2b3a52;color:#93adbf;}'
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 11, 12, 11)
        layout.setSpacing(14)
        self.clock = QLabel('准备开始')
        self.clock.setObjectName('recordClock')
        layout.addWidget(self.clock)
        self.hint = QLabel(audio_label(audio_mode) + ' · ' + hotkey + ' 停止')
        layout.addWidget(self.hint)
        self.stop_button = QPushButton('取消')
        self.stop_button.clicked.connect(self.action)
        layout.addWidget(self.stop_button)
        self.live = False
        self.adjustSize()

    def action(self):
        if self.live:
            self.stop_requested.emit()
        else:
            self.cancel_requested.emit()

    def countdown(self, value):
        self.clock.setText(f'{value} 秒后开始')

    def started(self):
        self.live = True
        self.stop_button.setText('■  停止')
        self.clock.setText('●  00:00')

    def progress(self, millis):
        if self.live:
            self.clock.setText(f'●  {millis // 60000:02d}:{millis // 1000 % 60:02d}')

    def stopping(self):
        self.clock.setText('正在生成视频')
        self.stop_button.setEnabled(False)


class VideoCanvas(QWidget):
    """Paint decoded frames directly so native previews and snapshots agree."""

    def __init__(self):
        super().__init__()
        self.image = None
        self.sink = QVideoSink(self)
        self.sink.videoFrameChanged.connect(self.receive)

    def receive(self, frame):
        image = frame.toImage()
        if not image.isNull():
            self.image = image
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 14, 14)
        painter.setClipPath(clip)
        painter.fillRect(self.rect(), QColor('#121826'))
        if self.image is not None:
            size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2, size.width(), size.height())
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(target, self.image)
        else:
            painter.setPen(QColor('#94a7c0'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '正在加载视频…')
        painter.end()


class VideoPreview(QDialog):
    def __init__(self, path, controller, warning='', *, audio_mode='silent'):
        super().__init__(None)
        self.path = Path(path)
        self.controller = controller
        self.saved_path = None
        self.audio_mode = normalize_audio_mode(audio_mode)
        dark = getattr(getattr(controller, 'window', None), 'theme_name', 'light') == 'dark'
        self.setWindowTitle('视频预览 · SnapFlow')
        self.resize(900, 650)
        self.setMinimumSize(560, 420)
        self.setStyleSheet(build_capture_qss(dark))
        apply_titlebar_theme(self, dark=dark)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        header = QFrame()
        header.setObjectName('captureHeader')
        row = QHBoxLayout(header)
        row.setContentsMargins(22, 16, 22, 16)
        title = QLabel('录制完成')
        title.setObjectName('captureTitle')
        row.addWidget(title)
        row.addStretch()
        self.badge = QLabel(('有声视频 · 电脑声音' if self.audio_mode == 'system' else '无声视频') + ' · MP4')
        self.badge.setObjectName('captureBadge')
        row.addWidget(self.badge)
        layout.addWidget(header)

        self.video = VideoCanvas()
        self.video.setMinimumHeight(200)
        body = QHBoxLayout()
        body.setContentsMargins(20, 0, 20, 0)
        body.addWidget(self.video)
        layout.addLayout(body, 1)

        self.player = QMediaPlayer(self)
        self.player.setVideoSink(self.video.sink)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.errorOccurred.connect(lambda code, message: self.error.setText('预览失败：' + message + '。仍可保存视频。'))

        tools = QHBoxLayout()
        tools.setContentsMargins(22, 0, 22, 0)
        self.play_button = QPushButton('播放')
        self.play_button.setAutoDefault(False)
        self.play_button.clicked.connect(self.toggle_play)
        tools.addWidget(self.play_button)
        self.time = QLabel('00:00 / 00:00')
        tools.addWidget(self.time)
        tools.addStretch()
        self.mute_button = QPushButton('静音')
        self.mute_button.setCheckable(True)
        self.mute_button.setAutoDefault(False)
        self.mute_button.setVisible(self.audio_mode == 'system')
        self.mute_button.toggled.connect(self.audio_output.setMuted)
        self.mute_button.toggled.connect(lambda muted: self.mute_button.setText('取消静音' if muted else '静音'))
        self.player.hasAudioChanged.connect(self.mute_button.setVisible)
        tools.addWidget(self.mute_button)
        layout.addLayout(tools)

        self.player.positionChanged.connect(self.update_time)
        self.player.durationChanged.connect(self.update_time)
        self.player.playbackStateChanged.connect(
            lambda state: self.play_button.setText('暂停' if state == QMediaPlayer.PlaybackState.PlayingState else '播放')
        )
        self.error = QLabel('')
        self.error.setWordWrap(True)
        self.error.setObjectName('captureError')
        self.error.hide()
        layout.addWidget(self.error)
        if warning:
            self.error.setText('录制提前结束：' + warning + '。已录内容可以预览和保存。')
            self.error.show()
        self.player.errorOccurred.connect(lambda *args: self.error.show())

        foot = QHBoxLayout()
        foot.setContentsMargins(22, 8, 22, 20)
        label = QLabel('保存到 ' + str(controller.settings['directory']) + ' · 保存后自动复制文件可直接 Ctrl+V 发送')
        label.setObjectName('captureHint')
        label.setToolTip(label.text())
        label.setWordWrap(True)
        foot.addWidget(label, 1)
        self.discard_button = QPushButton('不保存')
        self.discard_button.setObjectName('cancelCapture')
        self.discard_button.setAutoDefault(False)
        self.discard_button.clicked.connect(self.reject)
        foot.addWidget(self.discard_button)
        self.save_button = QPushButton('保存并复制文件')
        self.save_button.setObjectName('copyCapture')
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        foot.addWidget(self.save_button)
        layout.addLayout(foot)

        for seq, handler in (('Ctrl+S', self.save), ('Space', self.toggle_play)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(handler)

        self.player.setSource(QUrl.fromLocalFile(str(self.path)))
        self.player.play()
        self.finished.connect(lambda *_: self.release_player())

    def update_time(self, *_):
        def fmt(value):
            return f'{value // 60000:02d}:{value // 1000 % 60:02d}'

        self.time.setText(fmt(self.player.position()) + ' / ' + fmt(self.player.duration()))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()

    def release_player(self):
        self.player.stop()
        self.player.setSource(QUrl())

    def save(self):
        try:
            self.saved_path = save_video(self.path, self.controller.settings['directory'])
        except Exception as exc:
            self.error.setText('保存失败：' + str(exc) + '。视频仍在，请重试。')
            self.error.show()
            return
        self.controller.last_video = self.saved_path
        copied = False
        try:
            from .screen_capture import copy_file_to_clipboard
            copy_file_to_clipboard(self.saved_path)
            copied = True
        except Exception:
            pass
        if hasattr(self.controller, '_notify_window_refresh'):
            self.controller._notify_window_refresh()
        self.controller.notify(
            '视频已保存并复制文件' if copied else '视频已保存',
            self.saved_path.name + (' · 可直接 Ctrl+V 发送' if copied else ''),
        )
        self.accept()

    def reject(self):
        if (
            not self.saved_path
            and QMessageBox.question(
                self,
                '不保存视频',
                '丢弃这次录制的视频？',
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            != QMessageBox.StandardButton.Discard
        ):
            return
        super().reject()
