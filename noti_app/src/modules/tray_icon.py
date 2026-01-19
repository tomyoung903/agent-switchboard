"""System tray icon functionality for the notification app"""

import threading
import pystray
from PIL import Image, ImageDraw


def create_tray_icon(app):
    """Create and setup the system tray icon"""
    # Create a simple icon (bell emoji representation)
    icon_image = Image.new('RGB', (64, 64), color='#2C3E50')
    draw = ImageDraw.Draw(icon_image)

    # Draw a bell shape (simple circle for now)
    draw.ellipse([16, 16, 48, 48], fill='#3498DB')

    # Create tray icon menu
    menu = pystray.Menu(
        pystray.MenuItem('Show', app.show_window),
        pystray.MenuItem('Hide', app.hide_window),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('Exit', app.quit_app)
    )

    # Create tray icon
    tray_icon = pystray.Icon(
        "Notifications",
        icon_image,
        "Notification App",
        menu
    )

    # Run tray icon in separate thread
    tray_thread = threading.Thread(target=tray_icon.run, daemon=True)
    tray_thread.start()

    print("[TRAY] System tray icon created")
    return tray_icon
