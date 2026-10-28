"""Windows adapter for Junior's own runtime, separate from Codex's computer-use plugin.

No terminal, browser, authentication or security UI. Observation is window-scoped; input checks foreground
and focus again immediately before injection. All public operations are called by desktop.py's guarded worker.
"""

import ctypes
import io
import os
import time
from ctypes import wintypes
from pathlib import Path


class DesktopRefused(ValueError):
    pass


class DesktopUncertain(RuntimeError):
    pass


APPS = {
    "notepad.exe": "Notepad", "winword.exe": "Microsoft Word", "excel.exe": "Microsoft Excel",
    "powerpnt.exe": "Microsoft PowerPoint", "mspaint.exe": "Paint", "calc.exe": "Calculator",
    "calculatorapp.exe": "Calculator", "vlc.exe": "VLC media player",
    "wmplayer.exe": "Windows Media Player", "music.ui.exe": "Windows Music",
    "mediaplayer.exe": "Media Player", "spotify.exe": "Spotify", "itunes.exe": "iTunes",
}
KEYS = {"ctrl+a": [17, 65], "ctrl+z": [17, 90], "ctrl+y": [17, 89], "ctrl+b": [17, 66],
        "ctrl+i": [17, 73], "ctrl+u": [17, 85], "left": [37], "right": [39], "up": [38],
        "down": [40], "home": [36], "end": [35], "enter": [13], "backspace": [8], "delete": [46]}
EDITABLE = {"EditControl", "DocumentControl"}


class _Keyboard(ctypes.Structure):
    _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


class _Mouse(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("data", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]


class _InputData(ctypes.Union):
    _fields_ = [("keyboard", _Keyboard), ("mouse", _Mouse)]


class _Input(ctypes.Structure):
    _fields_ = [("kind", wintypes.DWORD), ("data", _InputData)]


def _send(inputs):
    array = (_Input * len(inputs))(*inputs)
    fn = ctypes.windll.user32.SendInput
    fn.argtypes, fn.restype = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int], wintypes.UINT
    if fn(len(inputs), array, ctypes.sizeof(_Input)) != len(inputs):
        raise DesktopUncertain("Windows didn't accept all input. Some input may have happened; inspect before retrying.")


