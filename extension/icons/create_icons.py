#!/usr/bin/env python3
"""
Simple icon generator for LinkedIn Applied Jobs Collector extension
Creates basic PNG icons in different sizes
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size):
    """Create a simple icon with the specified size"""
    # Create image with LinkedIn blue background
    img = Image.new('RGBA', (size, size), (10, 102, 194, 255))  # LinkedIn blue
    draw = ImageDraw.Draw(img)
    
    # Calculate proportions
    margin = size // 8
    icon_size = size - 2 * margin
    
    # Draw white document background
    doc_x = margin
    doc_y = margin
    doc_width = icon_size
    doc_height = int(icon_size * 0.8)
    
    # Rounded rectangle for document (simplified)
    draw.rectangle([doc_x, doc_y, doc_x + doc_width, doc_y + doc_height], 
                   fill=(255, 255, 255, 230), outline=(255, 255, 255, 255), width=2)
    
    # Draw document lines
    line_height = doc_height // 8
    line_margin = size // 16
    
    for i in range(6):
        y = doc_y + line_margin + i * line_height
        line_width = int(doc_width * (0.7 - i * 0.05))  # Decreasing width
        x = doc_x + (doc_width - line_width) // 2
        draw.rectangle([x, y, x + line_width, y + 2], fill=(10, 102, 194, 255))
    
    # Draw checkmark
    check_size = size // 6
    check_x = doc_x + doc_width // 4
    check_y = doc_y + doc_height * 3 // 4
    
    # Simple checkmark
    draw.line([(check_x, check_y), (check_x + check_size//2, check_y + check_size//2), 
               (check_x + check_size, check_y - check_size//2)], 
              fill=(10, 102, 194, 255), width=max(2, size//32))
    
    # Draw collection dots
    dot_size = max(2, size//16)
    dots_x = doc_x + doc_width + margin//2
    for i in range(3):
        dot_y = doc_y + margin + i * (margin + dot_size)
        draw.ellipse([dots_x, dot_y, dots_x + dot_size, dot_y + dot_size], 
                     fill=(255, 255, 255, 255))
    
    return img

def main():
    """Generate icons in different sizes"""
    sizes = [16, 48, 128]
    
    for size in sizes:
        print(f"Creating icon {size}x{size}...")
        icon = create_icon(size)
        filename = f"icon{size}.png"
        icon.save(filename, "PNG")
        print(f"Saved {filename}")
    
    print("All icons created successfully!")

if __name__ == "__main__":
    main() 