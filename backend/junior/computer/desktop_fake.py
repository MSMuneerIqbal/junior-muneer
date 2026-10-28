"""Fake-AI desktop demo for dashboard checks. Never touches the owner's real windows or input devices."""

import copy
import io

from PIL import Image, ImageDraw

from junior.computer.desktop_native import DesktopRefused


class FakeDesktop:
    text = "A simulated Notepad document."
    selected = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def window(self, hwnd):
        if hwnd != 8001:
            raise DesktopRefused("Demo window not found.")
        return {"handle": 8001, "pid": 8001, "started": "fake-desktop", "app": "notepad.exe",
                "title": "Junior desktop demo", "class": "FakeNotepad", "rect": [0, 0, 800, 500],
                "minimized": False, "foreground": True}

    def windows(self):
        return [self.window(8001)]

    def observe(self, hwnd):
        control = {"runtime": [8001, 1], "name": "Text editor", "type": "DocumentControl",
                   "rect": [10, 50, 790, 490], "password": False, "enabled": True, "pid": 8001, "index": 0}
        return {"window": self.window(hwnd), "controls": [control], "focused": copy.deepcopy(control)}

    def capture(self, hwnd):
        self.window(hwnd)
        image = Image.new("RGB", (800, 500), "white")
        draw = ImageDraw.Draw(image)
        draw.text((15, 15), "Simulated Notepad - no real PC input", fill="black")
        draw.text((15, 60), self.text[:500], fill="black")
        result = io.BytesIO()
        image.save(result, "PNG")
        return result.getvalue()

    def foreground(self, hwnd):
        self.window(hwnd)

    def focus(self, hwnd):
        self.window(hwnd)

    def close_window(self, hwnd, check):
        check()

    def focused(self, hwnd):
        return self.observe(hwnd)["focused"]

    def focus_control(self, hwnd, runtime):
        self.window(hwnd)

    def point(self, hwnd, x, y):
        return self.focused(hwnd)

    def click(self, hwnd, x, y, check):
        check()

    def type_text(self, hwnd, text, check):
        check()
        type(self).text = text if self.selected else self.text + text
        type(self).selected = False

    def press(self, hwnd, key, check):
        check()
        if key == "ctrl+a":
            type(self).selected = True
        elif key == "enter":
            type(self).text += "\n"
