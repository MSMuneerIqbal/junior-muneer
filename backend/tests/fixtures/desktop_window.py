"""Disposable native Windows editor for an explicitly run desktop-adapter check; no user files are opened.

Run by scripts/check_desktop_native.py. Its only window closes itself after 60 seconds.
"""

import json
import os
import ctypes
from ctypes import wintypes

import win32api
import win32con
import win32gui

editor = 0
window = 0


def handler(hwnd, message, wparam, lparam):
    if message in (win32con.WM_CLOSE, win32con.WM_TIMER):
        win32gui.DestroyWindow(hwnd)
        return 0
    if message == win32con.WM_DESTROY:
        win32gui.PostQuitMessage(0)
        return 0
    if message == win32con.WM_SETFOCUS and editor and hwnd == window:
        win32gui.SetFocus(editor)
    return win32gui.DefWindowProc(hwnd, message, wparam, lparam)


instance = win32api.GetModuleHandle(None)
klass = win32gui.WNDCLASS()
klass.hInstance, klass.lpszClassName, klass.lpfnWndProc = instance, "JuniorDesktopFixture", handler
klass.hbrBackground = win32con.COLOR_WINDOW + 1
win32gui.RegisterClass(klass)
window = win32gui.CreateWindowEx(0, klass.lpszClassName, "Junior synthetic desktop fixture",
                                win32con.WS_OVERLAPPEDWINDOW, 150, 150, 680, 430, 0, 0, instance, None)
approval_window = win32gui.CreateWindowEx(0, klass.lpszClassName, "Junior synthetic approval simulator",
                                         win32con.WS_OVERLAPPEDWINDOW, 900, 150, 300, 200, 0, 0, instance, None)
win32gui.ShowWindow(approval_window, win32con.SW_SHOW)
editor = win32gui.CreateWindowEx(0, "Edit", "Junior synthetic desktop fixture",
                                win32con.WS_VISIBLE | win32con.WS_CHILD | win32con.WS_BORDER | win32con.ES_MULTILINE,
                                20, 30, 620, 300, window, 100, instance, None)
win32gui.ShowWindow(window, win32con.SW_SHOW)
win32gui.UpdateWindow(window)
try:
    win32gui.SetForegroundWindow(window)
    win32gui.SetFocus(editor)
except Exception:
    pass
timer = ctypes.windll.user32.SetTimer
timer.argtypes, timer.restype = [wintypes.HANDLE, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p], ctypes.c_size_t
timer(window, 1, 60000, None)
print(json.dumps({"handle": window, "editor": editor, "approval_window": approval_window,
                  "pid": os.getpid(), "parent_pid": os.getppid()}), flush=True)
win32gui.PumpMessages()
