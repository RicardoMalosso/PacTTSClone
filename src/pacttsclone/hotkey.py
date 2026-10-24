"""Windows global hotkey, registered on its own native message-loop thread."""

import sys
import threading


def parse_hotkey(value):
    parts = value.upper().replace(" ", "").split("+")
    mods = 0x4000
    names = {"CTRL": 2, "CONTROL": 2, "ALT": 1, "SHIFT": 4}
    for modifier in parts[:-1]:
        if modifier not in names:
            raise ValueError("Use Ctrl/Alt/Shift plus a letter, digit or F1–F11.")
        mods |= names[modifier]
    key = parts[-1]
    if not parts[:-1]:
        raise ValueError("Use at least one modifier (Ctrl, Alt or Shift).")
    if len(key) == 1 and key.isascii() and key.isalnum():
        return mods, ord(key)
    if key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 11:
        return mods, 0x70 + int(key[1:]) - 1
    raise ValueError("Use a letter, digit or F1–F11. F12 is reserved by Windows.")


class GlobalHotkey:
    def __init__(self, callback):
        self.callback = callback
        self.stop = threading.Event()
        self.value = ""
        self.status = "Unavailable on this platform; buttons and focused-browser shortcut work."
        self.thread = None

    def configure(self, value):
        if value:
            parse_hotkey(value)
        self.close()
        self.value = value
        self.stop = threading.Event()
        if not value:
            self.status = "Disabled"
        elif sys.platform == "win32":
            ready = threading.Event()
            self.thread = threading.Thread(target=self._run, args=(ready,), daemon=True)
            self.thread.start()
            ready.wait(2)
        else:
            self.status = "Unavailable on this platform; buttons and focused-browser shortcut work."
        return self.status

    def _run(self, ready):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        registered = user32.RegisterHotKey(None, 8129, *parse_hotkey(self.value))
        self.status = "Active: " + self.value if registered else "Unavailable: shortcut is in use."
        ready.set()
        if not registered:
            return
        msg = wintypes.MSG()
        try:
            while not self.stop.wait(0.025):
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312:
                        self.callback()
        finally:
            user32.UnregisterHotKey(None, 8129)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(2)
            self.thread = None
