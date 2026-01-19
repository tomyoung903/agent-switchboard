"""
Styling module for Notification App
Handles all aesthetic configuration and theme settings
"""

# ============================================================================
# COLOR PALETTE - Modern Dark Theme
# ============================================================================

# Background colors
BG_PRIMARY = "#1e1e2e"      # Dark background
BG_SECONDARY = "#2d2d44"    # Slightly lighter for panels
BG_SELECTED = "#0d47a1"     # Vibrant blue for selected

# Text colors
TEXT_PRIMARY = "#e0e0e0"    # Light text
TEXT_SECONDARY = "#a0a0a0"  # Dimmed text
TEXT_SELECTED = "#ffffff"   # White for selected items
TEXT_ACCENT = "#64b5f6"     # Light blue accent

# Status colors
STATUS_DONE = "#4caf50"      # Green for done
STATUS_ONGOING = "#ffb74d"   # Orange/amber for ongoing
STATUS_ADDRESSED = "#78909c" # Blue-gray for addressed
STATUS_DEFAULT = "#a0a0a0"   # Gray for unknown status

# Selection indicator
SELECTION_BAR_COLOR = "#64b5f6"  # Light blue bar for selected item
SELECTION_BAR_WIDTH = 4

# Border and separator colors
BORDER_COLOR = "#404050"
SEPARATOR_COLOR = "#3d3d54"

# ============================================================================
# SPACING & LAYOUT
# ============================================================================

WINDOW_PADDING = 12          # Padding inside window
BAR_PADDING_X = 14           # Horizontal padding for message bars
BAR_PADDING_Y = 12           # Vertical padding for message bars
BAR_SPACING = 8              # Space between message bars
BORDER_WIDTH = 1             # Border width for bars
CORNER_RADIUS = 8            # Corner radius for rounded bars (in pixels)

# ============================================================================
# FONTS - Use tuples that can be converted to Font objects when needed
# ============================================================================

# Title font - bold, slightly larger
TITLE_FONT = ("Segoe UI", 11, "bold")

# Content font - regular, slightly dimmed
CONTENT_FONT = ("Segoe UI", 10)

# Small hint font - for keyboard shortcuts
HINT_FONT = ("Segoe UI", 8, "italic")

# ============================================================================
# COMPONENT STYLING FUNCTIONS
# ============================================================================

def get_message_bar_style(is_selected=False):
    """Get styling dict for a message bar based on selection state"""
    if is_selected:
        return {
            "bg": BG_SELECTED,
            "fg_title": TEXT_SELECTED,
            "fg_content": TEXT_SELECTED,
            "relief": "raised",
            "bd": 2,
        }
    else:
        return {
            "bg": BG_SECONDARY,
            "fg_title": TEXT_PRIMARY,
            "fg_content": TEXT_SECONDARY,
            "relief": "flat",
            "bd": 1,
        }


def get_status_color(status, is_selected=False):
    """Get color for status text based on status value"""
    if is_selected:
        return TEXT_SELECTED  # White when selected for readability

    status_lower = (status or "").lower()
    if status_lower == "done":
        return STATUS_DONE
    elif status_lower == "ongoing":
        return STATUS_ONGOING
    elif status_lower == "addressed":
        return STATUS_ADDRESSED
    else:
        return STATUS_DEFAULT


# ============================================================================
# WINDOW STYLING
# ============================================================================

def apply_window_theme(root, bg_color=BG_PRIMARY):
    """Apply the theme to the root window"""
    root.configure(bg=bg_color)


def apply_frame_theme(frame, bg_color=BG_PRIMARY):
    """Apply the theme to a frame"""
    frame.configure(bg=bg_color)
