# SnapFlow（轻截录屏）

SnapFlow 是一款 Windows 本地截图和录屏工具。按 **Alt+S** 框选屏幕，就能在选区里标注、滚动截长图，或录制指定区域。处理完成后可以复制图片、保存文件，或把截图贴在桌面上随时查看。

![SnapFlow 框选截图工具栏](docs/capture-unified-toolbar.png)

## 从一次截图开始

1. **截图与标注** · 按 `Alt+S` 拖出选区，用画笔、矩形、箭头、文字或马赛克标注。按 `Enter` 复制到剪贴板，点「保存」可将截图写入 PNG 文件。支持多屏和高 DPI 缩放。
2. **滚动长截图** · 切到「长截图」，在选区里滚动页面，或点「自动滚动」。采集时可查看实时拼接预览。点「完成采集」后，可以继续标注，再复制或保存。
3. **区域录屏** · 切到「视频」，选择「无声」或「有声 · 电脑声音」，然后点「开始录制」。录完点「停止」，预览后选择「保存视频」，导出 MP4。

主窗口会显示保存目录中的最近截图，可在列表里复制、置顶贴图或加渐变背景。关闭主窗口后，SnapFlow 继续在系统托盘运行。点击主窗口上的快捷键可修改截图快捷键和保存目录。

<details>
<summary>查看操作演示</summary>

![框选与标注操作](docs/capture-workflow.gif)

![滚动长截图操作](docs/long-capture.png)

![区域录屏的声音选项](docs/video-audio-unified.png)

</details>

## 在 Windows 上运行

需要 Windows 10 或 11 和 Python 3.11 及以上版本。在项目文件夹打开 PowerShell，首次运行依赖安装命令。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

安装完成后，双击 `Start-DocumentAssistant.cmd` 或桌面上的 **SnapFlow** 快捷方式。需要直接在托盘启动时，运行以下命令。

```powershell
.\.venv\Scripts\python.exe desktop.py --tray
```

## 测试与打包

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Windows 安装包和免安装版的构建步骤见 [Windows 打包说明](packaging/README.md)。
