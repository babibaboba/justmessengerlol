import threading
from pynput import keyboard

class HotkeyManager(threading.Thread):
    def __init__(self, callback_queue):
        super().__init__(daemon=True)
        self.callback_queue = callback_queue
        self.hotkeys = {}
        self.listener = None

    def run(self):
        self.listener = keyboard.Listener(on_press=self.on_press)
        self.listener.start()
        self.listener.join()

    def stop(self):
        if self.listener:
            self.listener.stop()

    def on_press(self, key):
        for hotkey, action in self.hotkeys.items():
            if key == hotkey:
                self.callback_queue.put(('hotkey_pressed', action))

    def set_hotkey(self, action, key_str):
        try:
            key = keyboard.KeyCode.from_char(key_str)
            self.hotkeys[key] = action
            return True
        except TypeError:
            try:
                key = keyboard.Key[key_str.lower()]
                self.hotkeys[key] = action
                return True
            except KeyError:
                return False