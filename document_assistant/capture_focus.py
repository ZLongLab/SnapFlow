"""Remember/restore foreground apps and enumerate visible Windows window bounds."""
import ctypes
import os
import sys
from ctypes import wintypes
from PySide6.QtCore import QRectF


def foreground_window():
    if sys.platform != 'win32':
        return None
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.GetForegroundWindow.restype = wintypes.HWND
    return api.GetForegroundWindow()


def window_owner(handle):
    """Treat a transient native popup and its owner as the same foreground app."""
    if not handle or sys.platform != 'win32':
        return handle
    api = ctypes.WinDLL('user32', use_last_error=True)
    api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    api.GetAncestor.restype = wintypes.HWND
    return api.GetAncestor(handle, 3) or handle


def restore_foreground(handle):
    if not handle or sys.platform != 'win32':
        return False
    api = ctypes.WinDLL('user32', use_last_error=True)
    for name in ('IsWindow', 'IsWindowVisible', 'SetForegroundWindow'):
        function = getattr(api, name)
        function.argtypes = [wintypes.HWND]
        function.restype = wintypes.BOOL
    if not api.IsWindow(handle) or not api.IsWindowVisible(handle):
        return False
    return bool(api.SetForegroundWindow(handle))


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ('cbSize', wintypes.DWORD),
        ('rcMonitor', wintypes.RECT),
        ('rcWork', wintypes.RECT),
        ('dwFlags', wintypes.DWORD),
        ('szDevice', wintypes.WCHAR * 32),
    ]


def _physical_monitors():
    """Return {device_name: (left, top, right, bottom)} for Windows monitors."""
    if sys.platform != 'win32':
        return {}
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    monitors = {}
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def _cb(hmon, _hdc, _rect_ptr, _lparam):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
            r = info.rcMonitor
            monitors[info.szDevice] = (r.left, r.top, r.right, r.bottom)
        return True

    user32.EnumDisplayMonitors(None, None, callback_type(_cb), 0)
    return monitors


def visible_window_rects_by_screen(screens, exclude_pid=None):
    """Capture visible top-level window rects in Z-order mapped to each screen's local logical coords.

    Returns {id(screen): [QRectF, ...]} safely; returns empty lists on non-Windows or any API failure.
    """
    result = {id(s): [] for s in screens}
    if sys.platform != 'win32' or not screens:
        return result
    try:
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        dwmapi = ctypes.WinDLL('dwmapi', use_last_error=True)
        skip_pid = os.getpid() if exclude_pid is None else exclude_pid

        raw_rects = []
        skip_classes = {'Progman', 'WorkerW', 'Windows.UI.Core.CoreWindow', 'EdgeUiInputTopWndClass'}
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        class_buf = ctypes.create_unicode_buffer(128)
        rect = wintypes.RECT()
        cloaked = ctypes.c_int(0)
        pid = wintypes.DWORD(0)

        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        DWMWA_CLOAKED = 14
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080

        def _enum(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                return True
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if skip_pid and pid.value == skip_pid:
                return True
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_TRANSPARENT:
                return True
            cloaked.value = 0
            if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0:
                if cloaked.value != 0:
                    return True
            user32.GetClassNameW(hwnd, class_buf, 128)
            cls_name = class_buf.value
            if cls_name in skip_classes:
                return True
            if (ex_style & WS_EX_TOOLWINDOW) and cls_name != 'Shell_TrayWnd':
                return True
            if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
                if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return True
            if rect.right - rect.left < 28 or rect.bottom - rect.top < 28:
                return True
            raw_rects.append((rect.left, rect.top, rect.right, rect.bottom))
            return True

        user32.EnumWindows(enum_proc(_enum), 0)
        if not raw_rects:
            return result

        monitors = _physical_monitors()
        for screen in screens:
            geom = screen.geometry()
            if geom.width() <= 0 or geom.height() <= 0:
                continue
            name = screen.name() if hasattr(screen, 'name') else ''
            mon = monitors.get(name)
            if mon is None and len(monitors) == 1:
                mon = next(iter(monitors.values()))
            if mon is None:
                dpr = float(screen.devicePixelRatio()) if hasattr(screen, 'devicePixelRatio') else 1.0
                ml, mt = round(geom.left() * dpr), round(geom.top() * dpr)
                mr, mb = ml + round(geom.width() * dpr), mt + round(geom.height() * dpr)
            else:
                ml, mt, mr, mb = mon
            mw = max(1, mr - ml)
            mh = max(1, mb - mt)
            sx = geom.width() / mw
            sy = geom.height() / mh
            screen_rects = []
            for rl, rt, rr, rb in raw_rects:
                il, it = max(ml, rl), max(mt, rt)
                ir, ib = min(mr, rr), min(mb, rb)
                if ir - il < 24 or ib - it < 24:
                    continue
                local = QRectF((il - ml) * sx, (it - mt) * sy, (ir - il) * sx, (ib - it) * sy)
                if local.width() >= 24 and local.height() >= 24:
                    screen_rects.append(local)
            result[id(screen)] = screen_rects
    except Exception:
        return {id(s): [] for s in screens}
    return result
