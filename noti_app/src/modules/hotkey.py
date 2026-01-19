"""Global hotkey listener for the notification app"""

from pynput import keyboard


def setup_global_hotkey(app):
    """Setup global hotkey listener for Ctrl+,"""
    def on_activate():
        """Toggle window visibility when hotkey is pressed"""
        print("[HOTKEY] Ctrl+, pressed - toggling window")
        if app.window_visible:
            app.hide_window()
        else:
            app.show_window()

    # Create hotkey combination: Ctrl+,
    hotkey = keyboard.HotKey(
        keyboard.HotKey.parse('<ctrl>+,'),
        on_activate
    )

    def for_canonical(f):
        return lambda k: f(hotkey_listener.canonical(k))

    # Start global keyboard listener in background thread
    hotkey_listener = keyboard.Listener(
        on_press=for_canonical(hotkey.press),
        on_release=for_canonical(hotkey.release)
    )
    hotkey_listener.start()

    print("[HOTKEY] Global hotkey Ctrl+, registered")
    return hotkey_listener
