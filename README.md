# SnapFlow（轻截录屏）

轻量级 Windows 本地截图、标注、滚动长截图与区域录屏工具，常驻系统托盘，零文档解析或后台联网依赖。

## 核心功能

- **框选截图与实时标注**：支持多屏高 DPI 原生像素裁剪，选区内直接进行画笔、矩形、箭头、文字、马赛克标注，一键复制到剪贴板或保存 PNG。
  - ![截图工具栏](docs/capture-unified-toolbar.png)
  - ![截图流程](docs/capture-workflow.gif)
- **滚动长截图与拼接**：框选区域后自动或手动滚动采集并实时拼接长图，支持长图标注与导出。
  - ![长截图拼接](docs/long-capture.png)
- **区域录屏与系统声音**：支持选定区域录制 MP4 视频，可选静音或同步录制电脑系统声音（WASAPI loopback）。
  - ![录屏与音频选项](docs/video-audio-unified.png)
- **系统托盘与全局热键**：默认快捷键 `Alt+S` 随时呼出截图，关闭控制面板后自动退回系统托盘运行，支持开机自启动配置。

## 安装与运行

### 环境安装

需要 Windows 10/11 与 Python 3.11+：

```powershell
.\setup.ps1
```

### 启动应用

- 双击 `Start-DocumentAssistant.cmd`，或运行 `.\start.ps1`
- 使用 `--tray` 参数可直接静默启动到系统托盘：
  ```powershell
  .venv\Scripts\python.exe desktop.py --tray
  ```

## 测试与打包

运行全部单元测试：

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

构建 Windows 独立发行包（PyInstaller + Inno Setup）：

```powershell
.\packaging\build.ps1 -Compiler "<ISCC.exe path>" -Output ".\dist-release"
```
