import tkinter as tk
import subprocess
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageTk
import atexit
import os
import signal
import ctypes
import pystray
from pynput import keyboard

# ==================== DPI AWARENESS (Windows) ====================
# MUST be called BEFORE creating any Tk() window to fix blurry text
DPI_SCALE = 1.0
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    # Get the scaling factor (e.g., 1.25 for 125%, 1.5 for 150%)
    DPI_SCALE = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
except (AttributeError, OSError):
    pass  # Not Windows or shcore not available
from .styles import (
    BG_PRIMARY, BG_SECONDARY, BG_SELECTED,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_ACCENT,
    WINDOW_PADDING, BAR_PADDING_X, BAR_PADDING_Y, BAR_SPACING, BORDER_WIDTH, CORNER_RADIUS,
    TITLE_FONT, CONTENT_FONT, HINT_FONT,
    SELECTION_BAR_COLOR, SELECTION_BAR_WIDTH,
    get_message_bar_style, get_status_color,
    apply_window_theme
)
from .ui_utils import create_rounded_rectangle_image
from .db import (
    get_all_windows, update_window_status, delete_window,
    get_db_hash, migrate_from_jsonl, DB_DIR
)

# ==================== CONFIGURATION ====================
# Window appearance and position settings (scaled for DPI, reduced by 20%)
WINDOW_WIDTH = int(304 * DPI_SCALE)   # 380 * 0.8
WINDOW_HEIGHT = int(200 * DPI_SCALE)  # 250 * 0.8
WINDOW_RESIZABLE = False

# Position settings: "center", "bottom-right", "top-right", "bottom-left", "top-left", "upper-monitor-center"
WINDOW_POSITION = "upper-monitor-center"
POSITION_OFFSET_X = 500
POSITION_OFFSET_Y = 500

# Hard-coded spawn position for upper monitor center (adjust empirically)
SPAWN_X = 1500  # Adjust: increase to move right, decrease to move left
SPAWN_Y = -1100 # Adjust: increase (less negative) to move down, decrease (more negative) to move up

# Database configuration now handled by db module
import platform
import sys

# Legacy JSONL path for migration (one-time) - in original location
if platform.system() == 'Windows':
    LEGACY_JSONL = Path(r"\\wsl.localhost\Ubuntu") / "home" / "tom" / "windows" / "noti_app" / "window_status" / "windows.jsonl"
else:
    LEGACY_JSONL = Path(__file__).parent.parent / "window_status" / "windows.jsonl"

# Also check the old DB location for migration
if platform.system() == 'Windows':
    OLD_DB_LOCATION = Path(r"\\wsl.localhost\Ubuntu") / "home" / "tom" / "windows" / "noti_app" / "window_status" / "windows.db"
else:
    OLD_DB_LOCATION = Path(__file__).parent.parent / "window_status" / "windows.db"

# Popup behavior configuration
# Set POPUP_DISABLED = True to prevent window from auto-popping up
POPUP_DISABLED = True
POPUP_STATUSES = ["done"]  # Only used if POPUP_DISABLED = False

# Debug option - disabled
DEBUG_MODE = False
# ========================================================

def load_window_statuses():
    """Load window statuses from SQLite database, sorted by status priority"""
    windows = get_all_windows()

    if not windows:
        return get_default_windows()

    # Sort by status priority: done (top) -> ongoing -> other/None -> addressed (last)
    def status_priority(w):
        status = (w.get('status') or '').lower()
        if status == 'done':
            return 0
        elif status == 'ongoing':
            return 1
        elif status == 'addressed':
            return 3
        else:
            return 2  # None or other statuses in the middle

    return sorted(windows, key=status_priority)


def save_window_statuses(windows):
    """Save window statuses to SQLite database (batch update)"""
    try:
        for window in windows:
            window_name = window.get('window_name')
            if window_name:
                update_window_status(window_name, window.get('status'))
        print(f"[DB] Saved {len(windows)} windows")
        return True
    except Exception as e:
        print(f"Error saving window statuses: {e}")
        return False


def get_default_windows():
    """Return default sample windows when database is empty"""
    return [
        {"window_name": "osora", "status": None},
        {"window_name": "osora2", "status": None},
        {"window_name": "osora3", "status": None}
    ]


class NotificationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Notifications")
        self.root.resizable(False, False)

        # Migrate from JSONL to SQLite (one-time)
        if LEGACY_JSONL.exists():
            print("[APP] Migrating from JSONL to SQLite...")
            migrate_from_jsonl(LEGACY_JSONL)

        # Keep window in taskbar but minimize title bar interaction
        # Don't use overrideredirect as it removes from taskbar
        self.root.attributes('-toolwindow', False)

        # Track window visibility state
        self.window_visible = True

        # Track selected message index
        self.selected_index = 0
        self.message_bars = []


        # Start the ntfy listener subprocess
        self.start_listener_subprocess()

        # Get screen dimensions
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # Calculate position based on WINDOW_POSITION setting
        if WINDOW_POSITION == "upper-monitor-center":
            # Use hard-coded values (adjusted empirically)
            x_position = SPAWN_X
            y_position = SPAWN_Y
        elif WINDOW_POSITION == "bottom-right":
            x_position = screen_width - WINDOW_WIDTH - POSITION_OFFSET_X
            y_position = screen_height - WINDOW_HEIGHT - POSITION_OFFSET_Y
        elif WINDOW_POSITION == "bottom-left":
            x_position = POSITION_OFFSET_X
            y_position = screen_height - WINDOW_HEIGHT - POSITION_OFFSET_Y
        elif WINDOW_POSITION == "top-right":
            x_position = screen_width - WINDOW_WIDTH - POSITION_OFFSET_X
            y_position = POSITION_OFFSET_Y
        elif WINDOW_POSITION == "top-left":
            x_position = POSITION_OFFSET_X
            y_position = POSITION_OFFSET_Y
        else:  # center
            x_position = (screen_width - WINDOW_WIDTH) // 2
            y_position = (screen_height - WINDOW_HEIGHT) // 2

        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{x_position}+{y_position}")
        apply_window_theme(self.root, BG_PRIMARY)

        # Setup system tray icon
        self.setup_tray_icon()

        # Setup global hotkey (Alt+B)
        self.setup_global_hotkey()

        # Start window hidden (minimize to tray on start)
        self.root.withdraw()
        self.window_visible = False

        # Create main frame with padding (scaled for DPI)
        window_padding_scaled = int(WINDOW_PADDING * DPI_SCALE)
        main_frame = tk.Frame(self.root, bg=BG_PRIMARY)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=window_padding_scaled, pady=window_padding_scaled)

        # Create canvas and scrollbar for scrolling
        canvas = tk.Canvas(main_frame, bg=BG_PRIMARY, highlightthickness=0)
        scrollbar = tk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=BG_PRIMARY)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Pack scrollbar and canvas
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Messages will be added to this scrollable frame
        messages_container = scrollable_frame

        # Bind mouse wheel to scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)  # Windows
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))  # Linux scroll up
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))  # Linux scroll down

        # Store references for dynamic message addition and scrolling
        self.messages_container = messages_container
        self.canvas = canvas

        # Load windows from status file (or use defaults if file is empty)
        # Windows are already sorted by timestamp (most recent first)
        self.windows = load_window_statuses()

        # Alias for backwards compatibility (windows are displayed as messages in UI)
        self.messages = self.windows

        # Create message bars
        for i, window in enumerate(self.windows):
            bar = self.create_message_bar(messages_container, i, window)
            self.message_bars.append(bar)

        # Create footer with keyboard hints
        footer_frame = tk.Frame(main_frame, bg=BG_PRIMARY)
        footer_frame.pack(fill=tk.X, pady=(window_padding_scaled, 0))

        hint_label = tk.Label(
            footer_frame,
            text="↑↓ Tab to select • Enter to trigger • A addressed • Del remove",
            font=HINT_FONT,
            bg=BG_PRIMARY,
            fg=TEXT_ACCENT
        )
        hint_label.pack(anchor="e")

        # Bind keyboard events
        self.root.bind("<Tab>", self.on_tab_pressed)
        self.root.bind("<Return>", self.on_enter_pressed)
        self.root.bind("<Up>", self.on_up_pressed)
        self.root.bind("<Down>", self.on_down_pressed)
        self.root.bind("<Prior>", self.on_page_up)  # Page Up
        self.root.bind("<Next>", self.on_page_down)  # Page Down
        self.root.bind("<Home>", self.on_home_pressed)  # Jump to first window
        self.root.bind("<End>", self.on_end_pressed)  # Jump to last window
        self.root.bind("<Delete>", self.on_delete_pressed)  # Delete selected window
        self.root.bind("a", self.on_addressed_pressed)  # Mark as addressed
        self.root.bind("<Key>", self.on_letter_pressed)  # Any letter key hides window

        # Track message count for detecting updates
        self.last_message_count = len(self.messages)

        # Start background monitor thread
        self.monitor_running = True
        monitor_thread = threading.Thread(
            target=self.monitor_queue_for_updates,
            daemon=True
        )
        monitor_thread.start()

        # Start listener health check (every 30 seconds)
        self.check_listener_health()

        # Set focus and highlight first message
        self.root.focus()
        self.update_selection()

    # ====== UI RENDERING ======
    # Functions for creating and rendering message bars in the UI

    def create_message_bar(self, parent, index, message):
        """Create a keyboard-navigable message bar with Pillow rounded corners"""
        message['index'] = index

        # Container with padding
        container = tk.Frame(parent, bg=BG_PRIMARY, highlightthickness=0)
        container.pack(fill=tk.X, pady=int(BAR_SPACING * DPI_SCALE) // 2, padx=0)

        # Calculate bar dimensions to fit window
        # Note: WINDOW_WIDTH is already scaled for DPI
        bar_width = WINDOW_WIDTH - int(WINDOW_PADDING * DPI_SCALE) * 2
        bar_height = int(36 * DPI_SCALE)

        # Create rounded rectangle images for both states (normal and selected)
        corner_radius_scaled = int(CORNER_RADIUS * DPI_SCALE)
        bg_img_normal = create_rounded_rectangle_image(bar_width, bar_height, corner_radius_scaled, BG_SECONDARY)
        bg_img_selected = create_rounded_rectangle_image(bar_width, bar_height, corner_radius_scaled, BG_SELECTED)

        # Convert to PhotoImages
        if not hasattr(self, 'photo_images'):
            self.photo_images = []

        photo_normal = ImageTk.PhotoImage(bg_img_normal)
        photo_selected = ImageTk.PhotoImage(bg_img_selected)
        self.photo_images.append(photo_normal)  # Keep references
        self.photo_images.append(photo_selected)

        # Create canvas with background image
        canvas = tk.Canvas(
            container,
            width=bar_width,
            height=bar_height,
            bg=BG_PRIMARY,
            highlightthickness=0,
            relief=tk.FLAT,
            bd=0
        )
        canvas.pack()
        bg_image_id = canvas.create_image(0, 0, image=photo_normal, anchor='nw')

        # Create single content frame on top of canvas (simplified hierarchy)
        content_frame = tk.Frame(canvas, bg=BG_SECONDARY, highlightthickness=0)
        canvas.create_window(bar_width // 2, bar_height // 2, window=content_frame,
                           width=bar_width - corner_radius_scaled * 2, height=bar_height - int(8 * DPI_SCALE))

        # Window name label on the LEFT (main focus)
        window_label = tk.Label(
            content_frame,
            text=message.get("window_name", "Unknown").upper(),  # Uppercase for emphasis
            font=TITLE_FONT,
            bg=BG_SECONDARY,
            fg=TEXT_PRIMARY,
            anchor="w"
        )
        padding_x_scaled = int(BAR_PADDING_X * DPI_SCALE)
        window_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(padding_x_scaled, 0))

        # Status label on the RIGHT (secondary info) with color-coded status
        if message.get("status"):
            status_color = get_status_color(message["status"], is_selected=False)
            status_label = tk.Label(
                content_frame,
                text=message["status"],
                font=CONTENT_FONT,
                bg=BG_SECONDARY,
                fg=status_color,  # Color-coded status
                anchor="e"
            )
            status_label.pack(side=tk.RIGHT, padx=(0, padding_x_scaled))
        else:
            status_label = None

        # Store references for selection updates (using content_frame as the main bar reference)
        content_frame._window_label = window_label
        content_frame._status_label = status_label
        content_frame._message = message
        content_frame._canvas = canvas
        content_frame._bg_image_id = bg_image_id
        content_frame._photo_normal = photo_normal
        content_frame._photo_selected = photo_selected

        return content_frame

    # ====== SELECTION & INPUT ======
    # Functions for handling keyboard navigation and message selection

    def update_selection(self):
        """Update visual state of all message bars based on selected_index"""
        for i, bar in enumerate(self.message_bars):
            is_selected = (i == self.selected_index)
            style = get_message_bar_style(is_selected=is_selected)
            bg = style["bg"]
            # Update canvas background image (handles rounded corners)
            if is_selected:
                bar._canvas.itemconfig(bar._bg_image_id, image=bar._photo_selected)
            else:
                bar._canvas.itemconfig(bar._bg_image_id, image=bar._photo_normal)
            # Update content frame and labels
            bar.configure(bg=bg)
            bar._window_label.configure(bg=bg, fg=style["fg_title"])
            if bar._status_label:
                # Use color-coded status when not selected, white when selected
                status_text = bar._message.get("status", "")
                status_color = get_status_color(status_text, is_selected=is_selected)
                bar._status_label.configure(bg=bg, fg=status_color)

    def trigger_selected_message(self):
        """Trigger action for the selected message"""
        message = self.messages[self.selected_index]
        if "window_name" in message:
            try:
                # Hide window to tray before triggering focus
                self._hide_window()
                print(f"[UI] Window hidden to tray before focus trigger")

                # Build focus URL from window_name
                focus_url = f"focus:{message['window_name']}"
                subprocess.Popen(["powershell.exe", "-Command", f"Start-Process '{focus_url}'"])
                print(f"Triggered: {focus_url}")
            except Exception as e:
                print(f"Error triggering focus protocol: {e}")

    def on_tab_pressed(self, event):
        """Handle Tab key - move to next message"""
        self.selected_index = (self.selected_index + 1) % len(self.messages)
        self.update_selection()
        self._scroll_to_selected()
        return "break"

    def on_up_pressed(self, event):
        """Handle Up arrow - move to previous message"""
        self.selected_index = (self.selected_index - 1) % len(self.messages)
        self.update_selection()
        self._scroll_to_selected()
        return "break"

    def on_down_pressed(self, event):
        """Handle Down arrow - move to next message"""
        self.selected_index = (self.selected_index + 1) % len(self.messages)
        self.update_selection()
        self._scroll_to_selected()
        return "break"

    def _scroll_to_selected(self):
        """Scroll canvas to ensure selected item is visible"""
        if not self.message_bars or self.selected_index < 0:
            return

        # Get the container of the selected bar
        selected_bar = self.message_bars[self.selected_index]
        container = selected_bar.master.master  # bar_frame -> canvas -> container

        # Update layout to get accurate positions
        self.canvas.update_idletasks()

        # Get container position relative to scrollable frame
        container_y = container.winfo_y()
        container_height = container.winfo_height()

        # Get visible region
        canvas_height = self.canvas.winfo_height()
        scroll_top = self.canvas.canvasy(0)
        scroll_bottom = scroll_top + canvas_height

        # Scroll if needed
        if container_y < scroll_top:
            # Item is above visible area - scroll up
            self.canvas.yview_moveto(container_y / self.messages_container.winfo_height())
        elif container_y + container_height > scroll_bottom:
            # Item is below visible area - scroll down
            target = (container_y + container_height - canvas_height) / self.messages_container.winfo_height()
            self.canvas.yview_moveto(target)

    def on_enter_pressed(self, event):
        """Handle Enter key - trigger selected message"""
        self.trigger_selected_message()
        return "break"

    def on_page_up(self, event):
        """Handle Page Up key - scroll up"""
        self.canvas.yview_scroll(-5, "units")
        return "break"

    def on_page_down(self, event):
        """Handle Page Down key - scroll down"""
        self.canvas.yview_scroll(5, "units")
        return "break"

    def on_home_pressed(self, event):
        """Handle Home key - jump to first window"""
        if self.messages:
            self.selected_index = 0
            self.update_selection()
            self.canvas.yview_moveto(0)  # Scroll to top
        return "break"

    def on_end_pressed(self, event):
        """Handle End key - jump to last window"""
        if self.messages:
            self.selected_index = len(self.messages) - 1
            self.update_selection()
            self.canvas.yview_moveto(1)  # Scroll to bottom
        return "break"

    def on_letter_pressed(self, event):
        """Handle letter keys (a-z) - hide window to tray (except special keys)"""
        # Check if the pressed key is a letter (a-z, A-Z)
        # Exclude 'a' which is used for "addressed"
        if event.char and len(event.char) == 1 and event.char.isalpha() and event.char.lower() != 'a':
            self._hide_window()
            print(f"[UI] Letter key '{event.char}' pressed - hiding window to tray")
            return "break"

    def on_delete_pressed(self, event):
        """Handle Delete key - delete selected window from database"""
        if not self.windows or self.selected_index < 0:
            return "break"

        # Get the window to delete
        window_to_delete = self.windows[self.selected_index]
        window_name = window_to_delete.get("window_name", "Unknown")

        print(f"[UI] Deleting window: {window_name}")

        # Delete from database (monitor thread will handle UI reload)
        if delete_window(window_name):
            print(f"[UI] Deleted '{window_name}'")
        else:
            print(f"[UI] Failed to delete '{window_name}'")

        return "break"

    def on_addressed_pressed(self, event):
        """Handle 'a' key - mark selected window as addressed"""
        if not self.windows or self.selected_index < 0:
            return "break"

        # Get the window to update
        window = self.windows[self.selected_index]
        window_name = window.get("window_name", "Unknown")

        print(f"[UI] Marking as addressed: {window_name}")

        # Update status in database (monitor thread will handle UI reload)
        if update_window_status(window_name, "addressed"):
            print(f"[UI] '{window_name}' marked as addressed.")
        else:
            print(f"[UI] Failed to update '{window_name}'")

        return "break"

    # ====== MESSAGE MONITORING ======
    # Functions for monitoring message queue and updating the UI with new messages

    def monitor_queue_for_updates(self):
        """Background thread - continuously monitor database for ANY changes"""
        print(f"[MONITOR] Starting database monitor")
        print(f"[MONITOR] DB_DIR = {DB_DIR}")

        # Debug log file
        debug_log = DB_DIR / "monitor_debug.txt"
        def log_debug(msg):
            try:
                with open(debug_log, "a") as f:
                    f.write(f"{datetime.now().isoformat()} {msg}\n")
            except: pass

        log_debug(f"Monitor started. DB_DIR={DB_DIR}")
        check_count = 0
        last_hash = None

        while self.monitor_running:
            try:
                # Use database hash for change detection (atomic, reliable)
                current_hash = get_db_hash()

                check_count += 1
                if check_count % 10 == 0:
                    print(f"[MONITOR] Check #{check_count}: DB hash={current_hash[:8] if current_hash else 'None'}...")

                # Detect change by comparing database hash
                if current_hash and current_hash != last_hash and last_hash is not None:
                    print(f"[MONITOR] DB changed (hash: {last_hash[:8]}... -> {current_hash[:8]}...)")
                    log_debug(f"DB changed: {last_hash} -> {current_hash}")

                    # Load windows from database
                    current_windows = load_window_statuses()
                    log_debug(f"Loaded {len(current_windows)} windows: {[w.get('window_name') for w in current_windows]}")

                    # Schedule full UI reload on main thread
                    self.root.after(0, self.reload_all_windows, current_windows)
                    log_debug("Scheduled reload_all_windows")

                    # Update last hash
                    last_hash = current_hash
                elif last_hash is None:
                    # First time - just record hash, don't reload
                    last_hash = current_hash

                # Sleep before next check
                time.sleep(0.5)
            except Exception as e:
                print(f"[MONITOR] Error monitoring database: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

    def reload_all_windows(self, new_windows):
        """Reload the entire UI with new window list (called from main thread via root.after)"""
        if not hasattr(self, 'messages_container'):
            return

        print(f"[UI] Reloading all windows: {len(new_windows)} total")

        # Check if any windows have a "done" status within the last 1 second
        should_popup = False

        # Skip popup logic if disabled
        if not POPUP_DISABLED:
            current_time = datetime.now()
            for window in new_windows:
                window_name = window.get("window_name")
                window_status = window.get("status")
                window_timestamp = window.get("timestamp")

                if window_status in POPUP_STATUSES:
                    # Parse timestamp and check if it's recent (within 1 second)
                    try:
                        window_time = datetime.fromisoformat(window_timestamp)
                        time_diff = (current_time - window_time).total_seconds()

                        if time_diff <= 1.0:  # Within last 1 second
                            should_popup = True
                            print(f"[UI] RECENT done: '{window_name}' ({time_diff:.2f}s ago) - triggers popup")
                            break
                        else:
                            print(f"[UI] OLD done: '{window_name}' ({time_diff:.2f}s ago) - no popup")
                    except:
                        pass  # Skip if timestamp parsing fails

        # Update our windows and messages lists
        # new_windows are already sorted by timestamp (most recent first) from load_window_statuses()
        self.windows = new_windows
        self.messages = self.windows  # Alias for compatibility

        # Clear all existing message bars from the UI
        for widget in self.messages_container.winfo_children():
            widget.destroy()

        # Clear the message bars list
        self.message_bars = []

        # Recreate all message bars
        for i, window in enumerate(self.windows):
            bar = self.create_message_bar(self.messages_container, i, window)
            self.message_bars.append(bar)

        # Update selection to first item if needed
        if self.selected_index >= len(self.windows):
            self.selected_index = 0 if self.windows else -1
        self.update_selection()

        # Force UI redraw
        self.messages_container.update_idletasks()

        # Popup window if needed
        if should_popup:
            if not self.window_visible:
                print(f"[UI] Window is hidden - showing from tray")
                self._show_window()
            else:
                print(f"[UI] Window is visible - bringing to front")
                self.popup_window()
        else:
            print(f"[UI] No popup - no window statuses in POPUP_STATUSES list")

        print(f"[UI] Reloaded {len(self.windows)} windows, {len(self.message_bars)} bars created")

    def add_new_messages(self, new_messages):
        """Add new messages to the UI (called from main thread via root.after)"""
        # Get the messages container (need to store reference during init)
        if not hasattr(self, 'messages_container'):
            return

        # Add new messages to the beginning of our messages list
        for msg in reversed(new_messages):
            self.messages.insert(0, msg)

        # Clear all existing message bars from the UI
        for widget in self.messages_container.winfo_children():
            widget.destroy()

        # Clear the message bars list
        self.message_bars = []

        # Recreate all message bars in the correct order
        for i, msg in enumerate(self.messages):
            bar = self.create_message_bar(self.messages_container, i, msg)
            self.message_bars.append(bar)

        # Update selection to first item if needed
        if self.selected_index >= len(self.messages):
            self.selected_index = 0 if self.messages else -1
        self.update_selection()

        # Debug output
        print(f"[UI] Added {len(new_messages)} new messages. Total messages: {len(self.messages)}")
        print(f"[UI] Recreated {len(self.message_bars)} message bars")

        # Force UI redraw - this is critical for dynamic widgets
        self.messages_container.update_idletasks()

        # Check if any new messages have a status that triggers popup
        should_popup = False
        if not POPUP_DISABLED:
            for msg in new_messages:
                msg_status = msg.get("status")
                if msg_status in POPUP_STATUSES:
                    should_popup = True
                    print(f"[UI] Message with status '{msg_status}' triggers popup")
                    break

        # Only popup the window if a triggering status was found (and popup not disabled)
        if should_popup and not POPUP_DISABLED:
            # If window is hidden in tray, show it first, otherwise just popup
            if not self.window_visible:
                print(f"[UI] Window is hidden - showing from tray")
                self._show_window()
            else:
                print(f"[UI] Window is visible - bringing to front")
                self.popup_window()
        else:
            print(f"[UI] No popup - message statuses not in POPUP_STATUSES list: {POPUP_STATUSES}")

        # Refresh selection (keep current selection or adjust if needed)
        self.update_selection()

        # Print to console for debugging
        print(f"[UI] Added {len(new_messages)} new message(s). Total: {len(self.messages)}")

    # ====== UI/WINDOW MANAGEMENT ======
    # Functions for system tray, hotkey setup, window visibility, and popups

    def setup_tray_icon(self):
        """Setup system tray icon"""
        # Create a simple icon (bell emoji representation)
        icon_image = Image.new('RGB', (64, 64), color='#2C3E50')
        draw = ImageDraw.Draw(icon_image)

        # Draw a bell shape (simple circle for now)
        draw.ellipse([16, 16, 48, 48], fill='#3498DB')

        # Create tray icon menu
        menu = pystray.Menu(
            pystray.MenuItem('Show', self.show_window),
            pystray.MenuItem('Hide', self.hide_window),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Exit', self.quit_app)
        )

        # Create tray icon
        self.tray_icon = pystray.Icon(
            "Notifications",
            icon_image,
            "Notification App",
            menu
        )

        # Run tray icon in separate thread
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()

        print("[TRAY] System tray icon created")

    def show_window(self, icon=None, item=None):
        """Show the window from tray"""
        self.root.after(0, self._show_window)

    def _show_window(self):
        """Internal method to show window (called from main thread)"""
        # Pre-render all content before showing to avoid white flash
        if hasattr(self, 'messages_container'):
            self.messages_container.update_idletasks()
        if hasattr(self, 'canvas'):
            self.canvas.update_idletasks()

        # Show the window without the visual flicker
        self.root.deiconify()
        self.root.update_idletasks()  # Force immediate render before popup

        # Now bring to front
        self.popup_window()
        self.window_visible = True
        print("[APP] Window shown from tray")

    def hide_window(self, icon=None, item=None):
        """Hide the window to tray"""
        self.root.after(0, self._hide_window)

    def _hide_window(self):
        """Internal method to hide window (called from main thread)"""
        self.root.withdraw()
        self.window_visible = False
        print("[APP] Window hidden to tray")

    def quit_app(self, icon=None, item=None):
        """Quit the application"""
        print("[APP] Quitting application...")
        self.tray_icon.stop()
        self.root.after(0, self.on_closing)

    def setup_global_hotkey(self):
        """Setup global hotkey listener for Ctrl+,"""
        def on_activate():
            """Toggle window visibility when hotkey is pressed"""
            print("[HOTKEY] Ctrl+, pressed - toggling window")
            if self.window_visible:
                self.hide_window()
            else:
                self.show_window()

        # Create hotkey combination: Ctrl+,
        hotkey = keyboard.HotKey(
            keyboard.HotKey.parse('<ctrl>+,'),
            on_activate
        )

        def for_canonical(f):
            return lambda k: f(self.hotkey_listener.canonical(k))

        # Start global keyboard listener in background thread
        self.hotkey_listener = keyboard.Listener(
            on_press=for_canonical(hotkey.press),
            on_release=for_canonical(hotkey.release)
        )
        self.hotkey_listener.start()

        print("[HOTKEY] Global hotkey Ctrl+, registered")

    # ====== LISTENER & SUBPROCESS MANAGEMENT ======
    # Functions for managing the ntfy listener subprocess and process lifecycle

    def start_listener_subprocess(self):
        """Start the ntfy listener as a subprocess on same platform as app"""
        try:
            # Get the path to the listener script
            listener_path = Path(__file__).parent / "ntfy_listener.py"

            # Kill any existing listener processes first
            try:
                if platform.system() == 'Windows':
                    subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/FI", "WINDOWTITLE eq ntfy_listener*"],
                                 capture_output=True, text=True)
                else:
                    subprocess.run(["pkill", "-f", "ntfy_listener.py"],
                                 capture_output=True, text=True)
            except:
                pass

            # Start the listener subprocess
            print(f"[APP] sys.executable = {sys.executable}")
            print(f"[APP] listener_path = {listener_path}")
            print(f"[APP] listener_path exists = {listener_path.exists()}")

            # Both app and listener run on same platform (Windows) for proper SQLite locking
            # Log to file for debugging (use DB_DIR which handles cross-platform paths)
            listener_log = DB_DIR / "listener_subprocess.log"
            print(f"[APP] Listener log: {listener_log}")
            try:
                log_file = open(str(listener_log), "w")
            except Exception as e:
                print(f"[APP] Could not open log file: {e}")
                log_file = subprocess.DEVNULL

            if platform.system() == 'Windows':
                # Windows launch - use same Python as app
                self.listener_process = subprocess.Popen(
                    [sys.executable, str(listener_path)],
                    stdout=log_file if log_file != subprocess.DEVNULL else subprocess.DEVNULL,
                    stderr=subprocess.STDOUT if log_file != subprocess.DEVNULL else subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                # Linux/WSL launch
                self.listener_process = subprocess.Popen(
                    ["python3", str(listener_path)],
                    stdout=log_file if log_file != subprocess.DEVNULL else subprocess.DEVNULL,
                    stderr=subprocess.STDOUT if log_file != subprocess.DEVNULL else subprocess.DEVNULL
                )

            print(f"[APP] Listener started with PID: {self.listener_process.pid}")

            # Register cleanup on exit
            atexit.register(self.stop_listener_subprocess)

            # Also handle window close event
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        except Exception as e:
            print(f"[APP] Error starting listener: {e}")
            import traceback
            traceback.print_exc()

    def check_listener_health(self):
        """Check if listener process is alive and restart if dead"""
        try:
            if hasattr(self, 'listener_process') and self.listener_process:
                poll = self.listener_process.poll()

                if poll is not None:
                    # Process has terminated
                    print(f"[APP] Listener died with exit code {poll}. Restarting...")
                    self.start_listener_subprocess()
                else:
                    # Process is still running
                    print(f"[APP] Listener health check: OK (PID {self.listener_process.pid})")

        except Exception as e:
            print(f"[APP] Error checking listener health: {e}")

        # Schedule next health check in 30 seconds
        self.root.after(30000, self.check_listener_health)

    def stop_listener_subprocess(self):
        """Stop the ntfy listener subprocess"""
        if hasattr(self, 'listener_process') and self.listener_process:
            try:
                print(f"[APP] Stopping listener process PID: {self.listener_process.pid}")

                # Try graceful termination first
                self.listener_process.terminate()

                # Wait up to 2 seconds for process to end
                try:
                    self.listener_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    self.listener_process.kill()
                    self.listener_process.wait()

                print("[APP] Listener stopped")
            except Exception as e:
                print(f"[APP] Error stopping listener: {e}")

    def kill_existing_processes(self):
        """Kill any existing notification app processes"""
        current_pid = os.getpid()
        print(f"[APP] Checking for existing app instances (current PID: {current_pid})")

        try:
            # Kill other Python processes running notification_app or main.py
            if platform.system() == 'Windows' or 'win' in sys.platform:
                # Windows - use taskkill
                subprocess.run(["taskkill", "/F", "/IM", "notification_app.py"],
                             capture_output=True, text=True)
                subprocess.run(["taskkill", "/F", "/IM", "main.py"],
                             capture_output=True, text=True)
            else:
                # Linux/WSL - use pgrep and kill
                result = subprocess.run(["pgrep", "-f", "notification_app.py"],
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    pids = result.stdout.strip().split('\n')
                    for pid_str in pids:
                        pid = int(pid_str.strip())
                        if pid != current_pid:
                            try:
                                os.kill(pid, signal.SIGTERM)
                                print(f"[APP] Killed existing app PID: {pid}")
                            except:
                                pass
        except Exception as e:
            print(f"[APP] Could not check for existing apps: {e}")

    def popup_window(self):
        """Bring window to front and focus it"""
        try:
            # Make sure content is rendered before bringing to front
            self.root.update_idletasks()

            # Raise the window to the top
            self.root.lift()
            self.root.attributes('-topmost', True)  # Temporarily make it topmost
            self.root.after(100, lambda: self.root.attributes('-topmost', False))  # Remove topmost after 100ms

            # Force focus
            self.root.focus_force()

            # On Windows, also try to bring to foreground
            if platform.system() == 'Windows' or 'win' in sys.platform:
                self.root.wm_state('normal')  # Restore if minimized

            print("[UI] Window brought to front")
        except Exception as e:
            print(f"[UI] Could not popup window: {e}")

    def on_closing(self):
        """Handle window close event"""
        self.monitor_running = False  # Stop the monitoring thread
        self.stop_listener_subprocess()  # Stop the listener
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()  # Stop the tray icon
        if hasattr(self, 'hotkey_listener'):
            self.hotkey_listener.stop()  # Stop the hotkey listener
        self.root.destroy()  # Close the window


if __name__ == "__main__":
    root = tk.Tk()
    app = NotificationApp(root)
    root.mainloop()
