"""UI utility functions for the notification app"""

from PIL import Image, ImageDraw


def create_rounded_rectangle_image(width, height, radius, color_hex):
    """Create a rounded rectangle image using Pillow"""
    # Convert hex color to RGB tuple
    color = tuple(int(color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

    # Create image with transparent background
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded rectangle
    # Draw the main rectangle
    draw.rectangle([radius, 0, width - radius, height], fill=color)
    draw.rectangle([0, radius, width, height - radius], fill=color)

    # Draw corner circles
    draw.ellipse([0, 0, radius * 2, radius * 2], fill=color)
    draw.ellipse([width - radius * 2, 0, width, radius * 2], fill=color)
    draw.ellipse([0, height - radius * 2, radius * 2, height], fill=color)
    draw.ellipse([width - radius * 2, height - radius * 2, width, height], fill=color)

    return img