class WindowsDesktop:
    """Stateless adapter. UIA objects are created and consumed in the same worker thread."""

    def __enter__(self):
        if os.name != "nt":
            raise DesktopRefused("Desktop controls need the Windows PC Helper/local backend, not the VPS desktop.")
        import win32api
        import win32gui
        import win32process
        import uiautomation as auto

        self.gui, self.api, self.process, self.auto = win32gui, win32api, win32process, auto
        self.initializer = auto.UIAutomationInitializerInThread()
        self.initializer.__enter__()
        dpi = ctypes.windll.user32.SetThreadDpiAwarenessContext
        dpi.argtypes, dpi.restype = [wintypes.HANDLE], wintypes.HANDLE
        self._dpi = dpi(ctypes.c_void_p(-4))
        try:
            self.interactive()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *args):
        if self._dpi:
            ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(self._dpi))
        self.initializer.__exit__(*args)

    def interactive(self):
        api = ctypes.WinDLL("user32", use_last_error=True)
        api.OpenInputDesktop.argtypes, api.OpenInputDesktop.restype = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE
        api.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        api.CloseDesktop.argtypes = [wintypes.HANDLE]
        desk = api.OpenInputDesktop(0, False, 1)
        if not desk:
            raise DesktopRefused("The desktop is locked or unavailable. Unlock it yourself; Junior cannot use security screens.")
        try:
            name, size = ctypes.create_unicode_buffer(256), wintypes.DWORD()
            if not api.GetUserObjectInformationW(desk, 2, name, ctypes.sizeof(name), ctypes.byref(size)) or name.value.lower() != "default":
                raise DesktopRefused("A secure or non-interactive desktop is active. Finish it yourself first.")
        finally:
            api.CloseDesktop(desk)

    def window(self, hwnd: int) -> dict:
        if not self.gui.IsWindow(hwnd) or not self.gui.IsWindowVisible(hwnd):
            raise DesktopRefused("That window is no longer available. List windows again.")
        thread, pid = self.process.GetWindowThreadProcessId(hwnd)
        process = self.api.OpenProcess(0x1000, False, pid)
        try:
            path, size = ctypes.create_unicode_buffer(2048), wintypes.DWORD(2048)
            query = ctypes.windll.kernel32.QueryFullProcessImageNameW
            query.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
            if not query(int(process), 0, path, ctypes.byref(size)):
                raise DesktopRefused("Windows won't identify that app. Elevated/security apps are not controlled.")
            started = self.process.GetProcessTimes(process)["CreationTime"].isoformat()
        finally:
            process.Close()
        return {"handle": hwnd, "pid": pid, "started": started, "app": Path(path.value).name.lower(),
                "title": self.gui.GetWindowText(hwnd)[:250], "class": self.gui.GetClassName(hwnd),
                "rect": list(self.gui.GetWindowRect(hwnd)), "minimized": bool(self.gui.IsIconic(hwnd)),
                "foreground": self.gui.GetForegroundWindow() == hwnd}

    def windows(self) -> list[dict]:
        result = []
        def add(hwnd, _):
            if len(result) >= 100 or not self.gui.IsWindowVisible(hwnd) or not self.gui.GetWindowText(hwnd):
                return
            try:
                result.append(self.window(hwnd))
            except Exception:
                pass  # unreadable windows are not automation targets
        self.gui.EnumWindows(add, None)
        return result

    @staticmethod
    def control_info(control) -> dict | None:
        if control is None:
            return None
        rect = control.BoundingRectangle
        password = bool(control.IsPassword)
        return {"runtime": list(control.GetRuntimeId()), "name": "[password field]" if password else control.Name[:200],
                "type": control.ControlTypeName, "rect": [rect.left, rect.top, rect.right, rect.bottom],
                "password": password, "enabled": bool(control.IsEnabled), "pid": control.ProcessId}

    def observe(self, hwnd: int) -> dict:
        window = self.window(hwnd)
        root = self.auto.ControlFromHandle(hwnd)
        controls, pending, end = [], [(root, 0)], time.monotonic() + 2
        while pending and len(controls) < 80 and time.monotonic() < end:
            control, depth = pending.pop(0)
            info = self.control_info(control)
            if info:
                info["index"] = len(controls)
                controls.append(info)
            if depth < 5 and info and not info["password"]:
                pending.extend((child, depth + 1) for child in control.GetChildren()[:80])
        focused = self.control_info(self.auto.GetFocusedControl()) if window["foreground"] else None
        if focused and focused["pid"] != window["pid"]:
            focused = None
        return {"window": window, "controls": controls, "focused": focused}

    def capture(self, hwnd: int) -> bytes:
        from PIL import Image, ImageStat
        import win32ui
        window = self.window(hwnd)
        left, top, right, bottom = window["rect"]
        if window["minimized"] or not 0 < (right - left) * (bottom - top) <= 8_000_000:
            raise DesktopRefused("Restore that window first; minimized or oversized windows cannot be captured.")
        # Print ONLY this window into a private bitmap; never fall back to screen/DC cropping of visible pixels.
        window_dc = self.gui.GetWindowDC(hwnd)
        source = win32ui.CreateDCFromHandle(window_dc)
        memory = source.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        try:
            bitmap.CreateCompatibleBitmap(source, right - left, bottom - top)
            memory.SelectObject(bitmap)
            render = ctypes.windll.user32.PrintWindow
            render.argtypes, render.restype = [wintypes.HANDLE, wintypes.HANDLE, wintypes.UINT], wintypes.BOOL
            if not render(hwnd, memory.GetSafeHdc(), 2):
                raise DesktopRefused("This app doesn't support a window-only capture. No screen fallback is used.")
            image = Image.frombytes("RGB", (right - left, bottom - top), bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1)
        finally:
            memory.DeleteDC()
            source.DeleteDC()
            self.gui.ReleaseDC(hwnd, window_dc)
            if bitmap.GetHandle():
                self.gui.DeleteObject(bitmap.GetHandle())
        if max(ImageStat.Stat(image).var) < 0.1:
            raise DesktopRefused("The app returned a blank window capture. Bring it into view and observe again.")
        if self.window(hwnd)["rect"] != window["rect"] or not 0 < image.width * image.height <= 8_000_000:
            raise DesktopRefused("Window capture dimensions changed. Observe it again.")
        image.thumbnail((1280, 800))
        out = io.BytesIO()
        image.save(out, "PNG")
        if out.tell() > 4 * 1024 * 1024:
            raise DesktopRefused("The screenshot is too large.")
        return out.getvalue()

    def foreground(self, hwnd: int):
        self.interactive()
        if self.gui.GetForegroundWindow() != hwnd:
            raise DesktopRefused("Focus moved to another window. Nothing was typed or clicked; observe/focus the target again.")

    def focus(self, hwnd: int):
        self.gui.ShowWindow(hwnd, 9)  # restore only the explicitly approved window
        self.auto.ControlFromHandle(hwnd).SetFocus()
        self.foreground(hwnd)

    def close_window(self, hwnd: int, check):
        check()
        self.gui.PostMessage(hwnd, 0x0010, 0, 0)  # WM_CLOSE: let the app handle unsaved work
        time.sleep(0.5)
        if self.gui.IsWindow(hwnd):
            raise DesktopUncertain("The close request was sent, but the window remains open. It may need confirmation; check it before trying again.")

    def focused(self, hwnd: int) -> dict | None:
        self.foreground(hwnd)
        info = self.control_info(self.auto.GetFocusedControl())
        if info and info["pid"] == self.window(hwnd)["pid"]:
            return info
        return None

    def focus_control(self, hwnd: int, runtime: list[int]):
        self.focus(hwnd)
        pending, end = [(self.auto.ControlFromHandle(hwnd), 0)], time.monotonic() + 2
        seen = 0
        while pending and seen < 80 and time.monotonic() < end:
            control, depth = pending.pop(0)
            seen += 1
            if list(control.GetRuntimeId()) == runtime:
                if control.IsPassword or not control.IsEnabled or control.ControlTypeName not in EDITABLE:
                    raise DesktopRefused("The approved edit control is no longer editable.")
                control.SetFocus()
                info = self.focused(hwnd)
                if not info or info["runtime"] != runtime or info["password"]:
                    raise DesktopRefused("Windows did not focus the approved edit control. Nothing will be typed.")
                return
            if depth < 5 and not control.IsPassword:
                pending.extend((child, depth + 1) for child in control.GetChildren()[:80])
        raise DesktopRefused("The approved edit control disappeared. Nothing will be typed.")

    def point(self, hwnd: int, x: int, y: int) -> dict:
        self.foreground(hwnd)
        window = self.window(hwnd)
        left, top, right, bottom = window["rect"]
        if not left <= x < right or not top <= y < bottom:
            raise DesktopRefused("That point is outside the target window.")
        hit = self.gui.WindowFromPoint((x, y))
        if hit != hwnd and not self.gui.IsChild(hwnd, hit):
            raise DesktopRefused("Another window covers that point. Nothing was clicked.")
        return self.control_info(self.auto.ControlFromPoint(x, y))

    def click(self, hwnd: int, x: int, y: int, check):
        self.api.SetCursorPos((x, y))
        check()
        self.point(hwnd, x, y)
        _send([_Input(0, _InputData(mouse=_Mouse(flags=2))), _Input(0, _InputData(mouse=_Mouse(flags=4)))])

    def type_text(self, hwnd: int, text: str, check):
        raw = text.encode("utf-16-le")
        for offset in range(0, len(raw), 32):
            check()  # recheck both foreground and the exact focused control before each short batch
            self.foreground(hwnd)
            inputs = []
            for pos in range(offset, min(offset + 32, len(raw)), 2):
                unit = int.from_bytes(raw[pos:pos + 2], "little")
                inputs.extend([_Input(1, _InputData(keyboard=_Keyboard(scan=unit, flags=4))),
                               _Input(1, _InputData(keyboard=_Keyboard(scan=unit, flags=6)))])
            _send(inputs)

    def press(self, hwnd: int, key: str, check):
        check()
        self.foreground(hwnd)
        codes = KEYS[key]
        _send([_Input(1, _InputData(keyboard=_Keyboard(vk=code))) for code in codes]
              + [_Input(1, _InputData(keyboard=_Keyboard(vk=code, flags=2))) for code in reversed(codes)])
