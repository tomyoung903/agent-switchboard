#!/usr/bin/env python3
"""
Wrapper script to launch the notification app from the noti_app root directory.
This ensures that src imports work correctly.
"""

import sys
import os

# Add the noti_app directory to the path so we can import src modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Now import and run the app
from src.notification_app import NotificationApp, tk

if __name__ == "__main__":
    root = tk.Tk()
    app = NotificationApp(root)
    root.mainloop()
