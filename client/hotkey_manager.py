import threading
from pynput import keyboard

class HotkeyManager(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.hotkey = None
        self.callback = None
        self.running = True
        self.listener = None

    def set_hotkey(self, key_combination):
        """
        Sets the hotkey to listen for.
        key_combination should be a set of pynput.keyboard.Key or pynput.keyboard.KeyCode
        e.g., {keyboard.Key.ctrl, keyboard.KeyCode.from_char('m')}
        """
        self.hotkey = key_combination

    def register_callback(self, func):
        self.callback = func

    def run(self):
        # A set of currently pressed keys
        current_keys = set()

        def on_press(key):
            if self.hotkey and key in self.hotkey:
                current_keys.add(key)
                if all(k in current_keys for k in self.hotkey):
                    if self.callback:
                        self.callback()
            
        def on_release(key):
            try:
                current_keys.remove(key)
            except KeyError:
                pass # Key was not in the set

        # Collect events until released
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            self.listener = listener
            listener.join()

    def stop(self):
        if self.listener:
            self.listener.stop()